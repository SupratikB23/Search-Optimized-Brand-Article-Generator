"""
Engine 1 — Company DNA Extractor  (v2 — full rewrite)

Extraction pipeline (in order of execution):
  0.  Sitemap XML parse   — fast, no browser, most reliable source of URLs
  1.  httpx BFS crawl     — discovers deep-linked pages without a browser (Fix 2)
  2.  JSON-LD mining      — highest ROI: services/articles straight from structured data (Fix 9)
  3.  Playwright scraping — full JS rendering with:
        • networkidle wait + content-length polling        (Fix 1)
        • accordion / details / tab expansion + Load-More  (Fix 5)
        • Shadow DOM text piercing                         (Fix 3)
        • Same-domain iframe content extraction            (Fix 4)
        • Raw-HTML httpx fallback when JS returns < 200c   (Fix 8)
  4.  Dynamic section detection from BFS results           (Fix 7)
  5.  Dedicated heading extractor for services pages
"""

import asyncio
import re
import json
import httpx
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urljoin, urlparse
from collections import Counter, defaultdict

from playwright.async_api import async_playwright

# ── spaCy ─────────────────────────────────────────────────────────────────────
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    NLP_AVAILABLE = True
except Exception:
    NLP_AVAILABLE = False
    print("[warn] spaCy not available — using simple keyword extraction")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class CompanyDNA:
    """Everything the article writer needs to know about the company."""

    name: str = ""
    domain: str = ""
    tagline: str = ""
    description: str = ""

    services: list[str] = field(default_factory=list)
    industries_served: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)

    tone_adjectives: list[str] = field(default_factory=list)
    tone_sample: str = ""
    avg_sentence_length: int = 15
    uses_first_person: bool = True

    target_audience: str = ""
    pain_points: list[str] = field(default_factory=list)

    existing_article_titles: list[str] = field(default_factory=list)
    existing_article_topics: list[str] = field(default_factory=list)
    top_keywords: list[str] = field(default_factory=list)
    brand_keywords: list[str] = field(default_factory=list)

    portfolio_items: list[dict] = field(default_factory=list)

    testimonials: list[str] = field(default_factory=list)
    notable_clients: list[str] = field(default_factory=list)

    usps: list[str] = field(default_factory=list)

    about_text: str = ""
    homepage_text: str = ""


# ── Section classification ─────────────────────────────────────────────────────

SECTION_SIGNALS: dict[str, list[str]] = {
    "about": [
        "about", "about-us", "aboutus", "our-story", "ourstory",
        "who-we-are", "whoweare", "company", "team", "our-team",
        "founders", "mission", "vision", "history",
    ],
    "services": [
        "services", "service", "what-we-do", "whatwedo",
        "solutions", "solution", "offerings", "offering",
        "capabilities", "capability", "expertise",
    ],
    "portfolio": [
        "portfolio", "projects", "project", "case-studies", "casestudies",
        "case-study", "gallery", "our-work", "ourwork", "showcase",
        "clients", "references", "work",
    ],
    "blog": [
        "blog", "blogs", "insights", "insight", "articles", "article",
        "news", "resources", "resource", "stories", "story",
        "journal", "updates", "update", "thinking", "perspectives",
        "perspective", "posts", "post", "guides", "guide",
        "tutorials", "tutorial", "tips", "tip", "knowledge",
        "learn", "learning", "media", "press", "publications",
        "publication", "editorial", "thought-leadership",
        "case-studies", "casestudies", "case-study", "casestudy",
        "roster", "works", "campaigns", "our-campaigns",
        # Expanded — Fix 7
        "lab", "labs", "craft", "ventures", "studio", "writings",
        "notes", "thoughts", "reads", "explore", "content",
        "ideas", "experiments", "playground", "letters", "dispatch",
    ],
    "contact": [
        "contact", "contact-us", "contactus", "get-in-touch",
        "getintouch", "hire", "reach", "enquiry", "inquiry",
    ],
}

SKIP_SEGMENTS = {
    "tag", "tags", "category", "categories", "author", "authors",
    "page", "wp-content", "wp-admin", "wp-includes", "wp-json",
    "feed", "rss", "atom", "cdn", "assets", "static", "media",
    "uploads", "images", "img", "css", "js", "fonts",
    "search", "404", "500", "sitemap", "robots",
    "login", "logout", "register", "admin", "dashboard",
    "cart", "checkout", "account", "wishlist",
    "privacy", "terms", "disclaimer", "cookie",
    "amp", "m",
}

_SKIP_EXTS = re.compile(
    r'\.(jpg|jpeg|png|gif|svg|webp|ico|css|js|pdf|zip|mp4|mp3|woff|ttf|eot|otf)$',
    re.I,
)


# ── URL helpers ────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x20-\x7E\n]", "", text)
    return text.strip()


def classify_path(path: str) -> Optional[str]:
    """Return the section type for a URL path, or None if unrecognised."""
    segments = path.lower().strip("/").split("/")
    for seg in segments:
        seg_clean = seg.split("?")[0].split("#")[0]
        for section, signals in SECTION_SIGNALS.items():
            if seg_clean in signals:
                return section
            for signal in signals:
                if signal in seg_clean and len(signal) > 4:
                    return section
    return None


def is_listing_url(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) <= 2


def is_article_url(path: str) -> bool:
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        return False
    slug = parts[-1]
    return bool(slug) and not slug.isdigit() and len(slug) > 3


def _norm_url(url: str) -> str:
    """Strip query string, fragment, and trailing slash for deduplication."""
    return url.split("?")[0].split("#")[0].rstrip("/")


def _is_same_domain(url: str, domain: str) -> bool:
    n = urlparse(url).netloc
    return n == domain or n.endswith("." + domain) or domain.endswith("." + n)


def _is_content_url(url: str) -> bool:
    """Return False for obvious non-content URLs (images, scripts, etc.)."""
    if _SKIP_EXTS.search(url):
        return False
    for seg in urlparse(url).path.strip("/").split("/"):
        if seg in SKIP_SEGMENTS:
            return False
    return True


# ── Sitemap parser ─────────────────────────────────────────────────────────────

async def fetch_sitemap(base_url: str, domain: str) -> list[str]:
    """Try common sitemap paths. Returns a flat list of all URLs found."""
    candidates = [
        f"{base_url}/sitemap.xml",
        f"{base_url}/sitemap_index.xml",
        f"{base_url}/sitemap-0.xml",
        f"{base_url}/wp-sitemap.xml",
        f"{base_url}/news-sitemap.xml",
        f"{base_url}/post-sitemap.xml",
        f"{base_url}/page-sitemap.xml",
    ]
    urls: list[str] = []
    try:
        async with httpx.AsyncClient(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SearchOS/1.0)"},
        ) as client:
            for sitemap_url in candidates:
                try:
                    resp = await client.get(sitemap_url)
                    if resp.status_code != 200:
                        continue
                    text = resp.text

                    if "<sitemapindex" in text or ("<sitemap>" in text and "<loc>" in text):
                        sub_locs = re.findall(r"<loc>\s*(https?://[^<]+)\s*</loc>", text)
                        for sub in sub_locs[:6]:
                            if "sitemap" in sub.lower():
                                try:
                                    r2 = await client.get(sub)
                                    if r2.status_code == 200:
                                        locs = re.findall(r"<loc>\s*(https?://[^<]+)\s*</loc>", r2.text)
                                        same = [u for u in locs if domain in u]
                                        urls.extend(same[:150])
                                except Exception:
                                    pass
                        if urls:
                            print(f"[DNA] Sitemap index: {len(urls)} URLs")
                            break

                    elif "<urlset" in text or "<url>" in text:
                        locs = re.findall(r"<loc>\s*(https?://[^<]+)\s*</loc>", text)
                        same = [u for u in locs if domain in u]
                        urls.extend(same[:300])
                        if urls:
                            print(f"[DNA] Sitemap: {sitemap_url} ({len(urls)} URLs)")
                            break
                except Exception:
                    continue
    except Exception:
        pass
    return urls


# ── Fix 2: BFS URL discovery via httpx (no browser) ──────────────────────────

async def _bfs_discover_urls(
    base_url: str,
    domain: str,
    max_pages: int = 60,
    max_depth: int = 3,
) -> list[str]:
    """
    Breadth-first link discovery using plain httpx GET requests.
    No JS rendering — relies on href attributes in raw HTML.
    Sufficient to expose site structure even on most SPAs because anchor tags
    are usually server-rendered even when content is client-rendered.
    """
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(_norm_url(base_url), 0)]
    all_found: list[str] = []

    async with httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    ) as client:
        while queue and len(visited) < max_pages:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            all_found.append(url)

            if depth >= max_depth:
                continue

            try:
                resp = await client.get(url, timeout=8)
                if resp.status_code >= 400:
                    continue
                html = resp.text[:400_000]  # cap at 400 KB

                hrefs = re.findall(r'href=["\']([^"\'#\s>]+)', html)
                for href in hrefs:
                    # Resolve relative
                    try:
                        full = _norm_url(urljoin(url, href))
                    except Exception:
                        continue
                    parsed = urlparse(full)
                    if parsed.scheme not in ("http", "https"):
                        continue
                    if not _is_same_domain(full, domain):
                        continue
                    if not _is_content_url(full):
                        continue
                    if full not in visited:
                        queue.append((full, depth + 1))

            except Exception:
                continue

    print(f"[DNA] BFS discovered {len(all_found)} URLs (depth ≤ {max_depth})")
    return all_found


# ── Fix 9: JSON-LD structured data miner ──────────────────────────────────────

def _mine_json_ld(html: str) -> dict:
    """
    Parse all <script type="application/ld+json"> blocks from raw HTML.
    Extracts: services, article titles, locations, name, description.
    This is the highest-ROI fix — clean, structured data that requires no NLP.
    """
    result: dict = {
        "services": [],
        "article_titles": [],
        "locations": [],
        "name": "",
        "description": "",
    }

    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.S | re.I,
    )

    def _walk(item: dict) -> None:
        if not isinstance(item, dict):
            return
        t = item.get("@type", "")
        types = t if isinstance(t, list) else [t]

        # ── Name / description ────────────────────────────────────────────
        org_types = {
            "Organization", "LocalBusiness", "WebSite", "Corporation",
            "Store", "Restaurant", "Hotel", "Agency", "ProfessionalService",
        }
        if any(x in types for x in org_types):
            if not result["name"] and item.get("name"):
                result["name"] = str(item["name"]).strip()
            if not result["description"] and item.get("description"):
                result["description"] = str(item["description"])[:300]

            # address → locations
            addr = item.get("address", {})
            if isinstance(addr, dict):
                for key in ("addressLocality", "addressRegion", "addressCountry"):
                    val = addr.get(key, "")
                    if val and str(val) not in result["locations"]:
                        result["locations"].append(str(val))

            # areaServed
            area = item.get("areaServed", [])
            if isinstance(area, str):
                area = [area]
            for a in (area if isinstance(area, list) else []):
                name = a if isinstance(a, str) else (a.get("name", "") if isinstance(a, dict) else "")
                if name and name not in result["locations"]:
                    result["locations"].append(name)

            # hasOfferCatalog → services
            catalog = item.get("hasOfferCatalog", {})
            if isinstance(catalog, dict):
                for offer in catalog.get("itemListElement", []):
                    if isinstance(offer, dict):
                        n = (offer.get("name", "")
                             or (offer.get("itemOffered", {}) or {}).get("name", ""))
                        if n:
                            result["services"].append(str(n).strip())

            # makesOffer / offers
            offers = item.get("makesOffer", item.get("offers", []))
            if isinstance(offers, dict):
                offers = [offers]
            for offer in (offers if isinstance(offers, list) else []):
                if isinstance(offer, dict):
                    n = offer.get("name", "")
                    if n:
                        result["services"].append(str(n).strip())

        # ── Service / Product ─────────────────────────────────────────────
        if any(x in types for x in ("Service", "Product", "Offer")):
            n = item.get("name", "")
            if n:
                result["services"].append(str(n).strip())

        # ── Article / Blog ────────────────────────────────────────────────
        article_types = {
            "Article", "BlogPosting", "NewsArticle",
            "TechArticle", "HowTo", "FAQPage",
        }
        if any(x in types for x in article_types):
            title = item.get("headline", item.get("name", ""))
            if title and len(str(title)) > 5:
                result["article_titles"].append(str(title).strip())

        # ── ItemList ──────────────────────────────────────────────────────
        if "ItemList" in types:
            for elem in item.get("itemListElement", []):
                if not isinstance(elem, dict):
                    continue
                n = elem.get("name", "")
                inner = elem.get("item", {})
                if isinstance(inner, dict) and inner.get("name"):
                    n = inner["name"]
                if n and len(str(n)) > 3:
                    result["services"].append(str(n).strip())

        # Recurse into nested objects
        for v in item.values():
            if isinstance(v, dict):
                _walk(v)
            elif isinstance(v, list):
                for sub in v:
                    if isinstance(sub, dict):
                        _walk(sub)

    for raw in blocks:
        try:
            data = json.loads(raw.strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            _walk(item)

    # Deduplicate
    result["services"]       = list(dict.fromkeys(s for s in result["services"] if s))[:15]
    result["article_titles"] = list(dict.fromkeys(s for s in result["article_titles"] if s))[:15]
    result["locations"]      = list(dict.fromkeys(s for s in result["locations"] if s))[:8]
    return result


# ── Fix 8: Raw HTML text extractor ────────────────────────────────────────────

def _extract_html_text(html: str) -> str:
    """
    Extract readable text from raw HTML using regex tag stripping.
    Used as a fallback when Playwright returns < 200 chars.
    """
    # Remove scripts, styles, and noscript blocks entirely
    html = re.sub(
        r"<(script|style|noscript|head)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I
    )
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    text = (
        text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
            .replace("&mdash;", "—").replace("&ndash;", "–").replace("&hellip;", "…")
    )
    return clean_text(text)


# ── NLP helpers ────────────────────────────────────────────────────────────────

def _is_lorem_ipsum(text: str) -> bool:
    latin_words = {
        "lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing",
        "elit", "sed", "eiusmod", "tempor", "incididunt", "labore", "dolore",
        "magna", "aliqua", "enim", "minim", "veniam", "quis", "nostrud",
        "exercitation", "ullamco", "laboris", "nisi", "aliquip", "commodo",
        "consequat", "duis", "aute", "irure", "reprehenderit", "voluptate",
        "velit", "esse", "cillum", "fugiat", "nulla", "pariatur", "excepteur",
        "sint", "occaecat", "cupidatat", "proident", "sunt", "culpa",
        "officia", "deserunt", "mollit", "anim", "etiam", "maecenas",
        "nullam", "donec", "curabitur", "ultricies", "faucibus", "fringilla",
        "blandit", "semper", "libero", "pellentesque", "habitant", "morbi",
        "tristique", "senectus", "netus", "malesuada", "fames", "turpis",
        "egestas", "praesent", "cursus", "viverra", "suspendisse",
        "potenti", "accumsan", "lacus", "vestibulum", "ante", "primis",
        "orci", "luctus", "posuere", "cubilia", "curae", "proin",
        "sapien", "venenatis", "lacinia", "feugiat", "vulputate", "tortor",
        "dignissim", "convallis", "aenean", "pretium", "ligula", "porttitor",
        "rhoncus", "phasellus", "augue", "sollicitudin",
        "facilisis", "eleifend", "quam", "dui", "leo", "vivamus",
        "fermentum", "nibh", "neque", "imperdiet", "tincidunt", "condimentum",
        "tempus", "integer", "bibendum", "arcu", "massa", "nunc",
        "pulvinar", "mattis", "placerat", "diam", "euismod", "quisque",
        "rutrum", "dictum", "nam", "eget", "hendrerit", "justo",
    }
    words = text.lower().split()
    if not words:
        return True
    latin_count = sum(1 for w in words if w.strip(".,;:!?()") in latin_words)
    return latin_count / len(words) > 0.4


def extract_keywords_spacy(texts: list[str], top_n: int = 30) -> list[str]:
    if not NLP_AVAILABLE or not texts:
        return extract_keywords_simple(texts, top_n)

    clean_texts = [t for t in texts if not _is_lorem_ipsum(t)]
    if not clean_texts:
        clean_texts = texts

    combined = " ".join(clean_texts[:10])[:50000]
    doc = nlp(combined)

    _det = {"the", "a", "an", "our", "your", "their", "this", "that",
            "its", "my", "we", "all", "each", "every", "more"}
    phrases = [chunk.text.lower().strip() for chunk in doc.noun_chunks
               if 1 <= len(chunk.text.split()) <= 3
               and chunk.text.split()[0].lower() not in _det]
    entities = [ent.text.lower().strip() for ent in doc.ents
                if ent.label_ not in ("DATE", "TIME", "CARDINAL", "ORDINAL")]

    stopwords = {
        "the", "a", "an", "this", "that", "our", "your", "we", "they",
        "it", "its", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "need",
        "more", "most", "also", "just", "very", "all", "any", "both",
        "each", "few", "other", "some", "such", "than", "too",
        "one", "two", "three", "way", "ways",
        "view", "skip", "content", "click", "explore", "read", "learn",
        "find", "know", "back", "next", "prev", "menu", "home", "page",
        "contact", "about", "work", "more", "less", "show", "hide",
        "submit", "send", "close", "open", "link", "button",
    }
    latin_junk = {
        "lorem", "ipsum", "dolor", "amet", "consectetur", "adipiscing",
        "elit", "etiam", "maecenas", "nullam", "donec", "curabitur",
        "ultricies", "faucibus", "fringilla", "blandit", "semper", "libero",
        "pellentesque", "habitant", "morbi", "tristique", "senectus",
        "netus", "malesuada", "fames", "turpis", "egestas", "praesent",
        "cursus", "viverra", "suspendisse", "potenti", "accumsan", "lacus",
        "vestibulum", "ante", "primis", "orci", "luctus", "posuere",
        "cubilia", "curae", "proin", "sapien", "venenatis", "lacinia",
        "feugiat", "vulputate", "tortor", "dignissim", "convallis",
        "aenean", "pretium", "ligula", "porttitor", "rhoncus", "phasellus",
        "augue", "sollicitudin", "facilisis", "eleifend", "quam", "dui",
        "leo", "vivamus", "fermentum", "nibh", "neque", "imperdiet",
        "tincidunt", "condimentum", "tempus", "integer", "bibendum",
        "arcu", "nunc", "pulvinar", "mattis", "placerat", "diam",
        "euismod", "quisque", "rutrum", "dictum", "nam", "eget",
        "hendrerit", "justo", "nulla", "quis",
    }

    counts = Counter(phrases + entities)
    results = []
    for term, _ in counts.most_common(top_n * 3):
        if term in stopwords or len(term) <= 3:
            continue
        if term.startswith(("http", "www")):
            continue
        if set(term.split()) & latin_junk:
            continue
        results.append(term)
        if len(results) >= top_n:
            break
    return results


def extract_keywords_simple(texts: list[str], top_n: int = 30) -> list[str]:
    clean_texts = [t for t in texts if not _is_lorem_ipsum(t)]
    if not clean_texts:
        clean_texts = texts
    combined = " ".join(clean_texts).lower()
    words = re.findall(r"\b[a-z]{4,}\b", combined)
    stopwords = {
        "this", "that", "with", "from", "have", "been", "will", "they",
        "their", "what", "when", "where", "which", "your", "about",
        "more", "also", "into", "over", "after", "some", "than", "then",
        "these", "those", "such", "each", "both", "many", "most", "much",
        "view", "skip", "content", "click", "explore", "read", "learn",
        "find", "know", "back", "next", "prev", "menu", "home", "page",
        "contact", "submit", "send", "close", "open", "link",
    }
    latin_junk = {
        "lorem", "ipsum", "dolor", "amet", "consectetur", "adipiscing",
        "elit", "etiam", "maecenas", "nullam", "donec", "curabitur",
        "ultricies", "faucibus", "fringilla", "blandit", "semper", "libero",
        "pellentesque", "habitant", "morbi", "tristique", "senectus",
        "netus", "malesuada", "fames", "turpis", "egestas", "praesent",
        "cursus", "viverra", "suspendisse", "potenti", "accumsan", "lacus",
        "vestibulum", "ante", "primis", "luctus", "posuere", "cubilia",
        "curae", "proin", "sapien", "venenatis", "lacinia", "feugiat",
        "vulputate", "tortor", "dignissim", "convallis", "aenean",
        "pretium", "ligula", "porttitor", "rhoncus", "phasellus", "augue",
        "sollicitudin", "facilisis", "eleifend", "quam", "vivamus",
        "fermentum", "nibh", "neque", "imperdiet", "tincidunt",
        "condimentum", "tempus", "integer", "bibendum", "arcu", "nunc",
        "pulvinar", "mattis", "placerat", "diam", "euismod", "quisque",
        "rutrum", "dictum", "eget", "hendrerit", "justo", "nulla", "quis",
        "orci", "duis",
    }
    reject = stopwords | latin_junk
    counts = Counter(w for w in words if w not in reject)
    return [w for w, _ in counts.most_common(top_n)]


def infer_tone(texts: list[str]) -> tuple[list[str], str, int, bool]:
    combined = " ".join(texts)
    sentences = re.split(r"[.!?]+", combined)
    sentences = [s.strip() for s in sentences if len(s.split()) > 5]

    if not sentences:
        return ["professional"], "", 15, True

    avg_len = int(sum(len(s.split()) for s in sentences) / max(len(sentences), 1))
    fp_count = sum(1 for s in sentences if re.search(r"\bwe\b|\bour\b|\bus\b", s, re.I))
    uses_first_person = fp_count > len(sentences) * 0.3

    tone = []
    if avg_len < 14:
        tone.append("concise")
    elif avg_len > 22:
        tone.append("detailed")

    technical_terms = re.findall(
        r"\b(ROI|strategy|solution|architecture|framework|methodology|"
        r"innovation|expertise|premium|bespoke|crafted|curated|luxury|"
        r"affordable|budget|transform|reimagine|elevate)\b",
        combined,
        re.I,
    )
    if any(t.lower() in ("premium", "bespoke", "luxury", "curated", "crafted") for t in technical_terms):
        tone.append("premium")
    if any(t.lower() in ("affordable", "budget") for t in technical_terms):
        tone.append("value-focused")
    if any(t.lower() in ("transform", "reimagine", "elevate", "innovation") for t in technical_terms):
        tone.append("aspirational")
    if not tone:
        tone = ["professional", "helpful"]

    nav_junk_starts = ("skip", "cookie", "accept", "menu", "home", "toggle",
                       "close", "search", "login", "sign", "privacy", "navigation")
    good_samples = [
        s for s in sentences
        if 10 < len(s.split()) < 30
        and not s.lower().startswith(nav_junk_starts)
        and not _is_lorem_ipsum(s)
    ]
    sample = good_samples[0] if good_samples else (sentences[0] if sentences else "")
    return tone, sample.strip(), avg_len, uses_first_person


def extract_usps(texts: list[str]) -> list[str]:
    """
    Extract unique selling points from page text.
    Two-pass approach:
      Pass 1 — regex patterns for explicit USP claims
      Pass 2 — short impactful sentences that read like value propositions
    """
    patterns = [
        # Numbers + achievement
        r"(\d+\+?\s+years?\s+(?:of\s+)?(?:experience|expertise|practice)[^.!?]*[.!?])",
        r"(over\s+\d+\s+(?:projects?|clients?|homes?|spaces?|families|brands?)[^.!?]*[.!?])",
        r"(\d+\+?\s+(?:happy\s+)?(?:clients?|customers?|homes?|projects?|brands?)[^.!?]*[.!?])",
        r"(trusted\s+by[^.!?]*[.!?])",
        # Quality / delivery claims
        r"(end[\-\s]to[\-\s]end[^.!?]*[.!?])",
        r"(turnkey[^.!?]*[.!?])",
        r"(single[\-\s]point[^.!?]*[.!?])",
        r"(in[\-\s]house[^.!?]*[.!?])",
        r"(custom[^.!?]{5,60}[.!?])",
        r"(bespoke[^.!?]{5,60}[.!?])",
        r"(on[\-\s]time[^.!?]*[.!?])",
        r"(on[\-\s]budget[^.!?]*[.!?])",
        r"(no hidden[^.!?]*[.!?])",
        r"(transparent[^.!?]*(?:pric|cost|fee)[^.!?]*[.!?])",
        r"(warranty[^.!?]*[.!?])",
        r"(guarantee[^.!?]*[.!?])",
        # Awards / certifications
        r"(award[^.!?]*[.!?])",
        r"(certified[^.!?]*[.!?])",
        r"(ISO[^.!?]*[.!?])",
        r"(accredited[^.!?]*[.!?])",
        # Uniqueness claims
        r"(only\s+(?:company|firm|studio|team|agency)[^.!?]*[.!?])",
        r"(first\s+(?:in|to)[^.!?]*[.!?])",
        # Team / expertise
        r"(team\s+of\s+(?:experienced|expert|skilled|certified)[^.!?]*[.!?])",
        r"(experienced\s+(?:team|designers?|architects?|professionals?)[^.!?]*[.!?])",
        r"(dedicated\s+(?:team|designers?|project)[^.!?]*[.!?])",
        # Process strengths
        r"(from\s+concept\s+to[^.!?]*[.!?])",
        r"(from\s+design\s+to[^.!?]*[.!?])",
        r"(from\s+(?:idea|vision)\s+to[^.!?]*[.!?])",
        r"(zero\s+compromise[^.!?]*[.!?])",
        r"(no\s+compromise[^.!?]*[.!?])",
        r"(attention\s+to\s+detail[^.!?]*[.!?])",
        r"(personalised?[^.!?]*(?:approach|service|solution)[^.!?]*[.!?])",
        r"(tailored[^.!?]*(?:approach|service|solution|design)[^.!?]*[.!?])",
    ]

    usps: list[str] = []
    seen: set[str] = set()
    combined = " ".join(t for t in texts if not _is_lorem_ipsum(t))

    # Pass 1 — explicit pattern matches
    for pattern in patterns:
        for m in re.findall(pattern, combined, re.I):
            usp = m.strip()
            key = usp.lower()[:50]
            if 8 < len(usp) < 160 and key not in seen:
                seen.add(key)
                usps.append(usp)
        if len(usps) >= 6:
            break

    # Pass 2 — short punchy sentences from about/homepage that read like value props
    if len(usps) < 3:
        _usp_triggers = re.compile(
            r"\b(we\s+(?:offer|provide|deliver|specialize|ensure|believe|design|create|build)|"
            r"our\s+(?:team|approach|process|mission|vision|expertise|commitment|promise|goal|philosophy)|"
            r"(?:expert|skilled|experienced|passionate|dedicated|certified|professional)\s+\w+|"
            r"quality|craftsmanship|excellence|luxury|premium|bespoke|affordable|transparent|"
            r"hassle[\-\s]free|stress[\-\s]free|end[\-\s]to[\-\s]end|turnkey|in[\-\s]house|"
            r"custom|personalised?|tailored|warranty|guarantee|award|certified)\b",
            re.I,
        )
        sentences = re.split(r"[.!?\n]+", combined)
        for s in sentences:
            s = s.strip()
            words = s.split()
            if len(words) < 5 or len(words) > 30:
                continue
            if not _usp_triggers.search(s):
                continue
            if _is_lorem_ipsum(s):
                continue
            key = s.lower()[:50]
            if key in seen:
                continue
            # Skip obvious nav/UI text
            if re.match(r"^(skip|menu|home|contact|about|login|toggle|cookie|accept)", s, re.I):
                continue
            seen.add(key)
            usps.append(s)
            if len(usps) >= 6:
                break

    return usps[:6]


# ── Core scraping function ─────────────────────────────────────────────────────

async def extract_company_dna(base_url: str) -> CompanyDNA:
    base_url = base_url.rstrip("/")
    domain   = urlparse(base_url).netloc

    dna = CompanyDNA(domain=domain)
    print(f"\n[DNA] Extracting company profile from: {base_url}")

    page_contents: dict[str, str] = {}
    article_titles: list[str]     = []
    article_texts:  list[str]     = []
    portfolio_items: list[dict]   = []

    # Accumulated JSON-LD data (merged across all scraped pages)
    jld_services:  list[str] = []
    jld_articles:  list[str] = []
    jld_locations: list[str] = []

    scraped_service_headings: list[str] = []

    # ── Step 0: Sitemap ────────────────────────────────────────────────────────
    sitemap_urls = await fetch_sitemap(base_url, domain)
    sitemap_by_section: dict[str, list[str]] = defaultdict(list)
    for url in sitemap_urls:
        sec = classify_path(urlparse(url).path)
        if sec:
            sitemap_by_section[sec].append(url)

    # ── Step 1: BFS URL discovery (no browser, httpx only) ────────────────────
    bfs_urls = await _bfs_discover_urls(base_url, domain, max_pages=60, max_depth=3)

    # Mine JSON-LD from homepage raw HTML before opening a browser
    try:
        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"},
        ) as hc:
            hp_resp = await hc.get(base_url)
            if hp_resp.status_code < 400:
                jld = _mine_json_ld(hp_resp.text)
                jld_services.extend(jld["services"])
                jld_articles.extend(jld["article_titles"])
                jld_locations.extend(jld["locations"])
                if jld["name"] and not dna.name:
                    dna.name = jld["name"]
                if jld["description"] and not dna.description:
                    dna.description = jld["description"][:300]
                print(
                    f"[DNA] JSON-LD (homepage): {len(jld['services'])} services, "
                    f"{len(jld['article_titles'])} articles, "
                    f"{len(jld['locations'])} locations"
                )
    except Exception as e:
        print(f"[DNA] JSON-LD pre-fetch skipped: {e}")

    # ── Step 2: Build section candidates ──────────────────────────────────────
    section_candidates: dict[str, list[str]] = defaultdict(list)
    queued: set[str] = set()

    def queue_url(section: str, url: str) -> None:
        u = _norm_url(url)
        if u and u not in queued and _is_content_url(u):
            queued.add(u)
            section_candidates[section].append(u)

    # Priority 1: sitemap
    for sec, urls in sitemap_by_section.items():
        for url in urls:
            queue_url(sec, url)

    # Priority 2: BFS — classify every discovered URL
    bfs_by_seg: dict[str, list[str]] = defaultdict(list)
    for url in bfs_urls:
        path = urlparse(url).path
        sec  = classify_path(path)
        if sec:
            queue_url(sec, url)
        seg = path.strip("/").split("/")[0].lower() if path.strip("/") else ""
        if seg and seg not in SKIP_SEGMENTS:
            bfs_by_seg[seg].append(url)

    # Fix 7 — Dynamic section detection:
    # Any segment with 3+ BFS children that has slug-like sub-URLs → auto-classify
    for seg, urls in bfs_by_seg.items():
        if classify_path(seg) is not None:
            continue  # already handled
        if len(urls) < 3:
            continue
        slug_like = sum(
            1 for u in urls
            if len(urlparse(u).path.strip("/").split("/")) >= 2
            and "-" in urlparse(u).path.split("/")[-1]
        )
        if slug_like >= 2:
            print(f"[DNA] Dynamic blog section: /{seg}/ ({len(urls)} URLs, {slug_like} slug-like)")
            for url in urls:
                queue_url("blog", url)
        else:
            print(f"[DNA] Dynamic portfolio section: /{seg}/ ({len(urls)} URLs)")
            for url in urls:
                queue_url("portfolio", url)

    # Priority 3: hardcoded fallbacks
    FALLBACKS: dict[str, list[str]] = {
        "about":     ["/about", "/about-us", "/our-story", "/who-we-are", "/company", "/team"],
        "services":  ["/services", "/what-we-do", "/solutions", "/offerings", "/capabilities"],
        "portfolio": ["/portfolio", "/projects", "/case-studies", "/gallery", "/work", "/our-work"],
        "blog":      ["/blog", "/insights", "/articles", "/news", "/resources", "/stories",
                      "/journal", "/updates", "/thinking", "/posts", "/guides", "/tutorials",
                      "/tips", "/knowledge", "/media", "/press", "/publications", "/lab",
                      "/craft", "/notes", "/thoughts", "/writings"],
        "contact":   ["/contact", "/contact-us", "/get-in-touch"],
    }
    for sec, paths in FALLBACKS.items():
        for path in paths:
            queue_url(sec, urljoin(base_url, path))

    print(
        "[DNA] Section candidates: "
        + ", ".join(f"{s}:{len(v)}" for s, v in section_candidates.items())
    )

    # ── Step 3: Playwright — full-render scraping ──────────────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        async def _route_handler(route):
            if route.request.resource_type in ("image", "media", "font"):
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", _route_handler)
        page = await context.new_page()

        # ── Inner helpers ──────────────────────────────────────────────────

        async def _html_fallback(url: str) -> str:
            """Fetch raw HTML via httpx and extract readable text."""
            try:
                async with httpx.AsyncClient(
                    timeout=10,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"},
                ) as hc:
                    r = await hc.get(url)
                    if r.status_code < 400:
                        jld = _mine_json_ld(r.text)
                        jld_services.extend(jld["services"])
                        jld_articles.extend(jld["article_titles"])
                        jld_locations.extend(jld["locations"])
                        txt = _extract_html_text(r.text)
                        print(f"[DNA]   HTML fallback: {len(txt)} chars")
                        return txt
            except Exception:
                pass
            return ""

        async def scrape(url: str, label: str = "") -> str:
            """
            Full-featured page scraper implementing Fixes 1, 3, 4, 5, 8.

            1. Navigate: try networkidle, fall back to domcontentloaded
            2. Poll until body text > 500 chars (up to 8 s)
            3. Scroll to trigger lazy loading
            4. Expand accordions / <details> / collapsed Bootstrap panels
            5. Click tab panels one-by-one (up to 5)
            6. Click Load-More buttons (up to 3 times)
            7. Extract innerText after removing nav/footer/cookie noise
            8. Pierce Shadow DOM if text is still thin (< 300 chars)
            9. Append same-domain iframe text
            10. Fallback to raw-HTML httpx if still < 200 chars
            11. Mine JSON-LD from page source
            """
            try:
                await asyncio.sleep(0.6)

                # 1. Navigate — Fix 1
                resp = None
                try:
                    resp = await page.goto(url, wait_until="networkidle", timeout=20000)
                except Exception:
                    try:
                        resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    except Exception as e:
                        print(f"[DNA] Navigation failed {url}: {e}")
                        return await _html_fallback(url)

                if not resp or resp.status >= 400:
                    return ""

                # 2. Poll until body has content — Fix 1
                deadline = asyncio.get_running_loop().time() + 8.0
                while asyncio.get_running_loop().time() < deadline:
                    body_len = await page.evaluate(
                        "() => document.body ? document.body.innerText.length : 0"
                    )
                    if body_len > 500:
                        break
                    await asyncio.sleep(0.3)

                # 3. Scroll to trigger lazy loading
                for frac in (0.33, 0.66, 1.0):
                    await page.evaluate(
                        f"window.scrollTo(0, document.body.scrollHeight * {frac})"
                    )
                    await asyncio.sleep(0.35)

                # 4. Expand accordions / details / collapsed panels — Fix 5
                await page.evaluate("""() => {
                    document.querySelectorAll('details').forEach(d => { d.open = true; });
                    [
                        '[aria-expanded="false"]',
                        '.accordion-button.collapsed',
                        '[data-bs-toggle="collapse"]',
                        '[data-toggle="collapse"]',
                    ].forEach(sel => {
                        try {
                            document.querySelectorAll(sel).forEach(el => {
                                try { el.click(); } catch(e) {}
                            });
                        } catch(e) {}
                    });
                }""")
                await asyncio.sleep(1.5)   # let CSS transitions finish

                # 5. Click tab panels one by one — Fix 5
                try:
                    tabs = await page.query_selector_all(
                        '[role="tab"]:not([aria-selected="true"])'
                    )
                    for tab in tabs[:5]:
                        try:
                            await tab.click(timeout=3000)
                            await asyncio.sleep(0.8)
                        except Exception:
                            pass
                except Exception:
                    pass

                # 6. Click Load-More buttons (up to 3 times) — Fix 5
                for _ in range(3):
                    try:
                        btn = await page.query_selector(
                            ':text("load more"), :text("see more"), :text("view more"), :text("show more")'
                        )
                        if not btn:
                            break
                        await btn.click(timeout=3000)
                        await asyncio.sleep(1.5)
                    except Exception:
                        break

                # Final scroll after all interactions
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.3)

                # 7. Extract innerText, removing noise
                text = await page.evaluate("""() => {
                    [
                        'nav', 'footer', 'header', 'script', 'style', 'noscript',
                        '.cookie', '#cookie',
                        '[class*="cookie"]', '[id*="cookie"]',
                        '[class*="popup"]',  '[class*="modal"]',
                        '[class*="banner"]', '[class*="overlay"]',
                    ].forEach(sel => {
                        try {
                            document.querySelectorAll(sel).forEach(el => el.remove());
                        } catch(e) {}
                    });
                    return document.body ? document.body.innerText : '';
                }""")

                # 8. Shadow DOM pierce — Fix 3
                if len(text) < 300:
                    try:
                        shadow = await page.evaluate("""() => {
                            function pierceText(root) {
                                const parts = [];
                                try {
                                    const walker = document.createTreeWalker(
                                        root,
                                        NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT,
                                        null
                                    );
                                    let node;
                                    while ((node = walker.nextNode())) {
                                        if (node.nodeType === 3) {
                                            const t = (node.textContent || '').trim();
                                            if (t) parts.push(t);
                                        } else if (node.nodeType === 1 && node.shadowRoot) {
                                            parts.push(pierceText(node.shadowRoot));
                                        }
                                    }
                                } catch(e) {}
                                return parts.join(' ');
                            }
                            return pierceText(document.body);
                        }""")
                        if shadow and len(shadow) > len(text):
                            text = shadow
                            print(f"[DNA]   Shadow DOM pierce: {len(text)} chars")
                    except Exception:
                        pass

                # 9. Same-domain iframe content — Fix 4
                try:
                    for frame in page.frames[1:]:
                        try:
                            frame_url = frame.url or ""
                            if frame_url and _is_same_domain(frame_url, domain):
                                f_text = await frame.evaluate(
                                    "() => document.body ? document.body.innerText : ''"
                                )
                                if f_text and len(f_text) > 50:
                                    text += "\n" + f_text
                        except Exception:
                            pass
                except Exception:
                    pass

                text = clean_text(text)

                # 10. HTML fallback — Fix 8
                if len(text) < 200:
                    fb = await _html_fallback(url)
                    if len(fb) > len(text):
                        text = fb

                # 11. Mine JSON-LD from this page's source
                try:
                    page_html = await page.content()
                    jld = _mine_json_ld(page_html)
                    jld_services.extend(jld["services"])
                    jld_articles.extend(jld["article_titles"])
                    jld_locations.extend(jld["locations"])
                except Exception:
                    pass

                return text

            except Exception as e:
                print(f"[DNA] scrape() error {url}: {e}")
                return await _html_fallback(url)

        async def get_page_links() -> list[dict]:
            try:
                return await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => ({href: e.href||'', text:(e.innerText||'').trim()}))",
                )
            except Exception:
                return []

        async def extract_service_headings() -> list[str]:
            """
            Extract service names directly from heading / accordion / tab labels
            on the currently loaded page.
            """
            try:
                return await page.evaluate("""() => {
                    const results = [];
                    const seen    = new Set();
                    const skipWords = new Set([
                        'menu','nav','cookie','toggle','close','search','login',
                        'sign','home','contact','about','skip','back','next',
                        'prev','submit','send','privacy','terms','loading',
                        'read more','learn more','view more','see more','get started',
                        'our services','what we do','how we work','why choose us',
                    ]);
                    function add(raw) {
                        const t = (raw || '').replace(/\\s+/g, ' ').trim();
                        if (t.length < 2 || t.length > 100) return;
                        const lower = t.toLowerCase();
                        if (skipWords.has(lower)) return;
                        if (lower.startsWith('skip ') || lower.startsWith('cookie')) return;
                        if (!seen.has(lower)) { seen.add(lower); results.push(t); }
                    }
                    // Headings inside service/accordion containers
                    [
                        '[class*="service"]','[id*="service"]',
                        '[class*="accordion"]','[id*="accordion"]',
                        '[class*="offering"]','[class*="capability"]',
                        '[class*="solution"]','[class*="tab-"]',
                        '[class*="feature"]','[class*="card"]',
                        '[class*="panel"]','[class*="box"]',
                        '.services','#services','.offerings','.solutions',
                        '[class*="what-we"]','[class*="whatwe"]',
                    ].forEach(sel => {
                        document.querySelectorAll(sel).forEach(container => {
                            container.querySelectorAll(
                                'h1,h2,h3,h4,h5,dt,summary,' +
                                '.title,.heading,[class*="title"],[class*="heading"],[class*="label"]'
                            ).forEach(el => add(el.innerText || el.textContent || ''));
                        });
                    });
                    // <summary> and accordion buttons globally
                    document.querySelectorAll(
                        'summary,.accordion-button,[class*="accordion-title"],' +
                        '[class*="panel-title"],[class*="tab-title"]'
                    ).forEach(el => add(el.innerText || el.textContent || ''));
                    // Short h3/h4 (likely service labels)
                    document.querySelectorAll('h3,h4').forEach(el => {
                        const t = (el.innerText || '').trim();
                        if (t.length > 2 && t.length < 80 && t.split(/\\s+/).length <= 8)
                            add(t);
                    });
                    return results.slice(0, 30);
                }""")
            except Exception:
                return []

        # ── Step 3a: Homepage ──────────────────────────────────────────────────
        print("[DNA] Scraping homepage...")
        homepage_text = await scrape(base_url, "homepage")
        dna.homepage_text = homepage_text[:3000]
        page_contents["homepage"] = homepage_text

        # Brand name (skip if already set by JSON-LD)
        if not dna.name:
            try:
                brand_name = await page.evaluate("""() => {
                    const ogSite = document.querySelector('meta[property="og:site_name"]');
                    if (ogSite && ogSite.content.trim()) return ogSite.content.trim();

                    const schemas = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const s of schemas) {
                        try {
                            const d = JSON.parse(s.textContent);
                            const items = Array.isArray(d) ? d : [d];
                            for (const item of items) {
                                if ((item['@type'] === 'Organization' || item['@type'] === 'LocalBusiness')
                                    && item.name) return item.name;
                                if (item.publisher && item.publisher.name) return item.publisher.name;
                            }
                        } catch(e) {}
                    }
                    for (const sel of [
                        'header img[alt]', '.logo img[alt]', '#logo img[alt]',
                        'a[class*="logo"] img[alt]', 'a[href="/"] img[alt]',
                        'img[class*="logo"][alt]', 'img[id*="logo"][alt]',
                        'nav img[alt]', '.navbar img[alt]', '.header img[alt]',
                    ]) {
                        const img = document.querySelector(sel);
                        if (img && img.alt && img.alt.trim().length > 1
                            && img.alt.trim().split(/\\s+/).length <= 5
                            && !img.alt.toLowerCase().includes('logo')
                            && img.alt.trim().length < 50)
                            return img.alt.trim();
                    }
                    for (const sel of [
                        'header .logo','header .brand','header .site-name',
                        '.navbar-brand','.site-title','#site-name',
                        'header h1','header h2','.logo-text','.brand-name',
                    ]) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const txt = el.innerText.trim();
                            if (txt && txt.split(/\\s+/).length <= 5 && txt.length < 60) return txt;
                        }
                    }
                    const title = document.title || '';
                    const parts = title.split(/[|\\u2013\\u2014\\xb7:\\u00bb]/).map(s => s.trim()).filter(Boolean);
                    const seoWords = ['best','top','leading','premier','#1','no.1',
                                      'affordable','cheap','data-driven','performance',
                                      'growth','agency','expert','specialist'];
                    function cleanSeg(s) {
                        return s.replace(/\\.(com|co|in|net|io|org|agency|studio|ai)(\\.[a-z]{2})?$/i,'').trim();
                    }
                    for (const part of parts) {
                        let candidate = /\\.[a-z]{2,6}(\\.[a-z]{2})?$/i.test(part)
                            ? cleanSeg(part) : part;
                        const words = candidate.split(/\\s+/);
                        const isSEO = words.length > 5 || seoWords.some(w => candidate.toLowerCase().includes(w));
                        if (!isSEO && words.length >= 1 && words.length <= 5 && candidate.length > 2)
                            return candidate;
                    }
                    if (parts.length > 0) {
                        const shortest = parts.reduce((a,b) => a.length <= b.length ? a : b);
                        const c = cleanSeg(shortest);
                        if (c.length > 2 && c.split(/\\s+/).length <= 5) return c;
                    }
                    return '';
                }""")
                if brand_name:
                    name = brand_name.strip()
                    if name and " " not in name and name.islower():
                        name = name.title()
                    if len(name.split()) > 6 or len(name) > 60:
                        name = domain.replace("www.", "").split(".")[0].title()
                    dna.name = name
            except Exception:
                pass

        if not dna.name:
            dna.name = domain.replace("www.", "").split(".")[0].title()

        # Meta description (skip if JSON-LD already provided it)
        if not dna.description:
            try:
                meta_desc = await page.evaluate("""() => {
                    const og = document.querySelector('meta[property="og:description"]');
                    if (og && og.content.trim()) return og.content.trim();
                    const meta = document.querySelector('meta[name="description"]');
                    if (meta && meta.content.trim()) return meta.content.trim();
                    return '';
                }""")
                if meta_desc:
                    dna.description = meta_desc[:300]
            except Exception:
                pass

        # ── Step 3b: Scrape key sections ───────────────────────────────────────
        for section in ["about", "services", "portfolio", "blog", "contact"]:
            candidates = section_candidates.get(section, [])
            listing_first = sorted(
                [u for u in candidates if is_listing_url(urlparse(u).path)],
                key=lambda u: len(urlparse(u).path),
            )
            for url in listing_first[:8]:
                print(f"[DNA] Trying {section}: {url}")
                text = await scrape(url, section)
                if len(text) > 200:
                    page_contents[section] = text
                    print(f"[DNA]   OK {len(text)} chars")
                    if section == "services":
                        scraped_service_headings = await extract_service_headings()
                        print(f"[DNA]   Service headings: {scraped_service_headings[:6]}")
                    break

        # ── Step 4: Discover articles ──────────────────────────────────────────
        discovered_articles: list[dict] = []

        # 4a: Blog + portfolio listing pages
        _UI_TEXT = re.compile(
            r"^(skip|menu|home|contact|about|login|sign\s|toggle|cookie|accept|"
            r"privacy|terms|close|search|next|prev|back|more|all|load|see\s|"
            r"view\s|read\s|get\s|our\s+work$|our\s+story$|who\s+we|what\s+we)",
            re.I,
        )
        for _als in ["blog", "portfolio"]:
            if not page_contents.get(_als):
                continue
            listing_url = next(
                (u for u in section_candidates.get(_als, [])
                 if is_listing_url(urlparse(u).path)),
                None,
            )
            if not listing_url:
                continue
            # The listing page's path segment (e.g. "portfolio") used to anchor child links
            listing_path_prefix = "/" + urlparse(listing_url).path.strip("/").split("/")[0]

            try:
                await page.goto(listing_url, wait_until="networkidle", timeout=15000)
            except Exception:
                try:
                    await page.goto(listing_url, wait_until="domcontentloaded", timeout=12000)
                except Exception:
                    continue
            await asyncio.sleep(0.5)

            # Strip nav/header/footer BEFORE reading links so UI anchors are excluded
            try:
                await page.evaluate("""() => {
                    ['nav','header','footer','.site-header','.site-footer',
                     '.main-navigation','#site-navigation',
                     '[class*="nav"]','[class*="menu"]','[id*="menu"]',
                     '[class*="cookie"]','[class*="popup"]','[class*="modal"]',
                    ].forEach(sel => {
                        try {
                            document.querySelectorAll(sel).forEach(el => el.remove());
                        } catch(e) {}
                    });
                }""")
            except Exception:
                pass

            before_count = len(discovered_articles)
            for link in await get_page_links():
                href = _norm_url(link["href"])
                text = link["text"].strip()
                if not href or not text:
                    continue
                if not _is_same_domain(href, domain):
                    continue
                # Must be a deeper path under the listing section, not a nav/top-level link
                link_path = urlparse(href).path
                if not link_path.startswith(listing_path_prefix + "/"):
                    continue
                # Must be a genuine article slug (not the listing page itself)
                if _norm_url(href) == _norm_url(listing_url):
                    continue
                parts = link_path.strip("/").split("/")
                if len(parts) < 2 or len(parts[-1]) <= 3:
                    continue
                if _UI_TEXT.match(text):
                    continue
                # Reject purely uppercase shouting (nav labels like "OUR WORK")
                if text == text.upper() and len(text.split()) <= 4:
                    continue
                if len(text) < 6 or len(text) > 200:
                    continue
                if _is_lorem_ipsum(text):
                    continue
                discovered_articles.append({"href": href, "text": text, "section": _als})
            print(f"[DNA] {_als.title()} listing → {len(discovered_articles) - before_count} article links")

        # 4b: BFS-discovered article URLs from blog-classified segments
        if not discovered_articles:
            bfs_blog = [
                u for u in bfs_urls
                if classify_path(urlparse(u).path) in ("blog", "portfolio")
                and is_article_url(urlparse(u).path)
            ]
            for url in bfs_blog[:10]:
                slug  = urlparse(url).path.strip("/").split("/")[-1]
                title = slug.replace("-", " ").replace("_", " ").title()
                src   = classify_path(urlparse(url).path) or "blog"
                discovered_articles.append({"href": url, "text": title, "section": src})
            if bfs_blog:
                print(f"[DNA] BFS blog/portfolio articles: {len(bfs_blog)} URLs")

        # 4c: Sitemap-based article discovery
        if not discovered_articles and sitemap_urls:
            seg_counts: Counter = Counter()
            for url in sitemap_urls:
                if not _is_same_domain(url, domain):
                    continue
                parts = urlparse(url).path.strip("/").split("/")
                if len(parts) >= 2:
                    seg_counts[parts[0].lower()] += 1
            content_segs = [
                seg for seg, cnt in seg_counts.most_common(10)
                if cnt >= 3 and seg not in SKIP_SEGMENTS
            ]
            for seg in content_segs[:3]:
                art_urls = [
                    u for u in sitemap_urls
                    if _is_same_domain(u, domain)
                    and urlparse(u).path.strip("/").split("/")[0].lower() == seg
                    and is_article_url(urlparse(u).path)
                ]
                if len(art_urls) >= 2:
                    for url in art_urls[:8]:
                        slug  = urlparse(url).path.strip("/").split("/")[-1]
                        title = slug.replace("-", " ").replace("_", " ").title()
                        discovered_articles.append({"href": url, "text": title, "section": "blog"})
                    print(f"[DNA] Sitemap /{seg}/ → {len(art_urls)} articles")
                    break

        # 4d: BFS dynamic sections as article sources (last resort)
        if not discovered_articles:
            for seg, urls in bfs_by_seg.items():
                if len(urls) < 3:
                    continue
                slug_like = [
                    u for u in urls
                    if len(urlparse(u).path.strip("/").split("/")) >= 2
                    and "-" in urlparse(u).path.split("/")[-1]
                ]
                if len(slug_like) >= 2:
                    for url in slug_like[:8]:
                        slug  = urlparse(url).path.strip("/").split("/")[-1]
                        title = slug.replace("-", " ").title()
                        discovered_articles.append({"href": url, "text": title, "section": "blog"})
                    print(f"[DNA] BFS dynamic /{seg}/ → {len(slug_like)} article-like URLs")
                    break

        # ── Step 5: Scrape top 5 articles ─────────────────────────────────────
        seen_hrefs: set[str] = set()
        unique_articles: list[dict] = []
        _connectors = {"a", "an", "the", "of", "in", "for", "to", "and", "or",
                       "but", "by", "at", "on", "with", "how", "why", "what",
                       "when", "which"}

        for art in discovered_articles:
            href = _norm_url(art["href"])
            text = art["text"].strip()
            src  = art.get("section", "blog")

            if any(href.startswith(p) for p in ("mailto:", "tel:", "javascript:")):
                continue
            if "@" in text:
                continue
            if href in seen_hrefs or len(text) < 8 or not is_article_url(urlparse(href).path):
                continue
            # Reject obvious UI/nav text (safety net for BFS/sitemap fallback paths)
            if _UI_TEXT.match(text):
                continue
            # Reject all-uppercase short strings (nav labels like "OUR WORK")
            if text == text.upper() and len(text.split()) <= 5:
                continue
            # Portfolio-sourced: reject if it looks like a bare company/project name
            if src == "portfolio":
                words = text.split()
                if len(words) < 3:
                    continue
                if not any(w.lower() in _connectors for w in words):
                    continue

            seen_hrefs.add(href)
            unique_articles.append({"href": href, "text": text})

        print(f"[DNA] {len(unique_articles)} unique article URLs to read")
        for link in unique_articles[:5]:
            print(f"[DNA] Reading article: {link['text'][:65]}")
            article_titles.append(link["text"].strip())
            art_text = await scrape(link["href"], "article")
            if art_text:
                article_texts.append(art_text[:2000])

        # ── Step 6: Portfolio items ────────────────────────────────────────────
        portfolio_text = page_contents.get("portfolio", "")
        if portfolio_text:
            lines = [l.strip() for l in portfolio_text.split("\n")
                     if 10 < len(l.strip()) < 150]
            for i, line in enumerate(lines[:20]):
                if any(w in line.lower() for w in [
                    "project", "home", "office", "apartment", "villa",
                    "bedroom", "kitchen", "living", "commercial", "sqft",
                    "designed", "delivered", "completed", "client",
                ]):
                    desc = lines[i + 1] if i + 1 < len(lines) else ""
                    portfolio_items.append({"title": line, "description": desc})

        await browser.close()

    # ── Build the DNA profile ──────────────────────────────────────────────────
    all_texts = [v for v in page_contents.values() if v and isinstance(v, str)]

    dna.tone_adjectives, dna.tone_sample, dna.avg_sentence_length, dna.uses_first_person = \
        infer_tone(all_texts)

    dna.top_keywords = extract_keywords_spacy(all_texts + article_texts, top_n=40)

    # Deduplicate accumulated JSON-LD data
    jld_services  = list(dict.fromkeys(s for s in jld_services if s))
    jld_articles  = list(dict.fromkeys(s for s in jld_articles if s))
    jld_locations = list(dict.fromkeys(s for s in jld_locations if s))

    # ── Locations ─────────────────────────────────────────────────────────────
    dna.locations = jld_locations[:6]
    if not dna.locations:
        combined_text = " ".join(all_texts[:3])
        loc_matches = re.findall(
            r"\b(New Delhi|Mumbai|Bangalore|Bengaluru|Chennai|Hyderabad|Pune|"
            r"Kolkata|Ahmedabad|Jaipur|Surat|Lucknow|Chandigarh|Noida|Gurgaon|"
            r"Gurugram|New York|London|Dubai|Singapore|Sydney|Toronto|Melbourne)\b",
            combined_text,
            re.I,
        )
        dna.locations = list(dict.fromkeys(m.title() for m in loc_matches))[:6]

    # ── Services — 4-tier priority ─────────────────────────────────────────────
    service_keywords = [
        # General
        "design", "install", "deliver", "service", "solution", "consult",
        "manage", "develop", "create", "provide", "strategy", "growth",
        "optimization", "audit", "training", "support", "analytics",
        # Interior / construction / architecture
        "interior", "furnish", "renovate", "renovation", "refurbish",
        "build", "construct", "modular", "kitchen", "bedroom", "living",
        "wardrobe", "ceiling", "flooring", "lighting", "residential",
        "commercial", "hospitality", "turnkey", "execution", "workmanship",
        "craftsmanship", "spaces", "aesthet", "functional", "luxury",
        "bespoke", "visualization", "visualisation", "rendering", "3d",
        "2d", "architectural", "landscape", "elevation", "layout",
        "planning", "project management", "procurement", "supervision",
        "remodel", "fit-out", "fitout", "fit out", "decor", "decoration",
        # Digital marketing
        "seo", "ppc", "google ads", "meta ads", "facebook ads", "social media",
        "content marketing", "email marketing", "lead generation", "conversion",
        "performance marketing", "branding", "web development", "paid ads",
        "advertising", "funnel", "campaign", "digital marketing", "sem",
        "search engine", "copywriting", "influencer", "automation",
        # Tech / SaaS
        "software", "saas", "platform", "api", "cloud", "app development",
        "machine learning", "data", "devops", "security", "integration",
        # Healthcare
        "health", "medical", "clinic", "telemedicine", "wellness",
        # Ecommerce
        "ecommerce", "shopify", "marketplace", "fulfillment",
        # Real estate
        "real estate", "property", "rental", "leasing",
    ]
    ui_noise = [
        "view more", "click", "skip", "instagram", "facebook", "youtube",
        "linkedin", "whatsapp", "pinterest", "explore", "connect on linkedin",
        "book a free", "view all", "view case", "meet the", "our vision",
    ]
    noise_phrases = [
        "our services", "we don't sell", "what we do", "how we work",
        "why choose us", "our approach", "our process", "get started",
        "learn more", "read more", "see all", "view all",
    ]

    def _is_service_name(text: str) -> bool:
        lower = text.lower()
        return (
            any(w in lower for w in service_keywords)
            and not any(u in lower for u in ui_noise)
            and not any(n in lower for n in noise_phrases)
            and not _is_lorem_ipsum(text)
        )

    def _add_services(candidates: list[str], limit: int = 12) -> None:
        seen: set[str] = set(s.lower() for s in dna.services)
        for s in candidates:
            s = s.strip()
            key = s.lower()
            if (len(s) > 1
                    and key not in seen
                    and not _is_lorem_ipsum(s)
                    and not any(n in key for n in noise_phrases + ui_noise)):
                seen.add(key)
                dna.services.append(s)
            if len(dna.services) >= limit:
                break

    # Tier 1: JSON-LD structured data (most reliable)
    if jld_services:
        _add_services(jld_services)
        print(f"[DNA]   Services from JSON-LD: {dna.services[:5]}")

    # Tier 2: Direct heading extraction from services page DOM
    if not dna.services and scraped_service_headings:
        _add_services(scraped_service_headings)
        print(f"[DNA]   Services from headings: {dna.services[:5]}")

    # Tier 3: Keyword-matched sentences from body text
    if not dna.services:
        services_raw = page_contents.get(
            "services",
            page_contents.get("homepage", "") + " " + page_contents.get("about", ""),
        )
        candidates = [
            chunk.strip()
            for chunk in re.split(r"[\n.!]", services_raw)
            if 4 < len(chunk.strip()) < 120
        ]
        _add_services([c for c in candidates if _is_service_name(c)])

    # Tier 4: Short capitalized phrases from homepage + services text
    if not dna.services:
        all_source = (
            page_contents.get("homepage", "")
            + "\n" + page_contents.get("services", "")
        )
        short_phrases = [
            line.strip()
            for line in all_source.split("\n")
            if 1 <= len(line.strip().split()) <= 8
            and 3 < len(line.strip()) < 80
            and _is_service_name(line.strip())
        ]
        _add_services(short_phrases, limit=10)

    # ── USPs, about, tagline ───────────────────────────────────────────────────
    # Prioritise about page text for USP extraction (richest source of value props)
    about_text_raw = page_contents.get("about", "")
    usp_texts = ([about_text_raw] if about_text_raw else []) + all_texts
    dna.usps = extract_usps(usp_texts)
    dna.about_text = about_text_raw[:2000]

    nav_junk = {"skip", "menu", "home", "contact", "about", "login", "sign",
                "cookie", "accept", "privacy", "toggle", "close", "search", "navigation"}
    tagline_candidates = [
        l.strip()
        for l in dna.homepage_text.split("\n")
        if 10 < len(l.strip()) < 150
        and not any(w in nav_junk for w in l.lower().split()[:2])
        and not _is_lorem_ipsum(l)
    ]
    if tagline_candidates:
        dna.tagline = tagline_candidates[0]
    elif dna.description:
        dna.tagline = dna.description[:150]

    # ── Article titles ─────────────────────────────────────────────────────────
    article_titles = [
        t for t in article_titles
        if "@" not in t
        and not t.lower().startswith("mailto")
        and len(t.split()) >= 2
        and not _is_lorem_ipsum(t)
    ]

    clean_jld_articles = [
        t for t in jld_articles
        if len(t.split()) >= 2 and not _is_lorem_ipsum(t)
    ]

    # Case-study metrics — performance agencies only
    case_study_titles: list[str] = []
    homepage_combined = dna.homepage_text + " " + page_contents.get("portfolio", "")
    if re.search(
        r"\b(ROAS|ROI|CPL|CPA|CTR|CPC|leads generated|ad spend|conversion rate)\b",
        homepage_combined, re.I,
    ):
        for pattern in [
            r"([+-]?\d+[%xX]?\s+\w+[\w\s]{3,40}?)(?=\s*Challenges|\s*Strategy|\s*$|\n)",
            r"(\d+\.?\d*[xX]?\s+(?:ROAS|ROI|CPL|CPA|CTR|CPC)\s+[\w\s]{3,30}?)(?=\s*Challenges|\s*Strategy|\s*$|\n)",
        ]:
            for m in re.findall(pattern, homepage_combined, re.I):
                t = m.strip()
                if 8 < len(t) < 100 and not _is_lorem_ipsum(t):
                    case_study_titles.append(t)
        seen_cs: set[str] = set()
        deduped_cs = []
        for t in case_study_titles:
            key = t.lower()[:30]
            if key not in seen_cs:
                seen_cs.add(key)
                deduped_cs.append(t)
        case_study_titles = deduped_cs

    dna.existing_article_titles = list(
        dict.fromkeys(article_titles + clean_jld_articles + case_study_titles)
    )[:20]
    dna.portfolio_items = portfolio_items[:10]

    # ── Audience ───────────────────────────────────────────────────────────────
    combined_text = " ".join(all_texts[:3])
    audience_clues = []
    if re.search(r"homeowner|home owner|residential|families", combined_text, re.I):
        audience_clues.append("homeowners")
    if re.search(r"corporate|office|commercial|business", combined_text, re.I):
        audience_clues.append("businesses")
    if re.search(r"startup|co-working|coworking", combined_text, re.I):
        audience_clues.append("startups")
    if re.search(r"luxury|premium|high-end|bespoke", combined_text, re.I):
        audience_clues.append("premium segment buyers")
    dna.target_audience = (
        ", ".join(audience_clues) if audience_clues else "professionals and homeowners"
    )

    # ── Pain points ────────────────────────────────────────────────────────────
    for pattern in [
        r"(without[^.!?]{10,60}[.!?])",
        r"(no more[^.!?]{5,50}[.!?])",
        r"(never worry[^.!?]{5,50}[.!?])",
        r"(stress[^.!?]{5,50}[.!?])",
        r"(hassle[^.!?]{5,50}[.!?])",
    ]:
        matches = re.findall(pattern, combined_text, re.I)
        dna.pain_points.extend(m.strip() for m in matches[:1])
    if not dna.pain_points:
        dna.pain_points = [
            "Managing vendors and timelines is overwhelming",
            "Uncertainty about costs spiraling beyond budget",
            "Getting quality finishes without constant supervision",
        ]

    print(f"\n[DNA] Profile built for: {dna.name}")
    print(f"  Services found:  {len(dna.services)}")
    print(f"  Articles found:  {len(dna.existing_article_titles)}")
    print(f"  Portfolio items: {len(dna.portfolio_items)}")
    print(f"  Locations:       {', '.join(dna.locations[:4])}")
    print(f"  Top keywords:    {', '.join(dna.top_keywords[:8])}")
    print(f"  Tone:            {', '.join(dna.tone_adjectives)}")

    return dna


def save_dna(dna: CompanyDNA, path: str = "company_dna.json"):
    with open(path, "w") as f:
        json.dump(asdict(dna), f, indent=2)
    print(f"[DNA] Saved to {path}")


def load_dna(path: str = "company_dna.json") -> CompanyDNA:
    with open(path) as f:
        data = json.load(f)
    return CompanyDNA(**data)


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    async def main():
        dna = await extract_company_dna(url)
        save_dna(dna)
        print("\n── Company DNA ──────────────────────────────")
        print(f"Name:     {dna.name}")
        print(f"Tagline:  {dna.tagline}")
        print(f"Audience: {dna.target_audience}")
        print(f"Tone:     {', '.join(dna.tone_adjectives)}")
        print(f"Services: {', '.join(dna.services[:5])}")
        print(f"USPs:     {chr(10).join(dna.usps[:3])}")

    asyncio.run(main())
