import pytest


def test_extract_excerpt_both_markers_found():
    """Markers found — return substring between them."""
    from rag_app.services.rag_pipeline import RAGPipeline

    text = "AAA start here BBB some content CCC end here DDD"
    result = RAGPipeline._extract_excerpt(text, "start here", "end here")
    assert "start here" in result
    assert "some content" in result
    assert "end here" in result
    assert "AAA" not in result
    assert "DDD" not in result


def test_extract_excerpt_start_not_found():
    """Start marker missing — return full text."""
    from rag_app.services.rag_pipeline import RAGPipeline

    text = "AAA BBB CCC"
    result = RAGPipeline._extract_excerpt(text, "MISSING", "CCC")
    assert result == text


def test_extract_excerpt_end_not_found():
    """End marker missing — return full text."""
    from rag_app.services.rag_pipeline import RAGPipeline

    text = "AAA BBB CCC"
    result = RAGPipeline._extract_excerpt(text, "AAA", "MISSING")
    assert result == text


def test_extract_excerpt_end_before_start():
    """End marker appears before start — return full text."""
    from rag_app.services.rag_pipeline import RAGPipeline

    text = "end here AAA start here BBB"
    result = RAGPipeline._extract_excerpt(text, "start here", "end here")
    assert result == text


def test_parse_topics_json_valid():
    """Valid JSON array parses correctly."""
    from rag_app.services.rag_pipeline import RAGPipeline

    raw = '[{"title": "T1", "summary": "S1", "start_marker": "a", "end_marker": "b"}]'
    result = RAGPipeline._parse_topics_json(raw)
    assert len(result) == 1
    assert result[0]["title"] == "T1"


def test_parse_topics_json_with_fences():
    """JSON wrapped in markdown fences still parses."""
    from rag_app.services.rag_pipeline import RAGPipeline

    raw = '```json\n[{"title": "T1", "summary": "S1", "start_marker": "a", "end_marker": "b"}]\n```'
    result = RAGPipeline._parse_topics_json(raw)
    assert len(result) == 1


def test_parse_topics_json_invalid():
    """Invalid JSON returns None."""
    from rag_app.services.rag_pipeline import RAGPipeline

    result = RAGPipeline._parse_topics_json("not json at all")
    assert result is None


def test_parse_topics_json_not_array():
    """JSON object (not array) returns None."""
    from rag_app.services.rag_pipeline import RAGPipeline

    result = RAGPipeline._parse_topics_json('{"title": "T1"}')
    assert result is None
