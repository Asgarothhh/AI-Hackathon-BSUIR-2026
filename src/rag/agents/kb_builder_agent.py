import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from src.rag.agents.llm_call import get_llm
from src.rag.tools.web_search import search_sources

logger = logging.getLogger(__name__)


class KnowledgeExtraction(BaseModel):
    summary: str = Field(default="", description="Detailed summary in Russian, 8-15 sentences")
    key_points: List[str] = Field(default_factory=list, description="Detailed list of key points")
    detailed_outline: List[str] = Field(
        default_factory=list, description="Structured section-by-section explanation"
    )
    definitions: List[Dict[str, str]] = Field(
        default_factory=list,
        description='List with {"term":"...", "definition":"..."} objects'
    )
    faqs: List[Dict[str, str]] = Field(
        default_factory=list,
        description='List with {"question":"...", "answer":"..."} objects'
    )
    chapters: List[Dict[str, str]] = Field(
        default_factory=list,
        description='List with {"title":"...", "content":"..."} chapter blocks',
    )


class KnowledgeBaseBuilderAgent:
    def __init__(self) -> None:
        self.model_name = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        self.fallback_model_name = os.getenv("OPENROUTER_FALLBACK_MODEL", "openai/gpt-4o-mini")
        self.llm = get_llm(self.model_name)
        self.parser = JsonOutputParser(pydantic_object=KnowledgeExtraction)

    @staticmethod
    def slugify(title: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", title.strip().lower())
        slug = slug.strip("-")
        return slug or "knowledge-page"

    def process(self, title: str, chapter: str, document_text: str) -> dict:
        logger.info(
            "KB process started: title='%s', chapter='%s', chars=%s",
            title,
            chapter,
            len(document_text or ""),
        )
        system_prompt = (
            "Ты агент построения базы знаний. "
            "Сделай максимально подробную и структурированную выдержку из документа. "
            "По возможности используй Markdown-таблицы для структурирования (например: определения, FAQ). "
            "Сформируй: summary, key_points, detailed_outline, definitions, faqs, chapters. "
            "summary должен быть развернутым, не менее 8 предложений. "
            "chapters должен содержать логические главы документа для навигации по базе знаний. "
            "Ответ строго в JSON."
        )
        human_prompt = (
            f"Заголовок: {title}\n"
            f"Глава: {chapter}\n\n"
            f"Документ:\n{document_text}\n\n"
            f"{self.parser.get_format_instructions()}"
        )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
        try:
            response = self.llm.invoke(messages)
        except Exception as exc:
            # Common issue: model alias removed/renamed in OpenRouter (404 NotFound).
            if "404" in str(exc) and self.model_name != self.fallback_model_name:
                logger.warning(
                    "Primary model '%s' failed with 404. Retrying with fallback '%s'.",
                    self.model_name,
                    self.fallback_model_name,
                )
                self.llm = get_llm(self.fallback_model_name)
                response = self.llm.invoke(messages)
            else:
                raise
        parsed = self.parser.parse(response.content)
        parsed["slug"] = self.slugify(title)
        parsed["title"] = title
        parsed["chapter"] = chapter
        logger.info(
            "KB process finished: title='%s', defs=%s, faqs=%s, chapters=%s",
            title,
            len(parsed.get("definitions", []) or []),
            len(parsed.get("faqs", []) or []),
            len(parsed.get("chapters", []) or []),
        )
        return parsed

    def process_documents(self, title: str, chapter: str, documents: List[Dict[str, str]]) -> dict:
        """
        Build one rich knowledge page from multiple input documents.
        documents item format: {"name": str, "content": str}
        """
        merged_blocks: List[str] = []
        for idx, doc in enumerate(documents, start=1):
            doc_name = (doc.get("name") or f"Документ {idx}").strip()
            doc_content = (doc.get("content") or "").strip()
            if not doc_content:
                continue
            merged_blocks.append(f"### Источник {idx}: {doc_name}\n{doc_content}")

        if not merged_blocks:
            raise ValueError("No non-empty documents provided")

        combined_document = "\n\n".join(merged_blocks)
        system_prompt = (
            "Ты агент построения базы знаний. "
            "Тебе передано несколько документов по одной теме. "
            "Сделай ЕДИНУЮ максимально подробную и структурированную статью, "
            "объединив информацию из всех источников, убрав повторы и противоречия. "
            "Явно выдели общие положения, отличия по источникам и практические выводы. "
            "По возможности используй Markdown-таблицы для определений и FAQ. "
            "Сформируй: summary, key_points, detailed_outline, definitions, faqs, chapters. "
            "summary должен быть развернутым, не менее 10 предложений. "
            "chapters должен содержать логические главы итоговой статьи. "
            "Ответ строго в JSON."
        )
        human_prompt = (
            f"Заголовок: {title}\n"
            f"Глава: {chapter}\n"
            f"Количество источников: {len(merged_blocks)}\n\n"
            f"Документы:\n{combined_document}\n\n"
            f"{self.parser.get_format_instructions()}"
        )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
        try:
            response = self.llm.invoke(messages)
        except Exception as exc:
            if "404" in str(exc) and self.model_name != self.fallback_model_name:
                logger.warning(
                    "Primary model '%s' failed with 404. Retrying with fallback '%s'.",
                    self.model_name,
                    self.fallback_model_name,
                )
                self.llm = get_llm(self.fallback_model_name)
                response = self.llm.invoke(messages)
            else:
                raise
        parsed = self.parser.parse(response.content)
        parsed["slug"] = self.slugify(title)
        parsed["title"] = title
        parsed["chapter"] = chapter
        return parsed

    def process_documents_chunked(self, title: str, chapter: str, documents: List[Dict[str, str]]) -> dict:
        """
        Token-safe multi-document build:
        1) split large inputs into small chunks
        2) run extraction per chunk
        3) merge extracted structures
        """
        chunk_size_chars = int(os.getenv("KB_CHUNK_SIZE_CHARS", "12000"))
        chunks = self._chunk_documents(documents, chunk_size_chars=chunk_size_chars)
        if not chunks:
            raise ValueError("No non-empty documents provided")

        partials: List[dict] = []
        for idx, chunk in enumerate(chunks, start=1):
            chunk_title = f"{title} (часть {idx})"
            extracted = self.process(chunk_title, chapter, chunk["content"])
            partials.append(extracted)

        merged = self._merge_extractions(partials, title, chapter)
        return merged

    def process_documents_chunked_with_partials(
        self,
        title: str,
        chapter: str,
        documents: List[Dict[str, str]],
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> tuple[dict, List[dict]]:
        chunk_size_chars = int(os.getenv("KB_CHUNK_SIZE_CHARS", "18000"))
        workers = max(1, int(os.getenv("KB_CHUNK_WORKERS", "3")))
        chunks = self._chunk_documents(documents, chunk_size_chars=chunk_size_chars)
        if not chunks:
            raise ValueError("No non-empty documents provided")
        logger.info("KB chunked build started: title='%s', chunks=%s", title, len(chunks))
        if progress_callback is not None:
            progress_callback({"stage": "chunks_ready", "total_chunks": len(chunks)})
        partials_by_idx: Dict[int, dict] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_meta = {}
            for idx, chunk in enumerate(chunks, start=1):
                logger.info("KB submit chunk %s/%s: %s", idx, len(chunks), chunk.get("name", "chunk"))
                if progress_callback is not None:
                    progress_callback(
                        {
                            "stage": "chunk_started",
                            "index": idx,
                            "total": len(chunks),
                            "name": chunk.get("name", ""),
                        }
                    )
                chunk_title = f"{title} (часть {idx})"
                future = executor.submit(self.process, chunk_title, chapter, chunk["content"])
                future_to_meta[future] = (idx, chunk.get("name", ""))

            for future in as_completed(future_to_meta):
                idx, name = future_to_meta[future]
                extracted = future.result()
                partials_by_idx[idx] = extracted
                logger.info("KB chunk done %s/%s: %s", idx, len(chunks), name)
                if progress_callback is not None:
                    progress_callback(
                        {
                            "stage": "chunk_done",
                            "index": idx,
                            "total": len(chunks),
                            "name": name,
                        }
                    )

        partials = [partials_by_idx[i] for i in sorted(partials_by_idx.keys())]
        merged = self._merge_extractions(partials, title, chapter)
        logger.info("KB chunked build finished: title='%s', chunks=%s", title, len(chunks))
        if progress_callback is not None:
            progress_callback({"stage": "chunks_merged", "total_chunks": len(chunks)})
        return merged, partials

    def suggest_title(self, document_text: str, fallback: str = "Документ") -> str:
        logger.info(
            "KB suggest_title started: fallback='%s', preview_chars=%s",
            fallback,
            min(len(document_text or ""), 5000),
        )
        prompt = (
            "Предложи короткий и понятный заголовок базы знаний (2-8 слов) "
            "для данного документа. Верни только заголовок без кавычек."
        )
        preview = document_text[:5000]
        messages = [SystemMessage(content=prompt), HumanMessage(content=preview)]
        try:
            response = self.llm.invoke(messages)
            title = (response.content or "").strip().strip('"').strip("'")
            if title:
                logger.info("KB suggest_title finished: title='%s'", title[:120])
                return title[:120]
        except Exception as exc:
            logger.warning("Auto-title generation failed: %s", exc)
        logger.info("KB suggest_title fallback used: '%s'", fallback)
        return fallback

    def to_markdown(self, extracted: dict, sources: List[str], images: List[str]) -> str:
        logger.info(
            "KB markdown build started: title='%s', sources=%s, images=%s",
            extracted.get("title", ""),
            len(sources or []),
            len(images or []),
        )
        summary = extracted.get("summary", "")
        key_points = extracted.get("key_points", [])
        detailed_outline = extracted.get("detailed_outline", [])
        definitions = extracted.get("definitions", [])
        faqs = extracted.get("faqs", [])
        chapters = extracted.get("chapters", [])
        sources = self._merge_sources_with_web(extracted, sources)

        lines: List[str] = [f"# {extracted['title']}", "", "## Подробная выдержка", "", summary, ""]
        if key_points:
            lines += ["## Ключевые тезисы", ""]
            for point in key_points:
                lines.append(f"- {point}")
            lines.append("")

        if detailed_outline:
            lines += ["## Детальная структура", ""]
            for item in detailed_outline:
                lines.append(f"- {item}")
            lines.append("")

        if chapters:
            lines += ["## Главы документа", ""]
            for idx, chapter in enumerate(chapters, start=1):
                ch_title = chapter.get("title", f"Глава {idx}").strip() or f"Глава {idx}"
                ch_content = chapter.get("content", "").strip()
                anchor = self._anchor_slug(f"chapter-{ch_title}")
                lines.append(f'### <a id="{anchor}"></a>{ch_title}')
                lines.append("")
                if ch_content:
                    lines.append(ch_content)
                    lines.append("")

        if definitions:
            lines += ["## Навигация по определениям", ""]
            for item in definitions:
                term = item.get("term", "").strip()
                if term:
                    def_anchor = self._anchor_slug(f"def-{term}")
                    lines.append(f"- [{term}](#{def_anchor})")
            lines.append("")

            lines += ["## Определения", ""]
            lines.append("| Термин | Определение |")
            lines.append("|---|---|")
            for item in definitions:
                term = item.get("term", "").strip()
                definition = item.get("definition", "").strip()
                if not term:
                    continue
                def_anchor = self._anchor_slug(f"def-{term}")
                term_cell = f'<a id="{def_anchor}"></a> **{term}**'
                def_cell = self._escape_table_cell(definition)
                lines.append(f"| {term_cell} | {def_cell} |")
            lines.append("")

        if faqs:
            lines += ["## Вопросы и ответы", ""]
            lines.append("| Вопрос | Ответ |")
            lines.append("|---|---|")
            for item in faqs:
                q = item.get("question", "").strip()
                a = item.get("answer", "").strip()
                if not (q and a):
                    continue
                q_cell = self._escape_table_cell(q)
                a_cell = self._escape_table_cell(a)
                lines.append(f"| {q_cell} | {a_cell} |")
            lines.append("")

        if images:
            lines += ["## Изображения", ""]
            for idx, image in enumerate(images, start=1):
                lines.append(f"![Изображение {idx}]({image})")
            lines.append("")

        if sources:
            lines += ["## Источники", ""]
            for source in sources:
                lines.append(f"- {source}")
            lines.append("")

        markdown = "\n".join(lines).strip()
        # Make definition terms clickable across the whole page.
        markdown = self._autolink_defined_terms(markdown, definitions)
        logger.info(
            "KB markdown build finished: title='%s', chars=%s",
            extracted.get("title", ""),
            len(markdown),
        )
        return markdown

    def enrich_created_markdown(self, title: str, chapter: str, markdown: str, chunk_results: List[dict]) -> str:
        """
        Editing tool for a freshly created KB article.
        Uses chunk-level insights to supplement missing details.
        """
        if not chunk_results:
            return markdown
        if os.getenv("KB_ENABLE_ENRICH_STEP", "0") not in {"1", "true", "yes"}:
            return markdown
        # Safety guard: avoid another context overflow on very large pages.
        if len(markdown) > int(os.getenv("KB_EDIT_MAX_MARKDOWN_CHARS", "90000")):
            return markdown

        context_blocks: List[str] = []
        for idx, item in enumerate(chunk_results[:50], start=1):
            summary = (item.get("summary") or "").strip()
            points = item.get("key_points") or []
            defs = item.get("definitions") or []
            faqs = item.get("faqs") or []
            context_blocks.append(
                "\n".join(
                    [
                        f"Источник-чанк {idx}",
                        f"summary: {summary[:1000]}",
                        "key_points: " + "; ".join(str(p)[:220] for p in points[:8]),
                        "definitions: " + "; ".join(
                            f"{d.get('term','')}: {str(d.get('definition',''))[:140]}" for d in defs[:6]
                        ),
                        "faqs: " + "; ".join(
                            f"{f.get('question','')} -> {str(f.get('answer',''))[:120]}" for f in faqs[:4]
                        ),
                    ]
                )
            )

        system_prompt = (
            "Ты редактор базы знаний. Тебе дан готовый markdown и дополнительные наблюдения "
            "из чанков документов. Твоя задача: дополнить статью только недостающими фактами, "
            "сохранив текущую структуру. Не удаляй полезный контент. "
            "Можно добавить новые пункты, определения и FAQ, если их не хватает. "
            "Верни только итоговый markdown."
        )
        context_text = "\n\n".join(context_blocks)
        human_prompt = (
            f"Заголовок: {title}\n"
            f"Глава: {chapter}\n\n"
            f"Текущий markdown:\n{markdown}\n\n"
            f"Контекст из чанков:\n{context_text}"
        )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
        try:
            response = self.llm.invoke(messages)
            updated = (response.content or "").strip()
            return updated if updated else markdown
        except Exception as exc:
            logger.warning("KB enrich markdown step failed: %s", exc)
            return markdown

    @staticmethod
    def _escape_table_cell(text: str) -> str:
        # Avoid breaking Markdown table pipes.
        # Keep line breaks inside cells.
        text = str(text or "").replace("|", "&#124;")
        return text.replace("\n", "<br/>")

    @staticmethod
    def _anchor_slug(text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", text.strip().lower()).strip("-")
        return slug or "section"

    def _autolink_defined_terms(self, markdown: str, definitions: List[Dict[str, str]]) -> str:
        terms = [item.get("term", "").strip() for item in definitions if item.get("term", "").strip()]
        # Long terms first to avoid partial replacements.
        terms.sort(key=len, reverse=True)
        out_lines: List[str] = []
        for line in markdown.splitlines():
            stripped = line.strip()
            # Do not inject definition links into headings to avoid noisy sidebar labels.
            if stripped.startswith("#"):
                out_lines.append(line)
                continue

            linked_line = line
            for term in terms:
                anchor = self._anchor_slug(f"def-{term}")
                # Skip terms already inside markdown link syntax.
                pattern = re.compile(rf"(?<!\])\b({re.escape(term)})\b", re.IGNORECASE)
                linked_line = re.sub(pattern, rf"[\1](#{anchor})", linked_line)
            out_lines.append(linked_line)
        return "\n".join(out_lines)

    def _merge_sources_with_web(self, extracted: dict, local_sources: List[str]) -> List[str]:
        if os.getenv("KB_ENABLE_WEB_SOURCES", "0") not in {"1", "true", "yes"}:
            return list(local_sources)
        merged = list(local_sources)
        terms: List[str] = []
        for item in extracted.get("definitions", [])[:5]:
            term = item.get("term", "").strip()
            if term:
                terms.append(term)
        query_parts = [extracted.get("title", "")] + terms
        query = " Беларусь ".join([part for part in query_parts if part]).strip()
        if not query:
            return merged

        try:
            web_sources = search_sources(query, limit=5)
        except Exception as exc:
            logger.warning("Web sources lookup failed: %s", exc)
            return merged

        existing = set(merged)
        for source in web_sources:
            if source.url not in existing:
                merged.append(source.url)
                existing.add(source.url)
        return merged

    def _chunk_documents(self, documents: List[Dict[str, str]], chunk_size_chars: int) -> List[Dict[str, str]]:
        chunks: List[Dict[str, str]] = []
        for idx, doc in enumerate(documents, start=1):
            name = (doc.get("name") or f"Документ {idx}").strip()
            content = (doc.get("content") or "").strip()
            if not content:
                continue
            pieces = self._split_text(content, max_chars=chunk_size_chars)
            for part_idx, piece in enumerate(pieces, start=1):
                chunks.append(
                    {
                        "name": f"{name}#{part_idx}",
                        "content": f"Источник: {name}\nЧасть: {part_idx}\n\n{piece}",
                    }
                )
        return chunks

    @staticmethod
    def _split_text(text: str, max_chars: int = 12000) -> List[str]:
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= max_chars:
            return [text]

        paragraphs = re.split(r"\n\s*\n", text)
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            p_len = len(paragraph) + 2
            if current and current_len + p_len > max_chars:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            # Very large single paragraph: hard split by size.
            if len(paragraph) > max_chars:
                for i in range(0, len(paragraph), max_chars):
                    part = paragraph[i : i + max_chars].strip()
                    if part:
                        if current:
                            chunks.append("\n\n".join(current))
                            current = []
                            current_len = 0
                        chunks.append(part)
                continue
            current.append(paragraph)
            current_len += p_len
        if current:
            chunks.append("\n\n".join(current))
        return chunks

    def _merge_extractions(self, partials: List[dict], title: str, chapter: str) -> dict:
        summaries: List[str] = []
        key_points: List[str] = []
        detailed_outline: List[str] = []
        chapters_out: List[Dict[str, str]] = []
        definitions_map: Dict[str, Dict[str, str]] = {}
        faq_map: Dict[str, Dict[str, str]] = {}

        for part in partials:
            s = (part.get("summary") or "").strip()
            if s:
                summaries.append(s)
            for item in part.get("key_points", []) or []:
                text = str(item).strip()
                if text and text not in key_points:
                    key_points.append(text)
            for item in part.get("detailed_outline", []) or []:
                text = str(item).strip()
                if text and text not in detailed_outline:
                    detailed_outline.append(text)
            for ch in part.get("chapters", []) or []:
                ch_title = str(ch.get("title", "")).strip()
                ch_content = str(ch.get("content", "")).strip()
                if ch_title and ch_content:
                    chapters_out.append({"title": ch_title, "content": ch_content})
            for d in part.get("definitions", []) or []:
                term = str(d.get("term", "")).strip()
                definition = str(d.get("definition", "")).strip()
                if term and definition and term.lower() not in definitions_map:
                    definitions_map[term.lower()] = {"term": term, "definition": definition}
            for f in part.get("faqs", []) or []:
                q = str(f.get("question", "")).strip()
                a = str(f.get("answer", "")).strip()
                if q and a and q.lower() not in faq_map:
                    faq_map[q.lower()] = {"question": q, "answer": a}

        merged_summary = "\n\n".join(summaries[:10]).strip()
        definitions = list(definitions_map.values())
        faqs = list(faq_map.values())

        return {
            "slug": self.slugify(title),
            "title": title,
            "chapter": chapter,
            "summary": merged_summary,
            "key_points": key_points[:40],
            "detailed_outline": detailed_outline[:60],
            "definitions": definitions[:120],
            "faqs": faqs[:80],
            "chapters": chapters_out[:80],
        }
