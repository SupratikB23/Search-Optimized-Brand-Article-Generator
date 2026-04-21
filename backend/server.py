"""
FastAPI server — exposes the 4 engines as REST endpoints + client management.
Run: python backend/run.py   (or: uvicorn server:app --reload --port 8000)
"""

import os
import sys
from pathlib import Path
from dataclasses import asdict

# Fix Windows console encoding so Unicode in print() doesn't crash uvicorn
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp1252", "charmap"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() in ("cp1252", "charmap"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from company_scraper import CompanyDNA, extract_company_dna
from trend_researcher import research_trends, TrendItem
from article_generator import (
    build_brief, write_article, ArticleBrief,
    quality_check, has_banned_phrases,
)
import database as db


app = FastAPI(title="SearchOS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.init_db()
    print("[searchos] Database ready at", db.DB_PATH)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _filter(dc_class, data: dict) -> dict:
    """Strip keys not present in a dataclass so extra frontend fields don't crash init."""
    known = {f.name for f in dc_class.__dataclass_fields__.values()}
    return {k: v for k, v in data.items() if k in known}


# ── Request models ────────────────────────────────────────────────────────────

class ExtractDNARequest(BaseModel):
    url: str

class ResearchTrendsRequest(BaseModel):
    services: list[str]
    top_keywords: list[str]
    existing_titles: list[str] = []

class BuildBriefRequest(BaseModel):
    dna: dict
    trend: dict
    angle: str
    article_type: str = "educational"

class WriteArticleRequest(BaseModel):
    brief: dict
    dna: dict
    trend: dict
    model: str = "gemini-2.0-flash"
    api_key: str | None = None

# ── Client management models ──────────────────────────────────────────────────

class CreateClientRequest(BaseModel):
    url: str

class SaveDNARequest(BaseModel):
    dna: dict

class SaveTrendsRequest(BaseModel):
    report: dict

class SaveBriefRequest(BaseModel):
    brief: dict

class SaveArticleRequest(BaseModel):
    article: dict
    brief_id: int | None = None


# ── Engine endpoints (unchanged) ──────────────────────────────────────────────

@app.post("/api/extract-dna")
async def api_extract_dna(req: ExtractDNARequest):
    try:
        dna = await extract_company_dna(req.url)
        return asdict(dna)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/research-trends")
async def api_research_trends(req: ResearchTrendsRequest):
    try:
        report = await research_trends(
            services=req.services,
            top_keywords=req.top_keywords,
            existing_titles=req.existing_titles,
        )
        return {
            "industry":          report.industry,
            "query_used":        report.query_used,
            "generated_at":      report.generated_at,
            "trends":            [asdict(t) for t in report.trends],
            "key_themes":        report.key_themes,
            "emerging_keywords": report.emerging_keywords,
            "article_angles":    report.article_angles,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/build-brief")
async def api_build_brief(req: BuildBriefRequest):
    try:
        dna   = CompanyDNA(**_filter(CompanyDNA,   req.dna))
        trend = TrendItem(**_filter(TrendItem,     req.trend))
        brief = build_brief(dna, trend, req.angle, article_type=req.article_type)
        return asdict(brief)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/write-article")
async def api_write_article(req: WriteArticleRequest):
    try:
        dna   = CompanyDNA(**_filter(CompanyDNA,    req.dna))
        trend = TrendItem(**_filter(TrendItem,      req.trend))
        brief = ArticleBrief(**_filter(ArticleBrief, req.brief))
        api_key = req.api_key or os.environ.get("GOOGLE_API_KEY", "")

        article = await write_article(brief, dna, trend, api_key=api_key, model=req.model)
        if not article:
            raise HTTPException(status_code=500, detail="Article generation failed")

        checks = quality_check(article.content, dna, brief)
        banned = has_banned_phrases(article.content)

        return {
            "content":          article.content,
            "word_count":       article.word_count,
            "seo_title":        article.seo_title,
            "meta_description": article.meta_description,
            "schema_faq":       article.schema_faq,
            "quality_passed":   article.quality_passed,
            "generated_at":     article.generated_at,
            "quality_checks":   [{"label": k.replace("_", " "), "pass": v} for k, v in checks.items()],
            "banned_phrases":   banned,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Client management endpoints ───────────────────────────────────────────────

@app.get("/api/clients")
async def api_list_clients():
    try:
        return await db.list_clients()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clients")
async def api_create_client(req: CreateClientRequest):
    try:
        return await db.create_client(req.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clients/{client_id}")
async def api_get_client(client_id: int):
    try:
        client = await db.get_client(client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return client
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/clients/{client_id}")
async def api_delete_client(client_id: int):
    try:
        ok = await db.delete_client(client_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Client not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Save endpoints (auto-called by frontend after each engine) ────────────────

@app.post("/api/clients/{client_id}/save-dna")
async def api_save_dna(client_id: int, req: SaveDNARequest):
    try:
        updated = await db.save_dna(client_id, req.dna)
        return {"ok": True, "client": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clients/{client_id}/save-trends")
async def api_save_trends(client_id: int, req: SaveTrendsRequest):
    try:
        record_id = await db.save_trends(client_id, req.report)
        return {"ok": True, "id": record_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clients/{client_id}/save-brief")
async def api_save_brief(client_id: int, req: SaveBriefRequest):
    try:
        record_id = await db.save_brief(client_id, req.brief)
        return {"ok": True, "id": record_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clients/{client_id}/save-article")
async def api_save_article(client_id: int, req: SaveArticleRequest):
    try:
        record_id = await db.save_article(client_id, req.brief_id, req.article)
        return {"ok": True, "id": record_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
