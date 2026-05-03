<img width="2911" height="1262" alt="BrandSCOPE_generated" src="https://github.com/user-attachments/assets/c07f718f-ab80-42eb-a382-a5276a6c8eac" />


# BrandSCOPE – Brand Search Content Optimization & Publishing Engine

**A 4-engine content intelligence platform that extracts a brand's DNA, tracks live industry trends, builds SEO/AEO/GEO-scored article briefs, and writes articles that sound exactly like the brand.**

Runs entirely on localhost. No subscriptions. Powered by Gemini (free tier) and Groq (free tier).

---

## Table of Contents

- [Overview](#overview)
- [The Four Engines](#the-four-engines)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)

---

## Overview

SearchOS is a self-hosted brand content platform built around a sequential 4-engine pipeline. Each engine feeds the next one, producing articles that are simultaneously optimized for:

- **SEO** - Traditional search engine ranking signals
- **AEO** - Answer Engine Optimization for featured snippets and AI Overviews
- **GEO** - Generative Engine Optimization for citation by ChatGPT, Perplexity, and Claude

The system manages multiple clients. Each client's full pipeline output - DNA, trends, briefs, and articles - is stored locally in a structured directory layout and a SQLite database.

---

## The Four Engines

**Engine 01 – Brand DNA Extractor** <br>
Scrapes a brand's website across up to 60 pages using Playwright + BFS crawling, mines JSON-LD structured data, runs DuckDuckGo searches, and synthesizes everything into a structured brand profile via Gemini.

**Engine 02 – Live Trend Research** <br>
Pulls real-time signals from Google News RSS and DuckDuckGo, then uses Gemini to classify each result into one of four segments: `brand_news`, `brand_future`, `industry_trend`, `competitive`. Outputs 10–14 ready-to-write article angles.

**Engine 03 – Article Brief Builder** <br>
Runs gap analysis between existing brand coverage and incoming trends. Produces a structured brief with SEO, AEO, and GEO scores assigned before a word is written.

**Engine 04 – Article Writer** <br>
Writes a complete article in the brand's voice using the brief and Brand DNA as context. Routes between Gemini 2.0 Flash (primary) and Groq (fallback). Filters AI clichés and computes final scores.

---

## Tech Stack

**Backend**

| Package | Purpose |
|---|---|
| FastAPI + Uvicorn | REST API server |
| Playwright | Full-render browser scraping |
| httpx | Async HTTP client for BFS crawling and fallback fetches |
| spaCy (`en_core_web_sm`) | NLP noun chunk extraction for keyword analysis |
| DDGS | DuckDuckGo web search - no API key |
| google-genai | Gemini 2.0 Flash - services, tone, USPs, classification, article writing |
| Groq | LLM fallback for article generation |
| aiosqlite | Async SQLite for metadata persistence |
| python-dotenv | Environment variable loading |

**Frontend**

| Package | Purpose |
|---|---|
| React 18 | UI framework |
| Vite 6 | Dev server and production bundler |
| Framer Motion | Animated landing page and transitions |

**Storage**

| Layer | What lives here |
|---|---|
| `data/searchos.db` | Client metadata, brief records, article metadata, SEO/AEO/GEO scores |
| `clients/{slug}/01_brand_dna/` | `company_dna.json` |
| `clients/{slug}/02_trend_research/` | `trends_{timestamp}.json` |
| `clients/{slug}/03_article_briefs/` | `brief_{timestamp}_{title}.json` |
| `clients/{slug}/04_articles/` | `{slug}.md` (final article in Markdown) |

---

## Prerequisites

- **Python** 3.11 or higher
- **Node.js** 18 or higher
- **Chromium** - installed automatically by Playwright on first run

**API keys required (both free):**

| Service | Free tier | Link |
|---|---|---|
| Google AI Studio (Gemini) | 1,500 requests/day on `gemini-2.0-flash` | aistudio.google.com/app/apikey |
| Groq | 14,400 requests/day | console.groq.com |

No other paid services, subscriptions, or cloud infrastructure required.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/search-optimization.git
cd "Search Optimization"
```

### 2. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

### 4. Download the spaCy language model

```bash
python -m spacy download en_core_web_sm
```

### 5. Install frontend dependencies

```bash
cd ../frontend
npm install
```

### 6. Build the frontend

```bash
npm run build
```

The built assets in `frontend/dist/` are served directly by the FastAPI server, so you do not need to run a separate dev server in production.

---

## Configuration

Copy the example environment file and fill in your keys:

```bash
cp backend/.env.example backend/.env
```

```env
# backend/.env

GOOGLE_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

Both keys are used only on your local machine and are never sent anywhere except the respective APIs.

---

## Running the Project

### Production mode (single command)

```bash
# From the project root
npm run server
```

This starts the FastAPI server on `http://localhost:8000`. The frontend is served from `frontend/dist/` at the same origin - no separate frontend process needed.

### Development mode (hot reload)

Open two terminals:

```bash
# Terminal 1 - Backend
cd backend
python run.py

# Terminal 2 - Frontend (hot reload)
cd frontend
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies API calls to `http://localhost:8000`.

---

