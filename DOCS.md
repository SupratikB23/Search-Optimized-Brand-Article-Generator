# BrandSCOPE – Technical Documentation

This file contains deep technical details for contributors and developers. 
For setup and usage, see [README.md](./README.md).

---

## Table of Contents

- [The Four Engines](#the-four-engines)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Data Storage](#data-storage)
- [How the Pipeline Works](#how-the-pipeline-works)

---

## The Four Engines

### Engine 01 - Brand DNA Extractor

Builds a complete intelligence profile of a brand from its website and the open web.

**Scraping pipeline:**

1. Sitemap XML parse - fast, no browser, most reliable source of URLs
2. BFS URL discovery via `httpx` - discovers up to 60 pages at depth 3 without a browser
3. JSON-LD structured data mining - extracts services, articles, locations from `<script type="application/ld+json">` blocks
4. Playwright full-render scraping with:
   - `networkidle` wait + `domcontentloaded` fallback + body text polling (8 s)
   - Accordion / `<details>` / Bootstrap collapse expansion
   - Tab panel clicking (up to 5 tabs)
   - Load More button clicking (up to 3 times)
   - Shadow DOM text piercing via `document.createTreeWalker`
   - Same-domain iframe content extraction
   - Raw HTML `httpx` fallback when JS yields fewer than 200 characters
5. Web search via DuckDuckGo DDGS - searches for brand services, differentiators, and published articles across the open web
6. Gemini AI synthesis - classifies all scraped and searched content into structured outputs

**Output fields:**

| Field | Description |
|---|---|
| `services` | Clean noun phrases (2-7 words each) - e.g. "Speech Recognition API", "Indic Language Models (Sarvam-1)" |
| `tone_adjectives` | AI-classified voice descriptors - e.g. "technical", "mission-driven", "confident" |
| `tone_sample` | Representative sentence extracted from actual page text |
| `uses_first_person` | Boolean derived from AI perspective classification |
| `usps` | Specific, factual differentiators with numbers and firsts where available |
| `existing_article_titles` | Merged from 4 sources: scraped links, JSON-LD, case-study metrics, internet search |
| `top_keywords` | AI brand keywords prepended to NLP-extracted noun chunks (up to 50) |
| `locations` | Cities and regions from JSON-LD + text pattern matching |

---

### Engine 02 - Live Trend Research

Pulls real-time signals from the open web and classifies them into four segments relative to the brand.

**Sources:**
- Google News RSS - zero cost, real-time headlines
- DuckDuckGo DDGS - broader web context, no API key required
- Brand-specific searches - what the brand has done recently and what it is planning

**Segments:**

| Segment | Description |
|---|---|
| `brand_news` | Recent launches, releases, and announcements by the brand |
| `brand_future` | Forward-looking signals - roadmap, upcoming features, stated plans |
| `industry_trend` | Broad market and technology trends in the brand's space |
| `competitive` | Competitor moves and market positioning signals |

**AI layer:** Gemini re-classifies every collected item into the correct segment, writes a 2-sentence brand trajectory summary, and generates 10-14 brand-specific article angles - not fill-in templates, but ready-to-write titles connecting brand activity to industry movement.

**Fallback:** All queries target 2026. If fewer than 8 results are returned, the engine automatically supplements with the same queries targeting 2025.

---

### Engine 03 - Article Brief Builder

Runs gap analysis between the brand's existing article coverage and the incoming trend signal. Produces a structured brief with SEO, AEO, and GEO scores assigned to each proposed angle before a word is written.

**Brief structure:**
- Working title and primary angle
- Target keyword cluster
- Recommended article type (educational / listicle / case study / opinion)
- SEO score, AEO score, GEO score (0-100 each)
- Suggested outline and talking points
- Brand voice guidance derived from Engine 01

---

### Engine 04 - Article Writer

Takes the brief and the full brand DNA and writes a complete article in the brand's voice.

**Model routing:**
- Primary: Gemini 2.0 Flash (`gemini-2.0-flash`)
- Fallback: Groq (when Gemini is rate-limited or unavailable)

**Quality controls:**
- Banned phrase filter - rejects output containing AI cliches ("in today's fast-paced", "delve into", "it goes without saying", etc.)
- SEO / AEO / GEO score computed on the final article
- All scores persisted to the database alongside the article

---

## Architecture

```
Browser (React + Vite)
        |
        | HTTP (JSON)
        v
FastAPI backend  (uvicorn, port 8000)
        |
        |-- Engine 01: company_scraper.py
        |       |-- Playwright (headless Chromium)
        |       |-- httpx BFS crawler
        |       |-- spaCy NLP
        |       |-- DDGS web search
        |       `-- Gemini 2.0 Flash (AI synthesis)
        |
        |-- Engine 02: trend_researcher.py
        |       |-- Google News RSS
        |       |-- DDGS web search
        |       `-- Gemini 2.0 Flash (classification + angles)
        |
        |-- Engine 03: article_generator.py (build_brief)
        |       `-- Gemini 2.0 Flash
        |
        `-- Engine 04: article_generator.py (write_article)
                |-- Gemini 2.0 Flash (primary)
                `-- Groq (fallback)

Persistence
        |-- SQLite (aiosqlite)  →  data/searchos.db
        `-- File system         →  clients/{slug}/0{1-4}_*/
```

---

## Project Structure

```
Search Optimization/
|
|-- backend/
|   |-- server.py              # FastAPI app - all REST endpoints
|   |-- company_scraper.py     # Engine 01 - Brand DNA extractor
|   |-- trend_researcher.py    # Engine 02 - Live trend research
|   |-- article_generator.py   # Engine 03 + 04 - Brief builder and article writer
|   |-- database.py            # aiosqlite ORM + file storage helpers
|   |-- run.py                 # Uvicorn entrypoint
|   |-- requirements.txt
|   |-- .env                   # Your API keys (git-ignored)
|   `-- .env.example
|
|-- frontend/
|   |-- src/
|   |   |-- App.jsx            # Root component - client management + engine tabs
|   |   |-- Landing.jsx        # Landing page with animated background
|   |   |-- BrandDNA.jsx       # Engine 01 UI
|   |   |-- TrendResearch.jsx  # Engine 02 UI - segment filter, brand summary
|   |   |-- BriefBuilder.jsx   # Engine 03 UI
|   |   |-- ArticleWriter.jsx  # Engine 04 UI
|   |   |-- components.jsx     # Shared design system components
|   |   |-- api.js             # Typed fetch wrappers for all endpoints
|   |   `-- App.css            # Global styles, CSS variables, animations
|   |-- package.json
|   `-- dist/                  # Production build (served by FastAPI as static files)
|
|-- data/
|   `-- searchos.db            # SQLite database (auto-created on first run)
|
|-- clients/                   # Per-client file storage (auto-created)
|   `-- {brand-slug}/
|       |-- 01_brand_dna/
|       |-- 02_trend_research/
|       |-- 03_article_briefs/
|       `-- 04_articles/
|
|-- package.json               # Root convenience scripts
`-- README.md
```

---

## API Reference

All endpoints accept and return JSON.

### Client Management

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/clients` | List all clients |
| `POST` | `/api/clients` | Create a new client from a URL |
| `GET` | `/api/clients/{id}` | Get a single client with full history |
| `DELETE` | `/api/clients/{id}` | Delete client and all associated data |

### Engine Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/extract-dna` | Run Engine 01 - Brand DNA extraction |
| `POST` | `/api/research-trends` | Run Engine 02 - Live trend research |
| `POST` | `/api/build-brief` | Run Engine 03 - Article brief generation |
| `POST` | `/api/write-article` | Run Engine 04 - Full article writing |

### Persistence Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/clients/{id}/save-dna` | Persist brand DNA to DB and file system |
| `POST` | `/api/clients/{id}/save-trends` | Persist trend report |
| `POST` | `/api/clients/{id}/save-brief` | Persist article brief |
| `POST` | `/api/clients/{id}/save-article` | Persist final article with scores |
| `GET` | `/api/clients/{id}/articles/{article_id}` | Retrieve a saved article |

### Engine 01 - Request / Response

```json
// POST /api/extract-dna
{ "url": "https://example.com" }

// Response (CompanyDNA)
{
  "name": "Example Brand",
  "domain": "example.com",
  "services": ["Service Name (Detail)", "..."],
  "tone_adjectives": ["technical", "confident"],
  "tone_sample": "A representative sentence from the site.",
  "uses_first_person": false,
  "usps": ["Specific factual claim", "..."],
  "existing_article_titles": ["Article title", "..."],
  "top_keywords": ["keyword", "..."],
  "locations": ["City", "..."]
}
```

### Engine 02 - Request / Response

```json
// POST /api/research-trends
{
  "services": ["Service Name"],
  "top_keywords": ["keyword"],
  "existing_titles": ["Previously written title"],
  "brand_name": "Example Brand",
  "domain": "example.com"
}

// Response (TrendReport)
{
  "industry": "saas",
  "trends": [
    {
      "title": "Trend headline",
      "summary": "...",
      "source": "Google News",
      "segment": "brand_news",
      "relevance_score": 0.87,
      "published": "Mon, 28 Apr 2026"
    }
  ],
  "brand_summary": "Two-sentence brand trajectory summary.",
  "segments": { "brand_news": 4, "industry_trend": 12, "competitive": 3, "brand_future": 2 },
  "article_angles": ["Ready-to-write article title", "..."],
  "key_themes": ["theme", "..."]
}
```

---

## Data Storage

### SQLite Schema

```
clients
  id, name, domain, slug, url, created_at

brand_dna
  id, client_id, dna_json, created_at

trend_reports
  id, client_id, report_json, created_at

article_briefs
  id, client_id, brief_json, angle, article_type, created_at

generated_articles
  id, client_id, brief_id, title, content, word_count,
  seo_score, aeo_score, geo_score, model_used, created_at
```

### File System Layout

Every engine output is also written to disk under `clients/{slug}/` for easy access, backup, and version history. The `{timestamp}` in filenames is a UTC ISO string, so multiple runs per client accumulate as separate files rather than overwriting.

---

## How the Pipeline Works

```
1. Add a client
   Enter a website URL. The system creates a client record and directory structure.

2. Engine 01 - Brand DNA
   Playwright opens the site, crawls up to 60 pages via BFS, expands accordions
   and tabs, extracts text, mines JSON-LD, then runs DuckDuckGo searches and
   passes everything to Gemini for structured extraction.
   Output: services, tone, USPs, keywords, existing articles.

3. Engine 02 - Trend Research
   Searches Google News RSS and DuckDuckGo for 2026 industry signals and brand-
   specific news. Gemini classifies each result into one of four segments and
   generates brand-aware article angles.
   Output: segmented trend list, brand summary, article angles.

4. Engine 03 - Brief Builder
   You pick an article angle. The system runs gap analysis against existing
   coverage and builds a structured brief with SEO, AEO, and GEO scores.
   Output: brief with outline, keyword cluster, and scores.

5. Engine 04 - Article Writer
   Gemini writes the full article using the brief and brand DNA as context.
   Quality check runs against the banned phrase list. Final scores are computed
   and the article is saved.
   Output: complete article in Markdown with final SEO / AEO / GEO scores.
```

---

## Development Notes

- After any change to a `backend/*.py` file, restart the FastAPI server.
- After any change to a `frontend/src/` file, run `npm run build` in `frontend/` to update the served assets, or use `npm run dev` for hot-reload during development.
- The SQLite database is created automatically at `data/searchos.db` on first server start via the `init_db()` migration in `database.py`. Existing databases are migrated non-destructively using `ALTER TABLE IF NOT EXISTS` guards.
- The `clients/` directory is git-ignored. All client data is local to your machine.

---
