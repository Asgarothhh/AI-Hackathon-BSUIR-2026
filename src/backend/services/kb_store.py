import re
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.backend.models.kb_models import KnowledgePage
from supabase.client import Client, create_client


class KnowledgeStore:
    def __init__(self) -> None:
        self._pages: Dict[str, KnowledgePage] = {}
        self._supabase: Optional[Client] = None
        self._supabase_table = os.getenv("KB_SUPABASE_TABLE", "kb_pages")
        default_path = Path.cwd() / "uploads" / "kb_store.json"
        self._persist_path = Path(os.getenv("KB_STORE_PATH", str(default_path)))
        self._init_supabase()
        self._load()

    def upsert(self, page: KnowledgePage, save: bool = True) -> KnowledgePage:
        # Remove placeholder welcome once real content appears.
        if page.slug != "welcome" and "welcome" in self._pages:
            self._pages.pop("welcome", None)
        self._pages[page.slug] = page
        if save:
            self._save()
        return page

    def replace_with(self, page: KnowledgePage) -> KnowledgePage:
        """
        Single-KB mode: keep only one knowledge page in storage.
        """
        self._pages = {page.slug: page}
        self._save()
        return page

    def get(self, slug: str) -> Optional[KnowledgePage]:
        return self._pages.get(slug)

    def all_pages(self) -> List[KnowledgePage]:
        return sorted(self._pages.values(), key=lambda x: (x.chapter, x.title))

    def flush(self) -> None:
        self._save()

    def chapters(self) -> Dict[str, List[KnowledgePage]]:
        result: Dict[str, List[KnowledgePage]] = {}
        for page in self.all_pages():
            result.setdefault(page.chapter, []).append(page)
        return result

    def search(self, query: str, limit: int = 5, allowed_slugs: Optional[set[str]] = None) -> List[KnowledgePage]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored = []
        for page in self._pages.values():
            if allowed_slugs is not None and page.slug not in allowed_slugs:
                continue
            haystack = f"{page.title}\n{page.markdown}"
            haystack_tokens = self._tokenize(haystack)
            if not haystack_tokens:
                continue

            overlap = len(query_tokens.intersection(haystack_tokens))
            exact_phrase_bonus = haystack.lower().count(query.lower().strip()) * 2
            score = overlap + exact_phrase_bonus
            if score > 0:
                scored.append((score, page))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [page for _, page in scored[:limit]]

    def search_snippets(
        self,
        query: str,
        limit: int = 6,
        allowed_slugs: Optional[set[str]] = None,
    ) -> List[dict]:
        """
        Return most relevant text fragments across pages for RAG answers.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored: List[tuple[int, dict]] = []
        for page in self._pages.values():
            if allowed_slugs is not None and page.slug not in allowed_slugs:
                continue
            for snippet in self._split_into_snippets(page.markdown):
                snippet_tokens = self._tokenize(snippet)
                if not snippet_tokens:
                    continue
                overlap = len(query_tokens.intersection(snippet_tokens))
                exact_bonus = snippet.lower().count(query.lower().strip()) * 2
                score = overlap + exact_bonus
                if score <= 0:
                    continue
                scored.append(
                    (
                        score,
                        {
                            "slug": page.slug,
                            "title": page.title,
                            "chapter": page.chapter,
                            "snippet": snippet.strip(),
                        },
                    )
                )

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        # Keep both latin/cyrillic words and numbers.
        return {token for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{2,}", text.lower())}

    @staticmethod
    def _split_into_snippets(markdown: str) -> List[str]:
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", markdown) if chunk.strip()]
        skip_patterns = (
            "## Навигация по определениям",
            "## Источники",
            "## Изображения",
        )
        filtered: List[str] = []
        for chunk in chunks:
            if len(chunk) < 60:
                continue
            if any(chunk.startswith(pattern) for pattern in skip_patterns):
                continue
            # Skip fragments overloaded with links only.
            if chunk.count("](") >= 4 and len(chunk) < 500:
                continue
            filtered.append(chunk)
        return filtered

    def auto_crosslink_term(self, term: str, target_slug: str, save: bool = True) -> bool:
        """
        Replace plain occurrences of term with Markdown links to target page.
        We skip the target page itself and already linked occurrences.
        """
        escaped = re.escape(term)
        # Not preceded by ]( and not inside existing markdown link title.
        pattern = re.compile(rf"(?<!\])\b({escaped})\b", re.IGNORECASE)
        changed = False
        for page in self._pages.values():
            if page.slug == target_slug:
                continue
            if re.search(pattern, page.markdown):
                replacement = rf"[\1](/kb/{target_slug})"
                updated = re.sub(pattern, replacement, page.markdown)
                if updated != page.markdown:
                    page.markdown = updated
                    changed = True
        if changed and save:
            self._save()
        return changed

    def auto_crosslink_terms(self, terms: List[str], target_slug: str) -> bool:
        """
        Batch cross-link terms and persist once.
        Reduces repeated full-store saves on large KB imports.
        """
        normalized: List[str] = []
        seen = set()
        for term in terms:
            value = (term or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(value)

        if not normalized:
            return False

        changed = False
        for term in normalized:
            if self.auto_crosslink_term(term, target_slug, save=False):
                changed = True
        if changed:
            self._save()
        return changed

    def _load(self) -> None:
        if self._supabase is not None:
            if self._load_from_supabase():
                return
        if not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else []
            for item in items:
                page = self._page_from_payload(item)
                if page.slug:
                    self._pages[page.slug] = page
        except Exception:
            # If file is corrupted, keep app running with empty in-memory state.
            self._pages = {}

    def _save(self) -> None:
        if self._supabase is not None:
            if self._save_to_supabase():
                return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for page in self._pages.values():
            item = asdict(page)
            item["updated_at"] = page.updated_at.isoformat()
            payload.append(item)
        self._persist_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _init_supabase(self) -> None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        if not (supabase_url and supabase_key):
            return
        try:
            self._supabase = create_client(supabase_url, supabase_key)
        except Exception:
            self._supabase = None

    def _load_from_supabase(self) -> bool:
        if self._supabase is None:
            return False
        try:
            response = self._supabase.table(self._supabase_table).select("*").execute()
            rows = response.data or []
            self._pages = {}
            for row in rows:
                page = self._page_from_payload(row)
                if page.slug:
                    self._pages[page.slug] = page
            return True
        except Exception:
            return False

    def _save_to_supabase(self) -> bool:
        if self._supabase is None:
            return False
        try:
            payload = []
            for page in self._pages.values():
                item = asdict(page)
                item["updated_at"] = page.updated_at.isoformat()
                payload.append(item)
            if payload:
                self._supabase.table(self._supabase_table).upsert(payload, on_conflict="slug").execute()

            # Keep remote table in sync with current in-memory pages.
            existing = self._supabase.table(self._supabase_table).select("slug").execute().data or []
            existing_slugs = {row.get("slug") for row in existing if isinstance(row, dict)}
            active_slugs = set(self._pages.keys())
            stale_slugs = sorted(slug for slug in existing_slugs if slug and slug not in active_slugs)
            if stale_slugs:
                self._supabase.table(self._supabase_table).delete().in_("slug", stale_slugs).execute()
            return True
        except Exception:
            return False

    @staticmethod
    def _page_from_payload(item: dict) -> KnowledgePage:
        updated_at_raw = item.get("updated_at")
        updated_at = datetime.utcnow()
        if isinstance(updated_at_raw, str):
            try:
                updated_at = datetime.fromisoformat(updated_at_raw)
            except ValueError:
                pass
        return KnowledgePage(
            slug=item.get("slug", ""),
            title=item.get("title", ""),
            chapter=item.get("chapter", "General"),
            markdown=item.get("markdown", ""),
            sources=item.get("sources", []) or [],
            images=item.get("images", []) or [],
            updated_at=updated_at,
        )


store = KnowledgeStore()
