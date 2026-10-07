"""Neo4j graph store for regulatory circular relationships.

Provides template-based Cypher queries for amendment chains, freshness checks,
impact analysis, and source summaries — no LLM-generated queries.
"""

from __future__ import annotations

import ssl

from neo4j import GraphDatabase

from rag_app.config import settings


def _fix_ssl_certs():
    """Point SSL_CERT_FILE to certifi's CA bundle if system certs are missing."""
    import os
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass


class GraphStore:
    """Neo4j-backed knowledge graph of regulatory circulars and their relationships."""

    def __init__(self):
        _fix_ssl_certs()
        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.neo4j_user, settings.NEO4J_PASSWORD),
        )
        self._driver.verify_connectivity()
        self.ensure_schema()

    def close(self):
        self._driver.close()

    # ── Schema ────────────────────────────────────────────────

    def ensure_schema(self):
        """Create uniqueness constraints (idempotent)."""
        constraints = [
            ("circular_number_unique", "Circular", "number"),
            ("regulation_name_unique", "Regulation", "name"),
            ("entity_type_unique", "Entity", "type"),
            ("topic_name_unique", "Topic", "name"),
        ]
        with self._driver.session() as session:
            for name, label, prop in constraints:
                session.run(
                    f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                )

    # ── Write methods (used by graph builder) ─────────────────

    def upsert_circular(self, data: dict):
        """MERGE a Circular node from obligation extraction data.

        Expected keys: number, title, date, source, effective_date,
        risk_level, doc_id, link, summary, subject.
        """
        with self._driver.session() as session:
            session.run(
                """
                MERGE (c:Circular {number: $number})
                SET c.title       = $title,
                    c.date        = $date,
                    c.source      = $source,
                    c.effective_date = $effective_date,
                    c.risk_level  = $risk_level,
                    c.doc_id      = $doc_id,
                    c.link        = $link,
                    c.summary     = $summary,
                    c.subject     = $subject,
                    c.is_latest   = true
                """,
                **data,
            )

    def create_supersedes(self, newer_number: str, older_ref: str, description: str = ""):
        """Create (newer)-[:SUPERSEDES]->(older) edge. Marks older as not latest."""
        with self._driver.session() as session:
            session.run(
                """
                MERGE (newer:Circular {number: $newer})
                MERGE (older:Circular {number: $older})
                MERGE (newer)-[r:SUPERSEDES]->(older)
                SET r.description = $desc,
                    older.is_latest = false
                """,
                newer=newer_number,
                older=older_ref,
                desc=description,
            )

    def create_amends(self, circular_number: str, regulation_name: str, provisions: str = ""):
        """Create (circular)-[:AMENDS]->(regulation) edge."""
        with self._driver.session() as session:
            session.run(
                """
                MERGE (c:Circular {number: $cn})
                MERGE (r:Regulation {name: $reg})
                SET r.source = c.source
                MERGE (c)-[rel:AMENDS]->(r)
                SET rel.specific_provisions = $provisions
                """,
                cn=circular_number,
                reg=regulation_name,
                provisions=provisions,
            )

    def create_applies_to(self, circular_number: str, entity_type: str, conditions: str = ""):
        """Create (circular)-[:APPLIES_TO]->(entity) edge."""
        with self._driver.session() as session:
            session.run(
                """
                MERGE (c:Circular {number: $cn})
                MERGE (e:Entity {type: $etype})
                MERGE (c)-[r:APPLIES_TO]->(e)
                SET r.conditions = $conditions
                """,
                cn=circular_number,
                etype=entity_type,
                conditions=conditions,
            )

    def create_about(self, circular_number: str, topic_name: str):
        """Create (circular)-[:ABOUT]->(topic) edge."""
        with self._driver.session() as session:
            session.run(
                """
                MERGE (c:Circular {number: $cn})
                MERGE (t:Topic {name: $topic})
                MERGE (c)-[:ABOUT]->(t)
                """,
                cn=circular_number,
                topic=topic_name,
            )

    def create_is_a(self, child_type: str, parent_type: str):
        """Create (child_entity)-[:IS_A]->(parent_entity) hierarchy edge."""
        with self._driver.session() as session:
            session.run(
                """
                MERGE (child:Entity {type: $child})
                MERGE (parent:Entity {type: $parent})
                MERGE (child)-[:IS_A]->(parent)
                """,
                child=child_type,
                parent=parent_type,
            )

    # ── Read methods (used by RAG pipeline) ───────────────────

    def get_amendment_chain(self, circular_number: str) -> list[dict]:
        """Walk the SUPERSEDES chain in both directions to build a full timeline.

        Returns circulars ordered oldest→newest.
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (start:Circular {number: $cn})
                OPTIONAL MATCH path_newer = (start)<-[:SUPERSEDES*]-(newer)
                OPTIONAL MATCH path_older = (start)-[:SUPERSEDES*]->(older)
                WITH collect(DISTINCT newer) + [start] + collect(DISTINCT older) AS all_nodes
                UNWIND all_nodes AS node
                WITH DISTINCT node
                RETURN node.number AS number,
                       node.title AS title,
                       node.date AS date,
                       node.is_latest AS is_latest,
                       node.source AS source,
                       node.link AS link,
                       node.summary AS summary
                ORDER BY node.date ASC
                """,
                cn=circular_number,
            )
            return [dict(record) for record in result]

    def get_latest_version(self, circular_number: str) -> dict | None:
        """Follow SUPERSEDES edges backward to find the latest (non-superseded) circular."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (start:Circular {number: $cn})
                OPTIONAL MATCH (latest)-[:SUPERSEDES*]->(start)
                WHERE latest.is_latest = true
                WITH coalesce(latest, start) AS current
                RETURN current.number AS number,
                       current.title AS title,
                       current.date AS date,
                       current.is_latest AS is_latest,
                       current.source AS source,
                       current.link AS link,
                       current.summary AS summary
                LIMIT 1
                """,
                cn=circular_number,
            )
            record = result.single()
            return dict(record) if record else None

    def get_related_circulars(self, circular_number: str) -> list[dict]:
        """Find circulars related via shared regulations, entities, or topics (1-hop)."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (c:Circular {number: $cn})
                OPTIONAL MATCH (c)-[:AMENDS]->(r:Regulation)<-[:AMENDS]-(r1)
                WITH c, collect(DISTINCT r1) AS via_reg
                OPTIONAL MATCH (c)-[:APPLIES_TO]->(e:Entity)<-[:APPLIES_TO]-(r2)
                WITH c, via_reg, collect(DISTINCT r2) AS via_entity
                WITH c, via_reg + via_entity AS partial
                OPTIONAL MATCH (c)-[:ABOUT]->(t:Topic)<-[:ABOUT]-(r3)
                WITH c, partial, collect(DISTINCT r3) AS via_topic
                WITH partial + via_topic AS all_related
                UNWIND all_related AS rel
                WITH DISTINCT rel
                WHERE rel.number IS NOT NULL
                RETURN rel.number AS number,
                       rel.title AS title,
                       rel.date AS date,
                       rel.source AS source,
                       rel.link AS link
                ORDER BY rel.date DESC
                LIMIT 10
                """,
                cn=circular_number,
            )
            return [dict(record) for record in result]

    def check_freshness(self, circular_numbers: list[str]) -> dict[str, dict]:
        """For a batch of circular numbers, check if each is still the latest version.

        Returns {circular_number: {is_latest: bool, superseded_by: str|None}}.
        """
        if not circular_numbers:
            return {}
        with self._driver.session() as session:
            result = session.run(
                """
                UNWIND $numbers AS cn
                OPTIONAL MATCH (c:Circular {number: cn})
                OPTIONAL MATCH (newer:Circular)-[:SUPERSEDES]->(c)
                WHERE newer.is_latest = true
                RETURN cn AS number,
                       c IS NOT NULL AS found,
                       c.is_latest AS is_latest,
                       newer.number AS superseded_by
                """,
                numbers=circular_numbers,
            )
            freshness = {}
            for record in result:
                if record["found"]:
                    freshness[record["number"]] = {
                        "is_latest": record["is_latest"] if record["is_latest"] is not None else True,
                        "superseded_by": record["superseded_by"],
                    }
            return freshness

    def get_impact_analysis(self, circular_number: str) -> dict:
        """Get entities affected by a circular plus any amended regulations."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (c:Circular {number: $cn})
                OPTIONAL MATCH (c)-[a:APPLIES_TO]->(e:Entity)
                OPTIONAL MATCH (c)-[am:AMENDS]->(r:Regulation)
                RETURN c.title AS title,
                       c.summary AS summary,
                       c.risk_level AS risk_level,
                       collect(DISTINCT {type: e.type, conditions: a.conditions}) AS entities,
                       collect(DISTINCT {name: r.name, provisions: am.specific_provisions}) AS regulations
                """,
                cn=circular_number,
            )
            record = result.single()
            if not record:
                return {"title": "", "entities": [], "regulations": []}
            data = dict(record)
            # Filter out nulls from optional matches
            data["entities"] = [e for e in data["entities"] if e.get("type")]
            data["regulations"] = [r for r in data["regulations"] if r.get("name")]
            return data

    def get_source_summary(self, source: str, start_date: str = "", end_date: str = "") -> list[dict]:
        """Get all circulars from a source, optionally filtered by date range."""
        query = """
            MATCH (c:Circular)
            WHERE c.source = $source
        """
        params: dict = {"source": source}
        if start_date:
            query += " AND c.date >= $start_date"
            params["start_date"] = start_date
        if end_date:
            query += " AND c.date <= $end_date"
            params["end_date"] = end_date
        query += """
            OPTIONAL MATCH (c)-[:ABOUT]->(t:Topic)
            RETURN c.number AS number,
                   c.title AS title,
                   c.date AS date,
                   c.is_latest AS is_latest,
                   c.risk_level AS risk_level,
                   c.summary AS summary,
                   collect(DISTINCT t.name) AS topics
            ORDER BY c.date DESC
        """
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def get_cross_source_by_topic(self, topic: str) -> list[dict]:
        """Get circulars about a topic grouped by source — for cross-regulator queries."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (c:Circular)-[:ABOUT]->(t:Topic)
                WHERE toLower(t.name) CONTAINS toLower($topic)
                RETURN c.number AS number,
                       c.title AS title,
                       c.date AS date,
                       c.source AS source,
                       c.link AS link
                ORDER BY c.source, c.date DESC
                """,
                topic=topic,
            )
            return [dict(record) for record in result]

    def get_circulars_for_entity(self, entity_type: str) -> list[dict]:
        """Find circulars applying to an entity type, traversing IS_A hierarchy downward.

        E.g. querying "Bank" also finds circulars tagged "Scheduled Commercial Bank",
        "Urban Cooperative Bank", etc.
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (target:Entity {type: $etype})
                OPTIONAL MATCH (descendant:Entity)-[:IS_A*]->(target)
                WITH target, collect(DISTINCT descendant) AS descendants
                WITH descendants + [target] AS all_entities
                UNWIND all_entities AS e
                WITH e
                MATCH (c:Circular)-[:APPLIES_TO]->(e)
                WITH DISTINCT c, e
                RETURN c.number AS number,
                       c.title AS title,
                       c.date AS date,
                       c.source AS source,
                       c.link AS link,
                       e.type AS matched_entity
                ORDER BY c.date DESC
                LIMIT 20
                """,
                etype=entity_type,
            )
            return [dict(record) for record in result]

    def get_stats(self) -> dict:
        """Return node/relationship counts for diagnostics."""
        with self._driver.session() as session:
            result = session.run(
                """
                OPTIONAL MATCH (c:Circular) WITH count(c) AS circulars
                OPTIONAL MATCH ()-[r:SUPERSEDES]->() WITH circulars, count(r) AS supersedes
                OPTIONAL MATCH ()-[a:AMENDS]->() WITH circulars, supersedes, count(a) AS amends
                OPTIONAL MATCH ()-[ap:APPLIES_TO]->() WITH circulars, supersedes, amends, count(ap) AS applies
                OPTIONAL MATCH ()-[ab:ABOUT]->() WITH circulars, supersedes, amends, applies, count(ab) AS about
                OPTIONAL MATCH ()-[ia:IS_A]->()
                RETURN circulars, supersedes, amends, applies, about, count(ia) AS is_a
                """
            )
            record = result.single()
            return dict(record) if record else {}
