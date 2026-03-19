const askBtn = document.getElementById("ask-btn");
const saveBtn = document.getElementById("save-btn");
const chatNode = document.getElementById("rag-chat");
const typingStatusNode = document.getElementById("typing-status");
const questionNode = document.getElementById("rag-question");
const allowEditNode = document.getElementById("allow-edit");
const mdEditor = document.getElementById("md-editor");
const sidebarSearchNode = document.getElementById("sidebar-search");

const pageSlug = document.body.dataset.slug;
const BRAILLE_FRAMES = ["⣾", "⣷", "⣯", "⣟"];
let typingTimer = null;
const SIDEBAR_HIGHLIGHT_CLASS = "sidebar-match";

if (askBtn) {
  askBtn.addEventListener("click", async () => {
    const question = questionNode.value.trim();
    if (!question) return;
    appendMessage("user", question);
    questionNode.value = "";
    autoResizeQuestion();
    askBtn.disabled = true;
    askBtn.classList.add("is-busy");
    startTypingStatus();

    // Create assistant bubble immediately.
    const msg = document.createElement("div");
    msg.className = "msg msg-assistant";
    const textNode = document.createElement("div");
    textNode.className = "assistant-answer-text";
    textNode.textContent = "";
    msg.appendChild(textNode);
    chatNode.appendChild(msg);
    chatNode.scrollTop = chatNode.scrollHeight;

    let metaRendered = false;
    let buffer = "";
    const sourcesMetaContainer = document.createElement("div");
    sourcesMetaContainer.className = "msg-meta";
    msg.appendChild(sourcesMetaContainer);

    try {
      const response = await fetch("/kb/ask/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          source_slug: pageSlug,
          allow_edit: Boolean(allowEditNode && allowEditNode.checked),
          target_slug: pageSlug,
        }),
      });

      if (!response.ok || !response.body) {
        textNode.textContent = "Ошибка запроса к чату";
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n");
        buffer = parts.pop() || "";
        for (const line of parts) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          let obj = null;
          try {
            obj = JSON.parse(trimmed);
          } catch (_) {
            continue;
          }

          if (obj.type === "token") {
            textNode.textContent += String(obj.value || "");
            chatNode.scrollTop = chatNode.scrollHeight;
          } else if (obj.type === "meta" && !metaRendered) {
            metaRendered = true;
            sourcesMetaContainer.innerHTML = "";
            const sources = Array.isArray(obj.sources) ? obj.sources : [];
            sources.forEach((s) => sourcesMetaContainer.appendChild(renderSourceCard(s)));
          } else if (obj.type === "error") {
            textNode.textContent = obj.detail || "Ошибка генерации";
          } else if (obj.type === "done") {
            // nothing
          }
        }
      }
    } catch (err) {
      textNode.textContent = `Ошибка сети: ${err?.message || "unknown error"}`;
    } finally {
      stopTypingStatus();
      askBtn.disabled = false;
      askBtn.classList.remove("is-busy");
    }
  });
}

if (questionNode) {
  autoResizeQuestion();
  questionNode.addEventListener("input", autoResizeQuestion);
  questionNode.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (askBtn && !askBtn.disabled) askBtn.click();
    }
  });
}

if (saveBtn) {
  saveBtn.addEventListener("click", async () => {
    const markdown = mdEditor.value;
    const response = await fetch(`/kb/${pageSlug}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown }),
    });

    if (response.ok) {
      window.location.reload();
    } else {
      const err = await response.json();
      alert(`Ошибка сохранения: ${err.detail || "unknown error"}`);
    }
  });
}

if (sidebarSearchNode) {
  indexSidebarBySectionText();
  sidebarSearchNode.addEventListener("input", () => filterSidebarChapters(sidebarSearchNode.value));
}

function appendMessage(role, text) {
  if (!chatNode) return;
  const msg = document.createElement("div");
  msg.className = `msg msg-${role}`;
  msg.textContent = text;
  chatNode.appendChild(msg);
  chatNode.scrollTop = chatNode.scrollHeight;
}

function autoResizeQuestion() {
  if (!questionNode) return;
  questionNode.style.height = "auto";
  const maxHeight = 140;
  const next = Math.min(questionNode.scrollHeight, maxHeight);
  questionNode.style.height = `${Math.max(36, next)}px`;
  questionNode.style.overflowY = questionNode.scrollHeight > maxHeight ? "auto" : "hidden";
}

async function appendAssistantAnswer(answerText) {
  if (!chatNode) return;
  const lines = String(answerText)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const primaryLine = lines.find((line) => line.startsWith("Ответ:")) || lines[0] || "";
  const answer = primaryLine.replace(/^Ответ:\s*/, "");
  const sourceLines = lines.filter((line) => line.startsWith("- SOURCE|"));

  const msg = document.createElement("div");
  msg.className = "msg msg-assistant";

  const textNode = document.createElement("div");
  textNode.className = "assistant-answer-text";
  textNode.textContent = "";
  msg.appendChild(textNode);

  chatNode.appendChild(msg);
  chatNode.scrollTop = chatNode.scrollHeight;

  await typeText(textNode, answer);

  if (sourceLines.length > 0) {
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    sourceLines
      .slice(0, 3)
      .map((line) => parseSourceLine(line.replace(/^-+\s*/, "")))
      .filter(Boolean)
      .forEach((source) => {
        meta.appendChild(renderSourceCard(source));
      });
    msg.appendChild(meta);
  }
  chatNode.scrollTop = chatNode.scrollHeight;
}

function parseSourceLine(rawSourceLine) {
  const parts = String(rawSourceLine || "").split("|");
  if (parts.length < 5) return null;
  // Compatible with both old and new source formats.
  const encTitle = parts[1] || "";
  const encChapter = parts[2] || "";
  const encLink = parts[3] || "";
  const encPreview = parts[4] || "";
  const encHighlight = parts.length > 5 ? parts.slice(5).join("|") : encPreview;
  return {
    title: safeDecode(encTitle) || "Источник",
    chapter: safeDecode(encChapter) || "Раздел",
    link: safeDecode(encLink) || "/kb/",
    preview: safeDecode(encPreview),
    highlightText: safeDecode(encHighlight) || safeDecode(encPreview),
  };
}

function renderSourceCard(source) {
  if (!isRenderableSource(source)) {
    return document.createDocumentFragment();
  }
  const card = document.createElement("div");
  card.className = "source-card";

  const titleNode = document.createElement("a");
  titleNode.className = "source-card-title";
  const hl = encodeURIComponent(String(source.highlightText || source.preview || ""));
  titleNode.href = `${source.link}?hl=${hl}`;
  titleNode.textContent = `${source.title} · ${source.chapter}`;
  titleNode.addEventListener("click", (event) => {
    event.preventDefault();
    showWhere(source.link, source.highlightText);
  });
  card.appendChild(titleNode);

  const evidenceText = String(source.evidenceText || source.highlightText || source.preview || "").trim();
  if (evidenceText) {
    const evidence = document.createElement("div");
    evidence.className = "source-evidence";
    evidence.textContent = evidenceText;
    card.appendChild(evidence);
  }

  return card;
}

function isRenderableSource(source) {
  if (!source || typeof source !== "object") return false;
  const link = String(source.link || "").trim();
  const highlightText = String(source.highlightText || "").trim();
  if (!link.startsWith("/kb/")) return false;
  if (highlightText.length < 5) return false;
  return true;
}

function typeText(node, text) {
  return new Promise((resolve) => {
    const content = String(text || "");
    if (!content) {
      resolve();
      return;
    }
    let idx = 0;
    const step = () => {
      idx += Math.max(1, Math.ceil(content.length / 120));
      node.textContent = content.slice(0, idx);
      if (chatNode) chatNode.scrollTop = chatNode.scrollHeight;
      if (idx < content.length) {
        window.requestAnimationFrame(step);
      } else {
        resolve();
      }
    };
    step();
  });
}

highlightQuerySnippet();
setupDefinitionHoverHighlight();

function highlightQuerySnippet() {
  const params = new URLSearchParams(window.location.search);
  const hl = params.get("hl");
  if (!hl) return;
  const target = document.querySelector(".markdown");
  if (!target) return;
  clearHighlights();
  const ok = highlightWithFallback(target, hl);
  if (!ok) return;
  const marked = target.querySelector("mark.kb-highlight");
  if (marked) {
    marked.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function setupDefinitionHoverHighlight() {
  const target = document.querySelector(".markdown");
  if (!target) return;

  const defLinks = target.querySelectorAll('a[href^="#def-"]');
  if (!defLinks || defLinks.length === 0) return;

  let active = null;

  const clear = () => {
    if (!active) return;
    active.classList.remove("kb-def-hover");
    active = null;
  };

  defLinks.forEach((link) => {
    link.addEventListener("mouseenter", () => {
      const hash = link.getAttribute("href");
      if (!hash) return;
      const defAnchor = document.querySelector(hash);
      if (!defAnchor) return;
      const container = defAnchor.closest("li") || defAnchor.parentElement;
      if (!container) return;
      clear();
      active = container;
      active.classList.add("kb-def-hover");
    });
    link.addEventListener("mouseleave", () => clear());
  });
}

function highlightTextNode(root, needle) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const candidates = buildSearchCandidates(needle);
  if (candidates.length === 0) return false;
  let node;
  while ((node = walker.nextNode())) {
    const value = node.nodeValue || "";
    const rawLower = value.toLowerCase();
    let matchedRaw = "";
    let rawIndex = -1;
    for (const candidate of candidates) {
      const testIdx = rawLower.indexOf(candidate.toLowerCase());
      if (testIdx !== -1) {
        matchedRaw = candidate;
        rawIndex = testIdx;
        break;
      }
    }
    if (rawIndex === -1) continue;
    const before = value.slice(0, rawIndex);
    const match = value.slice(rawIndex, rawIndex + matchedRaw.length);
    const after = value.slice(rawIndex + matchedRaw.length);

    const parent = node.parentNode;
    if (!parent) return false;

    const beforeNode = document.createTextNode(before);
    const mark = document.createElement("mark");
    mark.className = "kb-highlight";
    mark.textContent = match;
    const afterNode = document.createTextNode(after);

    parent.replaceChild(afterNode, node);
    parent.insertBefore(mark, afterNode);
    parent.insertBefore(beforeNode, mark);
    return true;
  }
  return false;
}

// Make highlight more reliable: try multiple attempts.
function highlightWithFallback(root, excerpt) {
  const attempts = buildSearchCandidates(excerpt);
  for (const a of attempts) {
    if (highlightTextNode(root, a)) return true;
  }

  const blocks = root.querySelectorAll("p, li, td, th, h1, h2, h3, h4, h5");
  for (const block of blocks) {
    const blockText = normalizeText(block.textContent || "");
    if (!blockText) continue;
    for (const a of attempts) {
      if (blockText.includes(normalizeText(a)) && highlightTextNode(block, a)) {
        return true;
      }
    }
  }
  return false;
}

function buildSearchCandidates(text) {
  const attempts = [];
  const source = String(text || "").trim();
  const norm = normalizeText(source);
  if (!norm) return attempts;
  attempts.push(source);
  const key = extractKeyPhrase(source);
  if (key) attempts.push(key);
  const words = norm.split(" ").filter(Boolean);
  if (words.length > 12) attempts.push(words.slice(0, 12).join(" "));
  if (words.length > 8) attempts.push(words.slice(0, 8).join(" "));
  if (words.length > 5) attempts.push(words.slice(0, 6).join(" "));
  return Array.from(new Set(attempts.map((x) => x.trim()).filter(Boolean)));
}

function filterSidebarChapters(query) {
  const needle = normalizeText(query);
  const chapters = document.querySelectorAll(".sidebar .chapter");
  chapters.forEach((chapter) => {
    chapter.classList.remove(SIDEBAR_HIGHLIGHT_CLASS);
    const title = chapter.dataset.title || "";
    const sectionText = chapter.dataset.content || "";
    if (!needle) {
      chapter.style.display = "";
      return;
    }
    const haystack = `${title} ${sectionText}`;
    const match = normalizeText(haystack).includes(needle);
    chapter.style.display = match ? "" : "none";
    if (match) {
      chapter.classList.add(SIDEBAR_HIGHLIGHT_CLASS);
    }
  });
}

function indexSidebarBySectionText() {
  const markdown = document.querySelector(".markdown");
  if (!markdown) return;
  const chapterNodes = Array.from(document.querySelectorAll(".sidebar .chapter"));
  if (chapterNodes.length === 0) return;

  const anchors = Array.from(markdown.querySelectorAll("h2 a[id], h3 a[id], h4 a[id]"));
  const index = new Map();
  for (const anchor of anchors) {
    const id = anchor.getAttribute("id");
    if (!id) continue;
    const heading = anchor.closest("h2,h3,h4");
    if (!heading) continue;
    let text = "";
    let node = heading.nextElementSibling;
    while (node && !/^H[234]$/.test(node.tagName)) {
      text += ` ${node.textContent || ""}`;
      node = node.nextElementSibling;
    }
    index.set(id, normalizeText(text).slice(0, 3000));
  }

  chapterNodes.forEach((chapter) => {
    const link = chapter.querySelector("a[href^='#']");
    if (!link) return;
    const href = link.getAttribute("href") || "";
    const anchor = href.replace(/^#/, "").trim();
    if (!anchor) return;
    chapter.dataset.content = index.get(anchor) || "";
  });
}

function showWhere(link, excerpt, clickedButton) {
  const targetPath = normalizePath(new URL(link, window.location.origin).pathname);
  const currentPath = normalizePath(window.location.pathname);
  setActiveSourceButton(clickedButton);
  if (targetPath === currentPath) {
    clearHighlights();
    const target = document.querySelector(".markdown");
    if (!target) return;
    const ok = highlightWithFallback(target, excerpt);
    if (ok) {
      const mark = target.querySelector("mark.kb-highlight");
      if (mark) mark.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const blockFound = highlightBlockFallback(target, excerpt);
    if (blockFound) {
      const block = target.querySelector(".kb-highlight-block");
      if (block) block.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    return;
  }
  const targetUrl = `${link}?hl=${encodeURIComponent(excerpt || "")}`;
  window.open(targetUrl, "_blank", "noopener,noreferrer");
}

function clearHighlights() {
  document.querySelectorAll("mark.kb-highlight").forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) return;
    const textNode = document.createTextNode(mark.textContent || "");
    parent.replaceChild(textNode, mark);
    parent.normalize();
  });
  document.querySelectorAll(".kb-highlight-block").forEach((node) => {
    node.classList.remove("kb-highlight-block");
  });
}

function highlightBlockFallback(root, excerpt) {
  const candidates = buildSearchCandidates(excerpt).map((c) => normalizeText(c));
  if (candidates.length === 0) return false;
  const blocks = root.querySelectorAll("p, li, td, th, h1, h2, h3, h4, h5, blockquote");
  for (const block of blocks) {
    const blockText = normalizeText(block.textContent || "");
    if (!blockText) continue;
    if (candidates.some((cand) => blockText.includes(cand))) {
      block.classList.add("kb-highlight-block");
      return true;
    }
  }
  return false;
}

function normalizeText(text) {
  return String(text)
    .toLowerCase()
    .replace(/[.,;:!?()"«»]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractKeyPhrase(text) {
  const words = normalizeText(text).split(" ").filter(Boolean);
  if (words.length < 4) return "";
  return words.slice(0, Math.min(8, words.length)).join(" ");
}

function safeDecode(value) {
  try {
    return decodeURIComponent(value || "");
  } catch (_) {
    return String(value || "");
  }
}

function normalizePath(pathname) {
  const cleaned = String(pathname || "").trim();
  if (!cleaned) return "/";
  return cleaned.replace(/\/+$/, "") || "/";
}

function setActiveSourceButton(buttonNode) {
  document.querySelectorAll(".download-btn.active-highlight").forEach((btn) => {
    btn.classList.remove("active-highlight");
  });
  if (buttonNode) {
    buttonNode.classList.add("active-highlight");
  }
}

function startTypingStatus() {
  if (!typingStatusNode) return;
  stopTypingStatus();
  let frameIdx = 0;
  typingStatusNode.textContent = `${BRAILLE_FRAMES[frameIdx]} Система печатает`;
  typingStatusNode.classList.add("visible");
  typingTimer = window.setInterval(() => {
    frameIdx = (frameIdx + 1) % BRAILLE_FRAMES.length;
    typingStatusNode.textContent = `${BRAILLE_FRAMES[frameIdx]} Система печатает`;
  }, 180);
}

function stopTypingStatus() {
  if (!typingStatusNode) return;
  if (typingTimer) {
    clearInterval(typingTimer);
    typingTimer = null;
  }
  typingStatusNode.classList.remove("visible");
  typingStatusNode.textContent = "";
}
