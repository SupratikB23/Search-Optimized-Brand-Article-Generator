"""
Persistent storage for SearchOS.
SQLite (via aiosqlite) for metadata + structured file system for full outputs.

Directory layout per client:
  clients/{slug}/
    01_brand_dna/      company_dna.json
    02_trend_research/ trends_{ts}.json
    03_article_briefs/ brief_{ts}_{title}.json
    04_articles/       {slug}.md
"""

import json
import re
import shutil
import aiosqlite
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

BASE_DIR    = Path(__file__).parent.parent
DB_PATH     = BASE_DIR / "data" / "searchos.db"
CLIENTS_DIR = BASE_DIR / "clients"

CLIENT_SUBDIRS = [
    "01_brand_dna",
    "02_trend_research",
    "03_article_briefs",
    "04_articles",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def url_to_slug(url: str) -> str:
    """https://www.nakshinteriors.com  →  nakshinteriors-com"""
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return re.sub(r"[^a-z0-9]+", "-", netloc).strip("-") or "brand"


def _make_client_dirs(slug: str):
    for sub in CLIENT_SUBDIRS:
        (CLIENTS_DIR / slug / sub).mkdir(parents=True, exist_ok=True)


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL DEFAULT '',
    domain     TEXT    NOT NULL DEFAULT '',
    slug       TEXT    NOT NULL UNIQUE,
    url        TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS brand_dna (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    dna_json   TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    UNIQUE(client_id)
);

CREATE TABLE IF NOT EXISTS trend_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    report_json TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS article_briefs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id    INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    brief_json   TEXT    NOT NULL,
    article_type TEXT    NOT NULL DEFAULT '',
    title        TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_articles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id        INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    brief_id         INTEGER REFERENCES article_briefs(id),
    title            TEXT    NOT NULL DEFAULT '',
    article_slug     TEXT    NOT NULL DEFAULT '',
    content_md       TEXT    NOT NULL DEFAULT '',
    word_count       INTEGER NOT NULL DEFAULT 0,
    seo_title        TEXT    NOT NULL DEFAULT '',
    meta_description TEXT    NOT NULL DEFAULT '',
    quality_passed   INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL
);
"""


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


# ── Client CRUD ───────────────────────────────────────────────────────────────

async def create_client(url: str) -> dict:
    slug   = url_to_slug(url)
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    name   = domain.split(".")[0].title()   # e.g. "Nakshinteriors"
    now    = _now()
    _make_client_dirs(slug)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            cur = await db.execute(
                "INSERT INTO clients (name, domain, slug, url, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (name, domain, slug, url, now, now),
            )
            await db.commit()
            cid = cur.lastrowid
        except aiosqlite.IntegrityError:
            # Slug collision — return the existing record
            row = await (await db.execute(
                "SELECT id FROM clients WHERE slug = ?", (slug,)
            )).fetchone()
            cid = row["id"]

        row = await (await db.execute(
            "SELECT * FROM clients WHERE id = ?", (cid,)
        )).fetchone()
        return dict(row)


async def list_clients() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("""
            SELECT
                c.*,
                (SELECT COUNT(*) FROM trend_reports      WHERE client_id = c.id) AS trend_count,
                (SELECT COUNT(*) FROM generated_articles WHERE client_id = c.id) AS article_count,
                (SELECT COUNT(*) FROM article_briefs     WHERE client_id = c.id) AS brief_count,
                (SELECT dna_json FROM brand_dna          WHERE client_id = c.id LIMIT 1) AS _dna_snap
            FROM clients c
            ORDER BY c.updated_at DESC
        """)).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            snap = d.pop("_dna_snap", None)
            if snap:
                try:
                    dna = json.loads(snap)
                    d["has_dna"]  = True
                    d["tagline"]  = dna.get("tagline", "")
                except Exception:
                    d["has_dna"] = False
                    d["tagline"] = ""
            else:
                d["has_dna"] = False
                d["tagline"] = ""
            result.append(d)
        return result


async def get_client(client_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        row = await (await db.execute(
            "SELECT * FROM clients WHERE id = ?", (client_id,)
        )).fetchone()
        if not row:
            return None
        c = dict(row)

        dna_row = await (await db.execute(
            "SELECT dna_json FROM brand_dna WHERE client_id = ? LIMIT 1",
            (client_id,),
        )).fetchone()
        c["dna"] = json.loads(dna_row["dna_json"]) if dna_row else None

        trend_row = await (await db.execute(
            "SELECT report_json FROM trend_reports WHERE client_id = ? ORDER BY created_at DESC LIMIT 1",
            (client_id,),
        )).fetchone()
        c["latest_trends"] = json.loads(trend_row["report_json"]) if trend_row else None

        art_rows = await (await db.execute(
            """SELECT id, title, article_slug, word_count, seo_title, quality_passed, created_at
               FROM generated_articles WHERE client_id = ? ORDER BY created_at DESC""",
            (client_id,),
        )).fetchall()
        c["articles"] = [dict(r) for r in art_rows]
        return c


async def delete_client(client_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT slug FROM clients WHERE id = ?", (client_id,)
        )).fetchone()
        if not row:
            return False
        slug = row["slug"]
        await db.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        await db.commit()

    client_dir = CLIENTS_DIR / slug
    if client_dir.exists():
        shutil.rmtree(client_dir)
    return True


# ── Save engine outputs ───────────────────────────────────────────────────────

async def save_dna(client_id: int, dna: dict) -> dict:
    """Upsert DNA — always one per client. Returns updated client row."""
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        slug_row = await (await db.execute(
            "SELECT slug FROM clients WHERE id = ?", (client_id,)
        )).fetchone()
        if not slug_row:
            raise ValueError(f"Client {client_id} not found")
        slug = slug_row["slug"]

        dna_str = json.dumps(dna, ensure_ascii=False)
        existing = await (await db.execute(
            "SELECT id FROM brand_dna WHERE client_id = ?", (client_id,)
        )).fetchone()
        if existing:
            await db.execute(
                "UPDATE brand_dna SET dna_json = ?, created_at = ? WHERE client_id = ?",
                (dna_str, now, client_id),
            )
        else:
            await db.execute(
                "INSERT INTO brand_dna (client_id, dna_json, created_at) VALUES (?,?,?)",
                (client_id, dna_str, now),
            )

        # Update client name/domain from extracted DNA
        if dna.get("name"):
            await db.execute(
                "UPDATE clients SET name = ?, domain = ?, updated_at = ? WHERE id = ?",
                (dna["name"], dna.get("domain", ""), now, client_id),
            )
        else:
            await db.execute("UPDATE clients SET updated_at = ? WHERE id = ?", (now, client_id))
        await db.commit()

        row = await (await db.execute("SELECT * FROM clients WHERE id = ?", (client_id,))).fetchone()
        updated = dict(row)

    path = CLIENTS_DIR / slug / "01_brand_dna" / "company_dna.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dna, indent=2, ensure_ascii=False), encoding="utf-8")
    return updated


async def save_trends(client_id: int, report: dict) -> int:
    """Each scan creates a new timestamped record."""
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        slug_row = await (await db.execute(
            "SELECT slug FROM clients WHERE id = ?", (client_id,)
        )).fetchone()
        if not slug_row:
            raise ValueError(f"Client {client_id} not found")
        slug = slug_row["slug"]

        cur = await db.execute(
            "INSERT INTO trend_reports (client_id, report_json, created_at) VALUES (?,?,?)",
            (client_id, json.dumps(report, ensure_ascii=False), now),
        )
        await db.execute("UPDATE clients SET updated_at = ? WHERE id = ?", (now, client_id))
        await db.commit()
        record_id = cur.lastrowid

    ts   = now[:19].replace(":", "-").replace("T", "_")
    path = CLIENTS_DIR / slug / "02_trend_research" / f"trends_{ts}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return record_id


async def save_brief(client_id: int, brief: dict) -> int:
    """Each brief build creates a new timestamped record."""
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        slug_row = await (await db.execute(
            "SELECT slug FROM clients WHERE id = ?", (client_id,)
        )).fetchone()
        if not slug_row:
            raise ValueError(f"Client {client_id} not found")
        slug = slug_row["slug"]

        cur = await db.execute(
            "INSERT INTO article_briefs (client_id, brief_json, article_type, title, created_at) VALUES (?,?,?,?,?)",
            (
                client_id,
                json.dumps(brief, ensure_ascii=False),
                brief.get("article_type", ""),
                brief.get("title", ""),
                now,
            ),
        )
        await db.execute("UPDATE clients SET updated_at = ? WHERE id = ?", (now, client_id))
        await db.commit()
        record_id = cur.lastrowid

    ts         = now[:19].replace(":", "-").replace("T", "_")
    title_slug = re.sub(r"[^a-z0-9]+", "-", (brief.get("title") or "brief").lower())[:40].strip("-")
    path       = CLIENTS_DIR / slug / "03_article_briefs" / f"brief_{ts}_{title_slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    return record_id


async def save_article(client_id: int, brief_id: int | None, article: dict) -> int:
    """Save generated article to DB + write .md file."""
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        slug_row = await (await db.execute(
            "SELECT slug FROM clients WHERE id = ?", (client_id,)
        )).fetchone()
        if not slug_row:
            raise ValueError(f"Client {client_id} not found")
        client_slug = slug_row["slug"]

        art_slug = article.get("slug") or re.sub(
            r"[^a-z0-9]+", "-",
            (article.get("seo_title") or "article").lower()
        )[:60].strip("-")

        cur = await db.execute(
            """INSERT INTO generated_articles
               (client_id, brief_id, title, article_slug, content_md,
                word_count, seo_title, meta_description, quality_passed, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                client_id,
                brief_id,
                article.get("seo_title") or article.get("title", ""),
                art_slug,
                article.get("content", ""),
                article.get("word_count", 0),
                article.get("seo_title", ""),
                article.get("meta_description", ""),
                1 if article.get("quality_passed") else 0,
                now,
            ),
        )
        await db.execute("UPDATE clients SET updated_at = ? WHERE id = ?", (now, client_id))
        await db.commit()
        record_id = cur.lastrowid

    art_dir = CLIENTS_DIR / client_slug / "04_articles"
    art_dir.mkdir(parents=True, exist_ok=True)
    if article.get("content"):
        (art_dir / f"{art_slug}.md").write_text(article["content"], encoding="utf-8")

    return record_id
