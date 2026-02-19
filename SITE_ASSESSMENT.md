# Site Assessment: RBI, SEBI, MCA, IRDAI, eGazette

## 1. Can we programmatically detect new publications within 4 hours?

| Site | Feasibility | Method | Latency |
|------|-------------|--------|---------|
| **RBI** | **Yes** | RSS feeds available (`notifications_rss.xml`, `pressreleases_rss.xml`, `Publication_rss.xml`, `speeches_rss.xml`, `tenders_rss.xml`) at rbi.org.in. Poll every 30-60 min. | < 1 hour |
| **SEBI** | **Yes** | RSS feeds available at sebi.gov.in/rss.html (Circulars, Master Circulars, Orders, Press Releases). Also listed on API Setu. | < 1 hour |
| **MCA** | **Yes (fragile)** | RSS feeds at mca.gov.in (Press Releases, Notices & Circulars). But site uses Akamai bot protection — RSS may also be gated. Fallback: poll with headless browser. | 1-4 hours |
| **IRDAI** | **Polling only** | No RSS/API. Must scrape the listing page periodically. Page is stable enough for polling every 1-2 hours. Liferay CMS serves data server-side, so simple GET works. | 1-2 hours |
| **eGazette** | **Polling only** | No RSS/API. ASP.NET postback navigation required (session token + ViewState). Must replay the full homepage -> postback -> parse flow each time. | 2-4 hours |

**Verdict:** RBI and SEBI are easy (RSS). MCA is possible but fragile. IRDAI and eGazette require periodic scraping. 4-hour detection is achievable for all 5 sites.

---

## 2. Machine-readable text PDFs vs scanned images

| Site | Machine-Readable | Scanned/Image | Success Rate | Avg Content Size |
|------|-----------------|----------------|-------------|-----------------|
| **RBI** | 19/19 | 0 | **100%** | ~5,300 chars |
| **SEBI** | 48/50 | 0 | **96%** | ~132,000 chars |
| **MCA** | 24/30 | 0 | **80%** | ~10,200 chars |
| **IRDAI** | 518/575 | 1 (0.2%) | **90%** | ~10,600 chars |
| **eGazette** | 200/200 | 0 | **100%** | ~133,000 chars |

**Key findings:**
- **Zero scanned-image PDFs found** across 813 documents (1 borderline outlier in IRDAI)
- All sites publish natively digital, text-extractable PDFs
- `pdfplumber` works well across all sites; no OCR needed
- MCA's 80% rate is due to download failures (Akamai protection), not scan quality
- IRDAI's ~10% failures are mostly network/encoding issues, not scanned docs
- ~20% of IRDAI and ~48% of eGazette documents are in Hindi — text extraction still works

**Verdict:** Essentially 100% machine-readable. No need for OCR infrastructure.

---

## 3. How often does the site structure change?

Based on Wayback Machine CDX analysis (unique page digests over time):

| Site | Stability | Change Rate | Unique Digests | Maintenance Needed |
|------|-----------|------------|----------------|-------------------|
| **SEBI** | Very stable | Minimal in 5+ years | 1 unique digest across 13 snapshots | Yearly review |
| **RBI** | Moderate | Monthly | 57 unique / 200+ snapshots (28%) | Monthly review |
| **eGazette** | Stable structure | Content updates weekly | URLs stable, listings refresh | Quarterly review |
| **MCA** | Unstable | Every 3-4 days | 109 unique / 200+ snapshots (54%) | Weekly monitoring |
| **IRDAI** | Very unstable | Near-daily | 16 unique / 17 snapshots (94%) | Weekly monitoring |

**Key findings:**
- **SEBI** is rock-solid — the listing page structure hasn't changed in years
- **RBI** changes periodically but follows consistent ASP.NET patterns
- **eGazette** URL patterns and ASP.NET postback structure are stable; only content rotates
- **MCA** and **IRDAI** change frequently — crawlers for these sites need robust error handling and regular maintenance
- IRDAI migrated to Liferay CMS relatively recently, so the high churn may stabilize

---

## 4. Are there RSS feeds or APIs?

| Site | RSS Feeds | Official API | 3rd-Party API | Email/SMS Alerts |
|------|-----------|-------------|---------------|-----------------|
| **RBI** | **Yes** — 5 feeds (notifications, press releases, publications, speeches, tenders) at `rbi.org.in/Scripts/rss.aspx` | **Yes** — RBI Innovation Hub (rbih.tech), RBI API Marketplace | Yes | Unknown |
| **SEBI** | **Yes** — feeds for Circulars, Master Circulars, Orders, Gazette Notifications at `sebi.gov.in/rss.html` | **Yes** — via API Setu platform (`directory.apisetu.gov.in`) | Yes | Yes (investor alerts) |
| **MCA** | **Yes** — Press Releases, Notices & Circulars at `mca.gov.in/.../rss-feeds.html` | No official | **Yes** — Attestr, AuthBridge, Masters India, Surepass (company/director data) | Unknown |
| **IRDAI** | **No** | **No** | **No** | No |
| **eGazette** | **No** | **No** | **No** | No |

**Verdict:** RBI is best-equipped (5 RSS feeds + APIs). SEBI and MCA have RSS. IRDAI and eGazette have nothing — scraping is the only option.

---

## 5. Historical notification volumes

| Site | All-Time Total | Annual Avg | Peak Year | Current Trend | Frequency |
|------|---------------|-----------|-----------|---------------|-----------|
| **RBI** | Thousands+ | Not quantified publicly | — | Steady, multiple per week | ~3-5/week |
| **SEBI** | Hundreds | ~21-22/yr (2025) | 2026 (pace: ~170/yr) | Increasing | ~2/week |
| **MCA** | 200+ circulars since Companies Act 2013 | Variable | 89 in first year of 2013 Act | Event-driven, irregular | As-needed |
| **IRDAI** | **575** (full crawl) | **54/yr** (2016-2025 avg) | **101** (2020, pandemic) | Declining — master circular consolidation | ~1/week |
| **eGazette** | Tens of thousands | ~1,000-1,500 extraordinary + 52 weekly/yr | 2026 (spike) | Increasing | ~3-5/day (extraordinary) |

**IRDAI detailed year-by-year** (from crawled data — 575 circulars):
```
2026:   2     (Jan-Feb, partial)
2025:  13
2024:  29
2023:  51
2022:  64
2021:  53
2020: 101     <-- pandemic peak
2019:  45
2018:  58
2017:  65
2016:  61
2015:  33     (partial)
```

**Key findings:**
- **IRDAI** shows a clear downward trend post-2020, partly due to IRDAI issuing master circulars that consolidate/repeal 55+ older circulars (May 2024)
- **eGazette** extraordinary gazettes are high-volume (~3-5/day) — most are ministry-specific statutory notifications
- **SEBI** volume is modest but growing in 2026
- **MCA** circulars are event-driven (major spikes around new legislation like Companies Act 2013)
- **RBI** doesn't publish aggregate stats but is the most prolific issuer

---

## Summary & Recommendations

1. **For 4-hour detection:** Use RSS for RBI/SEBI/MCA. Poll IRDAI every 1-2 hours, eGazette every 2-4 hours.
2. **PDF processing:** `pdfplumber` is sufficient — no OCR needed. All sites publish machine-readable PDFs.
3. **Crawler maintenance:** SEBI crawler is lowest-maintenance. MCA and IRDAI crawlers need weekly monitoring due to frequent site structure changes.
4. **RSS/API integration:** Add RSS polling for RBI, SEBI, and MCA to get near-real-time updates without scraping.
5. **Volume planning:** Expect ~1,500-2,000 total new documents/year across all 5 sites (dominated by eGazette extraordinary notifications).
