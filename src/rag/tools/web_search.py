import html as html_lib
import logging
import re
from typing import Iterable, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

TRUSTED_LEGAL_DOMAINS = (
    "pravo.by",
    "etalonline.by",
    "kodeksy-by.com",
)

LEGAL_HINTS = (
    "трудовой кодекс",
    "кодекс",
    "статья",
    "закон",
    "указ",
    "постановление",
    "республика беларусь",
)


class WebSource(BaseModel):
    title: str = Field(default="")
    url: str
    snippet: str = Field(default="")


def _strip_tags(raw: str) -> str:
    no_tags = re.sub(r"<[^>]+>", "", raw)
    return html_lib.unescape(no_tags).strip()


def _extract_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _unwrap_duckduckgo_url(raw_url: str) -> str:
    """
    Converts DDG redirect links to original target URL when possible.
    """
    if not raw_url:
        return raw_url

    parsed = urlparse(raw_url)
    if "duckduckgo.com" not in (parsed.netloc or "").lower():
        return raw_url

    query = parse_qs(parsed.query)
    uddg = query.get("uddg", [])
    if not uddg:
        return raw_url
    return unquote(uddg[0])


def _iter_results(html: str) -> Iterable[WebSource]:
    # Pull result blocks to attach snippet to each URL.
    blocks = re.findall(r'(<div class="result__body">.*?</div>\s*</div>)', html, flags=re.DOTALL)
    if not blocks:
        # Fallback: only links, no snippets.
        links = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.DOTALL)
        for href, raw_title in links:
            clean_url = _unwrap_duckduckgo_url(html_lib.unescape(href).strip())
            if clean_url.startswith("http"):
                yield WebSource(title=_strip_tags(raw_title), url=clean_url, snippet="")
        return

    for block in blocks:
        match_link = re.search(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            flags=re.DOTALL,
        )
        if not match_link:
            continue

        href, raw_title = match_link.group(1), match_link.group(2)
        snippet_match = re.search(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', block, flags=re.DOTALL)
        if not snippet_match:
            snippet_match = re.search(r'<div[^>]*class="result__snippet"[^>]*>(.*?)</div>', block, flags=re.DOTALL)

        clean_url = _unwrap_duckduckgo_url(html_lib.unescape(href).strip())
        if not clean_url.startswith("http"):
            continue

        yield WebSource(
            title=_strip_tags(raw_title),
            url=clean_url,
            snippet=_strip_tags(snippet_match.group(1)) if snippet_match else "",
        )


def _score_source(source: WebSource, query: str, preferred_domains: Optional[Iterable[str]] = None) -> int:
    title_snippet = f"{source.title} {source.snippet}".lower()
    domain = _extract_domain(source.url)
    query_lc = query.lower()
    score = 0

    if domain in TRUSTED_LEGAL_DOMAINS:
        score += 40
    if preferred_domains and any(domain.endswith(d.lower()) for d in preferred_domains):
        score += 25
    if any(hint in title_snippet for hint in LEGAL_HINTS):
        score += 20
    if any(token and token in title_snippet for token in query_lc.split()):
        score += 10
    # Penalize search engines/aggregators and social pages.
    if any(bad in domain for bad in ("yandex.", "google.", "bing.", "youtube.", "facebook.", "vk.com", "t.me")):
        score -= 30
    return score


def search_sources(
    query: str,
    limit: int = 5,
    preferred_domains: Optional[Iterable[str]] = None,
) -> List[WebSource]:
    """
    Web search helper with URL unwrapping and legal-source ranking.
    Returns deduplicated, ranked links (best first).
    """
    query = query.strip()
    if not query:
        return []

    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            html = response.text
    except Exception as exc:
        logger.warning("Web search failed for query '%s': %s", query, exc)
        return []

    unique: dict[str, WebSource] = {}
    for item in _iter_results(html):
        if item.url not in unique:
            unique[item.url] = item

    ranked = sorted(
        unique.values(),
        key=lambda src: _score_source(src, query=query, preferred_domains=preferred_domains),
        reverse=True,
    )
    results = ranked[: max(limit, 0)]
    logger.info("Web search query='%s' found %s results", query, len(results))
    return results
