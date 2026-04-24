"""
Engine 1 — Company DNA Extractor
Scrapes a brand website and builds a deep profile:
tone, services, projects, audience, writing style, keywords used.

Discovery strategy (in order):
  1. sitemap.xml  — most reliable, exposes all URLs the site wants indexed
  2. Homepage link crawl — finds every internal link, auto-classifies by path keywords
  3. Auto-detect listing pages — any nav page with 3+ sub-links is treated as a blog/portfolio
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

# ── spaCy for NLP (free, local) ──────────────────────────────────────────────
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    NLP_AVAILABLE = True
except Exception:
    NLP_AVAILABLE = False
    print("[warn] spaCy not available — keyword extraction will use simple method")


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


# ── Section classification keywords ──────────────────────────────────────────
# Maps section type → keywords that can appear anywhere in the URL path segment.
# Order matters: more specific sections listed first.

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
        "clients", "references",
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
    ],
    "contact": [
        "contact", "contact-us", "contactus", "get-in-touch",
        "getintouch", "hire", "reach", "enquiry", "inquiry",
    ],
}

# Segments that are NOT content pages (skip them)
SKIP_SEGMENTS = {
    "tag", "tags", "category", "categories", "author", "authors",
    "page", "wp-content", "wp-admin", "wp-includes", "wp-json",
    "feed", "rss", "atom", "cdn", "assets", "static", "media",
    "uploads", "images", "img", "css", "js", "fonts",
    "search", "404", "500", "sitemap", "robots",
    "login", "logout", "register", "admin", "dashboard",
    "cart", "checkout", "account", "wishlist",
    "privacy", "terms", "disclaimer", "cookie",
    "amp", "m",  # mobile/AMP subdomains sometimes appear as paths
}


# ── Helpers ───────────────────────────────────────────────────────────────────

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
            # Also partial match: e.g. "blogpost" → blog
            for signal in signals:
                if signal in seg_clean and len(signal) > 4:
                    return section
    return None


def is_listing_url(path: str) -> bool:
    """True if path looks like a listing/index page (1-2 segments), not an article."""
    parts = path.strip("/").split("/")
    return len(parts) <= 2


def is_article_url(path: str) -> bool:
    """True if path looks like a single article (2+ segments, last part is a slug)."""
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        return False
    slug = parts[-1]
    return bool(slug) and not slug.isdigit() and len(slug) > 3


# ── Sitemap parser ────────────────────────────────────────────────────────────

async def fetch_sitemap(base_url: str, domain: str) -> list[str]:
    """
    Try common sitemap paths. Returns a flat list of all URLs found.
    Handles both sitemap.xml and sitemap_index.xml (nested sitemaps).
    """
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

                    # Sitemap index: contains <sitemap> tags pointing to sub-sitemaps
                    if "<sitemapindex" in text or ("<sitemap>" in text and "<loc>" in text):
                        sub_locs = re.findall(r"<loc>\s*(https?://[^<]+)\s*</loc>", text)
                        for sub in sub_locs[:6]:
                            if "sitemap" in sub.lower():
                                try:
                                    r2 = await client.get(sub)
                                    if r2.status_code == 200:
                                        locs = re.findall(r"<loc>\s*(https?://[^<]+)\s*</loc>", r2.text)
                                        same_domain = [u for u in locs if domain in u]
                                        urls.extend(same_domain[:150])
                                except Exception:
                                    pass
                        if urls:
                            print(f"[DNA] Sitemap index: {len(urls)} URLs")
                            break

                    # Regular sitemap: contains <url><loc>...</loc></url>
                    elif "<urlset" in text or "<url>" in text:
                        locs = re.findall(r"<loc>\s*(https?://[^<]+)\s*</loc>", text)
                        same_domain = [u for u in locs if domain in u]
                        urls.extend(same_domain[:300])
                        if urls:
                            print(f"[DNA] Sitemap: {sitemap_url} ({len(urls)} URLs)")
                            break

                except Exception:
                    continue
    except Exception:
        pass

    return urls


# ── NLP helpers (unchanged) ───────────────────────────────────────────────────

def _is_lorem_ipsum(text: str) -> bool:
    """Return True if text looks like Lorem Ipsum / placeholder Latin."""
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
        "egestas", "praesent", "commodo", "cursus", "viverra", "suspendisse",
        "potenti", "accumsan", "lacus", "vestibulum", "ante", "primis",
        "orci", "luctus", "posuere", "cubilia", "curae", "proin",
        "sapien", "venenatis", "lacinia", "feugiat", "vulputate", "tortor",
        "dignissim", "convallis", "aenean", "pretium", "ligula", "porttitor",
        "rhoncus", "consequat", "phasellus", "augue", "sollicitudin",
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

    # Filter out Lorem Ipsum / placeholder text before NLP
    clean_texts = [t for t in texts if not _is_lorem_ipsum(t)]
    if not clean_texts:
        clean_texts = texts  # fallback

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

    # Latin / Lorem Ipsum words to reject from keywords
    latin_junk = {
        "lorem", "ipsum", "dolor", "amet", "consectetur", "adipiscing",
        "elit", "sed", "etiam", "maecenas", "nullam", "donec", "curabitur",
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
        # Reject if any word in the term is Latin placeholder
        term_words = set(term.split())
        if term_words & latin_junk:
            continue
        results.append(term)
        if len(results) >= top_n:
            break
    return results


def extract_keywords_simple(texts: list[str], top_n: int = 30) -> list[str]:
    # Filter out Lorem Ipsum text
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
    # Latin / Lorem Ipsum words
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
        combined, re.I
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
    good_samples = [s for s in sentences
                    if 10 < len(s.split()) < 30
                    and not s.lower().startswith(nav_junk_starts)
                    and not _is_lorem_ipsum(s)]
    sample = good_samples[0] if good_samples else (sentences[0] if sentences else "")

    return tone, sample.strip(), avg_len, uses_first_person


def extract_usps(texts: list[str]) -> list[str]:
    patterns = [
        r"(\d+\+?\s+years?\s+(?:of\s+)?(?:experience|expertise)[^.!?]*[.!?])",
        r"(over\s+\d+\s+(?:projects?|clients?|homes?|spaces?)[^.!?]*[.!?])",
        r"(trusted\s+by[^.!?]*[.!?])",
        r"(award[^.!?]*[.!?])",
        r"(guarantee[^.!?]*[.!?])",
        r"(only\s+(?:company|firm|studio)[^.!?]*[.!?])",
        r"(certified[^.!?]*[.!?])",
        r"(ISO[^.!?]*[.!?])",
    ]
    usps = []
    combined = " ".join(texts)
    for pattern in patterns:
        matches = re.findall(pattern, combined, re.I)
        usps.extend(m.strip() for m in matches[:2])
    return list(set(usps))[:6]


# ── Core scraping function ────────────────────────────────────────────────────

async def extract_company_dna(base_url: str) -> CompanyDNA:
    base_url = base_url.rstrip("/")
    parsed_base = urlparse(base_url)
    domain = parsed_base.netloc  # e.g. "example.com" or "www.example.com"

    dna = CompanyDNA(domain=domain)
    print(f"\n[DNA] Extracting company profile from: {base_url}")

    page_contents: dict[str, str] = {}
    article_titles: list[str] = []
    article_texts:  list[str] = []
    portfolio_items: list[dict] = []

    # ── Step 1: Sitemap (fast, no browser) ───────────────────────────────────
    sitemap_urls = await fetch_sitemap(base_url, domain)

    # Build section → candidate URLs from sitemap
    sitemap_by_section: dict[str, list[str]] = defaultdict(list)
    for url in sitemap_urls:
        path = urlparse(url).path
        section = classify_path(path)
        if section:
            sitemap_by_section[section].append(url)

    # ─────────────────────────────────────────────────────────────────────────
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
        await context.route("**/*", lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font")
            else route.continue_())

        page = await context.new_page()

        async def scrape(url: str, label: str = "") -> str:
            try:
                await asyncio.sleep(0.8)
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if not resp or resp.status >= 400:
                    return ""
                # Scroll down to trigger lazy-loaded / carousel content
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await asyncio.sleep(0.5)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)
                text = await page.evaluate("""() => {
                    ['nav','footer','header','script','style','noscript',
                     '.cookie','#cookie','[class*="cookie"]','[id*="cookie"]',
                     '[class*="popup"]','[class*="modal"]'].forEach(sel => {
                        try { document.querySelectorAll(sel)
                              .forEach(el => el.remove()); } catch(e){}
                    });
                    return document.body ? document.body.innerText : '';
                }""")
                return clean_text(text)
            except Exception as e:
                print(f"[DNA] Could not scrape {url}: {e}")
                return ""

        async def get_page_links() -> list[dict]:
            """Get all links from the currently loaded page."""
            try:
                return await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => ({href: e.href||'', text:(e.innerText||'').trim()}))",
                )
            except Exception:
                return []

        def is_same_domain(url: str) -> bool:
            n = urlparse(url).netloc
            return n == domain or n.endswith("." + domain) or domain.endswith("." + n)

        # ── Step 2: Homepage ─────────────────────────────────────────────────
        print("[DNA] Scraping homepage...")
        homepage_text = await scrape(base_url, "homepage")
        dna.homepage_text = homepage_text[:3000]
        page_contents["homepage"] = homepage_text

        # Extract brand name — prefer OG/meta tags, then structured data, then <title>.
        # Avoid using raw <title> since it often contains SEO phrases or taglines.
        try:
            brand_name = await page.evaluate("""() => {
                // 1. Open Graph site_name (most reliable brand name)
                const ogSite = document.querySelector('meta[property="og:site_name"]');
                if (ogSite && ogSite.content.trim()) return ogSite.content.trim();

                // 2. Schema.org Organization name
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

                // 3. <title> — split on common separators and check each segment
                const title = document.title || '';
                // Split on all common separators: | – — - · : » ·
                const parts = title.split(/[|–—·:»]/).map(s => s.trim()).filter(Boolean);
                const seoWords = ['best', 'top', 'leading', 'premier', '#1', 'no.1',
                                  'affordable', 'cheap', 'data-driven', 'performance',
                                  'growth', 'agency', 'expert', 'specialist'];

                // Find the shortest segment that looks like a brand name (1-4 words, no SEO bait)
                for (const part of parts) {
                    const words = part.split(/\\s+/);
                    const lower = part.toLowerCase();
                    const isSEO = words.length > 4 || seoWords.some(w => lower.includes(w));
                    if (!isSEO && words.length >= 1 && words.length <= 4) return part;
                }

                // If all segments are SEO-ish, try the shortest one
                if (parts.length > 0) {
                    const shortest = parts.reduce((a, b) => a.length <= b.length ? a : b);
                    if (shortest.split(/\\s+/).length <= 4) return shortest;
                }

                return '';
            }""")
            if brand_name:
                dna.name = brand_name.strip()
            else:
                dna.name = domain.replace("www.", "").split(".")[0].title()
        except Exception:
            dna.name = domain.replace("www.", "").split(".")[0].title()

        # Grab meta description / OG description for tagline fallback
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

        # ── Step 3: Discover all internal links from homepage ────────────────
        all_home_links = await get_page_links()

        # Group links by first path segment
        nav_segments: dict[str, list[dict]] = defaultdict(list)
        for link in all_home_links:
            href = link["href"]
            if not is_same_domain(href):
                continue
            path = urlparse(href).path.rstrip("/")
            parts = path.strip("/").split("/")
            seg = parts[0].lower() if parts and parts[0] else ""
            if seg and seg not in SKIP_SEGMENTS:
                nav_segments[seg].append({"href": href, "text": link["text"]})

        print(f"[DNA] Discovered segments: {list(nav_segments.keys())[:20]}")

        # ── Step 4: Build per-section candidate URL lists ────────────────────
        # Priority: sitemap > homepage nav discovery > hardcoded fallback
        section_candidates: dict[str, list[str]] = defaultdict(list)
        queued: set[str] = set()

        def queue(section: str, url: str):
            u = url.split("?")[0].split("#")[0].rstrip("/")
            if u and u not in queued:
                queued.add(u)
                section_candidates[section].append(u)

        # Sitemap-derived
        for section, urls in sitemap_by_section.items():
            for url in urls:
                queue(section, url)

        # Homepage-nav-derived
        for seg, links in nav_segments.items():
            sec = classify_path(seg)
            if sec:
                for link in links:
                    queue(sec, link["href"])

        # Hardcoded fallbacks
        FALLBACKS: dict[str, list[str]] = {
            "about":    ["/about", "/about-us", "/our-story", "/who-we-are", "/company", "/team", "/our-team"],
            "services": ["/services", "/what-we-do", "/solutions", "/offerings", "/capabilities"],
            "portfolio":["/portfolio", "/projects", "/case-studies", "/gallery", "/work", "/our-work"],
            "blog":     ["/blog", "/insights", "/articles", "/news", "/resources", "/stories",
                         "/journal", "/updates", "/thinking", "/posts", "/guides", "/tutorials",
                         "/tips", "/knowledge", "/media", "/press", "/publications"],
            "contact":  ["/contact", "/contact-us", "/get-in-touch"],
        }
        for section, paths in FALLBACKS.items():
            for path in paths:
                queue(section, urljoin(base_url, path))

        # ── Step 5: Scrape each section ──────────────────────────────────────
        for section in ["about", "services", "portfolio", "blog", "contact"]:
            candidates = section_candidates.get(section, [])
            # Try listing URLs first (shorter paths), skip deep article URLs
            listing_first = sorted(
                [u for u in candidates if is_listing_url(urlparse(u).path)],
                key=lambda u: len(urlparse(u).path)
            )
            for url in listing_first[:8]:
                print(f"[DNA] Trying {section}: {url}")
                text = await scrape(url, section)
                if len(text) > 200:
                    page_contents[section] = text
                    print(f"[DNA]   OK {len(text)} chars")
                    break

        # ── Step 6: Discover articles (3-layer strategy) ─────────────────────

        discovered_articles: list[dict] = []

        # — 6a: Scrape blog AND portfolio listing pages and pull links —
        # Many sites put articles/case-studies under portfolio or case-study sections
        article_listing_sections = ["blog", "portfolio"]
        for _als in article_listing_sections:
            listing_text = page_contents.get(_als, "")
            if not listing_text:
                continue
            listing_url = next(
                (u for u in section_candidates.get(_als, [])
                 if is_listing_url(urlparse(u).path)),
                None
            )
            if listing_url:
                await page.goto(listing_url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(0.5)
                links_on_listing = await get_page_links()
                for link in links_on_listing:
                    href = link["href"].split("?")[0].split("#")[0]
                    text = link["text"].strip()
                    if not is_same_domain(href):
                        continue
                    path = urlparse(href).path
                    parts = path.strip("/").split("/")
                    if (len(parts) >= 1 and len(text) > 5
                        and len(parts[-1]) > 3
                        and parts[-1] not in {"#", ""}
                        and not _is_lorem_ipsum(text)):
                        discovered_articles.append({"href": href, "text": text})
                print(f"[DNA] {_als.title()} listing → {len(discovered_articles)} article links so far")

        # Legacy blog-only path (kept for sites where blog_text exists but loop above handled it)
        blog_text = page_contents.get("blog", "")
        if blog_text and not discovered_articles:
            blog_url = next(
                (u for u in section_candidates.get("blog", [])
                 if is_listing_url(urlparse(u).path)),
                None
            )
            if blog_url:
                await page.goto(blog_url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(0.5)
                links_on_blog = await get_page_links()
                for link in links_on_blog:
                    href = link["href"].split("?")[0].split("#")[0]
                    text = link["text"].strip()
                    if not is_same_domain(href):
                        continue
                    path = urlparse(href).path
                    parts = path.strip("/").split("/")
                    # Accept links with 1+ path segments, meaningful text, real slug
                    if (len(parts) >= 1 and len(text) > 5
                        and len(parts[-1]) > 3
                        and parts[-1] not in {"#", ""}
                        and not _is_lorem_ipsum(text)):
                        discovered_articles.append({"href": href, "text": text})
            print(f"[DNA] Blog listing → {len(discovered_articles)} article links")

        # — 6b: Sitemap-based article discovery —
        # Find path segments that appear 3+ times in sitemap (= blog/news sections)
        if not discovered_articles and sitemap_urls:
            seg_counts: Counter = Counter()
            for url in sitemap_urls:
                p = urlparse(url)
                if not is_same_domain(url):
                    continue
                parts = p.path.strip("/").split("/")
                if len(parts) >= 2:
                    seg_counts[parts[0].lower()] += 1

            # Top segments with 3+ entries, excluding known non-content segments
            content_segments = [
                seg for seg, cnt in seg_counts.most_common(10)
                if cnt >= 3 and seg not in SKIP_SEGMENTS
            ]
            print(f"[DNA] Sitemap content segments: {content_segments[:6]}")

            for seg in content_segments[:3]:
                art_urls = [
                    u for u in sitemap_urls
                    if is_same_domain(u)
                    and urlparse(u).path.strip("/").split("/")[0].lower() == seg
                    and is_article_url(urlparse(u).path)
                ]
                if len(art_urls) >= 2:
                    for url in art_urls[:8]:
                        slug = urlparse(url).path.strip("/").split("/")[-1]
                        title = slug.replace("-", " ").replace("_", " ").title()
                        discovered_articles.append({"href": url, "text": title})
                    print(f"[DNA] Sitemap segment /{seg}/ → {len(art_urls)} articles")
                    break

        # — 6c: Auto-detect listing pages from homepage nav —
        # Any nav segment that has 3+ links to sub-paths is probably a blog/news
        if not discovered_articles:
            for seg, links in nav_segments.items():
                if seg in SKIP_SEGMENTS:
                    continue
                sub_links = [
                    l for l in links
                    if len(urlparse(l["href"]).path.strip("/").split("/")) >= 2
                    and len(l["text"].strip()) > 10
                ]
                if len(sub_links) >= 3:
                    print(f"[DNA] Auto-detected listing: /{seg}/ ({len(sub_links)} items)")
                    for l in sub_links[:8]:
                        discovered_articles.append({"href": l["href"], "text": l["text"]})
                    break

        # — 6d: Try every undiscovered nav segment as a potential listing page —
        if not discovered_articles:
            unclassified = [
                seg for seg in nav_segments
                if seg not in SKIP_SEGMENTS and classify_path(seg) is None
            ]
            print(f"[DNA] Trying unclassified segments for articles: {unclassified[:5]}")
            for seg in unclassified[:6]:
                listing_url = urljoin(base_url, f"/{seg}")
                text = await scrape(listing_url, f"listing-{seg}")
                if len(text) < 150:
                    continue
                links_on_page = await get_page_links()
                sub = [
                    l for l in links_on_page
                    if is_same_domain(l["href"])
                    and len(urlparse(l["href"]).path.strip("/").split("/")) >= 2
                    and len(l["text"].strip()) > 12
                ]
                if len(sub) >= 3:
                    print(f"[DNA] Found listing: /{seg}/ ({len(sub)} articles)")
                    for l in sub[:8]:
                        discovered_articles.append({"href": l["href"], "text": l["text"]})
                    break

        # ── Step 7: Scrape top 5 articles ────────────────────────────────────
        # Deduplicate
        seen_hrefs: set[str] = set()
        unique_articles: list[dict] = []
        for art in discovered_articles:
            href = art["href"].split("?")[0].split("#")[0].rstrip("/")
            text = art["text"].strip()
            if href not in seen_hrefs and len(text) > 8 and is_article_url(urlparse(href).path):
                seen_hrefs.add(href)
                unique_articles.append({"href": href, "text": text})

        print(f"[DNA] {len(unique_articles)} unique article URLs to read")
        for link in unique_articles[:5]:
            print(f"[DNA] Reading article: {link['text'][:65]}")
            article_titles.append(link["text"].strip())
            text = await scrape(link["href"], "article")
            if text:
                article_texts.append(text[:2000])

        # ── Step 8: Portfolio items ───────────────────────────────────────────
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
                    desc = lines[i+1] if i+1 < len(lines) else ""
                    portfolio_items.append({"title": line, "description": desc})

        await browser.close()

    # ── Build the DNA profile ─────────────────────────────────────────────────
    all_texts = [v for v in page_contents.values() if v]

    dna.tone_adjectives, dna.tone_sample, dna.avg_sentence_length, dna.uses_first_person = \
        infer_tone(all_texts)

    dna.top_keywords = extract_keywords_spacy(all_texts + article_texts, top_n=40)

    services_raw = page_contents.get(
        "services",
        page_contents.get("homepage", "") + " " + page_contents.get("about", ""),
    )
    service_candidates = []
    for chunk in re.split(r"[\n.!]", services_raw):
        chunk = chunk.strip()
        if 8 < len(chunk) < 120:
            service_candidates.append(chunk)

    service_keywords = [
        # General
        "design", "install", "deliver", "service", "solution", "consult",
        "manage", "develop", "create", "provide", "strategy", "growth",
        "optimization", "audit", "training", "support", "analytics",
        # Interior / construction
        "interior", "furnish", "renovate", "build", "construct", "modular",
        "kitchen", "bedroom", "living", "wardrobe", "ceiling", "flooring",
        "lighting", "residential", "commercial", "hospitality", "turnkey",
        "execution", "workmanship", "craftsmanship", "spaces", "aesthet",
        "functional", "luxury", "bespoke",
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
    ui_noise = ["view more", "click", "skip", "instagram", "facebook",
                "youtube", "linkedin", "whatsapp", "pinterest", "explore",
                "connect on linkedin", "book a free", "view all", "view case",
                "meet the", "our vision"]
    # Phrases that are section headers / taglines, not actual service descriptions
    noise_phrases = [
        "our services", "we don't sell", "what we do", "how we work",
        "why choose us", "our approach", "our process", "get started",
        "learn more", "read more", "see all", "view all",
    ]
    dna.services = [
        c for c in service_candidates
        if any(w in c.lower() for w in service_keywords)
        and not any(u in c.lower() for u in ui_noise)
        and not any(n in c.lower() for n in noise_phrases)
        and not _is_lorem_ipsum(c)
        and len(c.split()) >= 3  # Must be at least 3 words (not just a heading)
    ][:10]

    # If no services found via keyword matching, try extracting from structured
    # patterns on the homepage (e.g., "Performance Marketing", "SEO & Content")
    if not dna.services:
        # Look for short capitalized phrases that look like service names
        homepage_lines = [l.strip() for l in (page_contents.get("homepage", "") + " " + page_contents.get("services", "")).split("\n")]
        for line in homepage_lines:
            line = line.strip()
            # Service-like: 2-8 words, not all lowercase nav junk
            words = line.split()
            if 2 <= len(words) <= 8 and len(line) < 80 and len(line) > 8:
                lower = line.lower()
                if any(w in lower for w in service_keywords):
                    if not any(n in lower for n in noise_phrases):
                        if not any(u in lower for u in ui_noise):
                            if not _is_lorem_ipsum(line):
                                dna.services.append(line)
            if len(dna.services) >= 10:
                break
        # Deduplicate
        seen = set()
        unique_services = []
        for s in dna.services:
            key = s.lower().strip()
            if key not in seen:
                seen.add(key)
                unique_services.append(s)
        dna.services = unique_services[:10]

    dna.usps = extract_usps(all_texts)
    dna.about_text = page_contents.get("about", "")[:2000]

    # Tagline: prefer meta description / OG description, then first meaningful homepage line
    tagline_candidates = []
    # Try to grab meta/OG descriptions from homepage text (already scraped)
    # We'll set tagline from the homepage lines but filter out nav junk
    nav_junk = {"skip", "menu", "home", "contact", "about", "login", "sign", "cookie",
                "accept", "privacy", "toggle", "close", "search", "navigation"}
    lines = [l.strip() for l in dna.homepage_text.split("\n") if 10 < len(l.strip()) < 150]
    for line in lines:
        words = line.lower().split()
        if any(w in nav_junk for w in words[:2]):
            continue
        if _is_lorem_ipsum(line):
            continue
        tagline_candidates.append(line)
    if tagline_candidates:
        dna.tagline = tagline_candidates[0]
    elif dna.description:
        # Fallback to meta/OG description
        dna.tagline = dna.description[:150]
    else:
        dna.tagline = ""

    # Filter out email addresses and junk from article titles
    article_titles = [
        t for t in article_titles
        if "@" not in t                        # no emails
        and not t.lower().startswith("mailto")
        and len(t.split()) >= 2                # at least 2 words
        and not _is_lorem_ipsum(t)
    ]

    # ── Extract case studies / results from homepage text ─────────────────────
    # Many sites embed case studies as inline cards on the homepage with patterns
    # like "+57% Subs UWorld EdTech" or "4.2 ROAS Personiks Healthcare"
    # These are valuable as "existing article topics" even if not linked pages.
    case_study_titles = []
    homepage_combined = dna.homepage_text + " " + page_contents.get("portfolio", "")
    # Pattern: metric + brand/company name — e.g. "+57% Subs UWorld" or "-41% CPL HomeDealz"
    cs_patterns = [
        # "+57% Subs UWorld  EdTech SaaS" or "-41% CPL HomeDealz  Real Estate"
        r"([+-]?\d+[%xX]?\s+\w+[\w\s]{3,40}?)(?=\s*Challenges|\s*Strategy|\s*$|\n)",
        # "4.2 ROAS Personiks" or "4.2X ROAS for Personiks"
        r"(\d+\.?\d*[xX]?\s+(?:ROAS|ROI|CPL|CPA|CTR|CPC)\s+[\w\s]{3,30}?)(?=\s*Challenges|\s*Strategy|\s*$|\n)",
    ]
    for pattern in cs_patterns:
        matches = re.findall(pattern, homepage_combined, re.I)
        for m in matches:
            title = m.strip()
            if 8 < len(title) < 100 and not _is_lorem_ipsum(title):
                case_study_titles.append(title)

    # Also look for "Case Study" or "Our Work" section headers followed by client names
    cs_section = re.search(
        r"(?:case stud|our work|results|work speaks)[^\n]*\n(.*?)(?=\n(?:how we work|about|contact|footer|$))",
        homepage_combined, re.I | re.S
    )
    if cs_section:
        cs_text = cs_section.group(1)
        # Extract lines that look like case study titles (short, have a brand name + metric)
        for line in cs_text.split("\n"):
            line = line.strip()
            if (10 < len(line) < 100
                and re.search(r"[+-]?\d+[%xX]", line)
                and not _is_lorem_ipsum(line)):
                case_study_titles.append(line)

    # Deduplicate case studies
    seen_cs = set()
    unique_cs = []
    for t in case_study_titles:
        key = t.lower()[:30]
        if key not in seen_cs:
            seen_cs.add(key)
            unique_cs.append(t)

    # Merge: scraped article titles + extracted case study titles
    all_article_titles = article_titles + unique_cs

    dna.existing_article_titles = all_article_titles
    dna.portfolio_items = portfolio_items[:10]

    combined = " ".join(all_texts[:3])
    audience_clues = []
    if re.search(r"homeowner|home owner|residential|families", combined, re.I):
        audience_clues.append("homeowners")
    if re.search(r"corporate|office|commercial|business", combined, re.I):
        audience_clues.append("businesses")
    if re.search(r"startup|co-working|coworking", combined, re.I):
        audience_clues.append("startups")
    if re.search(r"luxury|premium|high-end|bespoke", combined, re.I):
        audience_clues.append("premium segment buyers")
    dna.target_audience = (
        ", ".join(audience_clues) if audience_clues else "professionals and homeowners"
    )

    pain_patterns = [
        r"(without[^.!?]{10,60}[.!?])",
        r"(no more[^.!?]{5,50}[.!?])",
        r"(never worry[^.!?]{5,50}[.!?])",
        r"(stress[^.!?]{5,50}[.!?])",
        r"(hassle[^.!?]{5,50}[.!?])",
    ]
    for pattern in pain_patterns:
        matches = re.findall(pattern, combined, re.I)
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
