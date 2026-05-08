<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { apiFetch, hasToken } from "../lib/api";

const router = useRouter();

const loadingDocuments = ref(false);
const documentsError = ref("");
const documents = ref([]);
const selectedDocumentId = ref("");
const selectedDocumentLabel = ref("");
const pinnedDocumentIds = ref(JSON.parse(localStorage.getItem("bki-pinned-context-documents") || "[]"));
const documentFilters = ref({
  year: "",
  category: "",
  active: "active",
});
const answerMode = ref("detailed");

const answerModes = [
  { value: "brief", label: "Краткий ответ" },
  { value: "detailed", label: "Подробный разбор" },
  { value: "extract", label: "Извлечение данных" },
];

const chatMessages = ref([
  {
    role: "assistant",
    content:
      "Выберите документ для контекста или оставьте поиск по всей базе, затем задайте вопрос в чате.",
    sources: [],
  },
]);
const chatInput = ref("");
const chatLoading = ref(false);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
    .replace(/_([^_\n]+)_/g, "<em>$1</em>")
    .replace(/\[(source\d+)\]/gi, '<span class="source-ref">[$1]</span>');
}

function renderMarkdown(value) {
  const lines = String(value ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listItems = [];
  let listType = "";
  let codeLines = [];
  let inCode = false;

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  }

  function flushList() {
    if (!listItems.length) return;
    const tag = listType === "ol" ? "ol" : "ul";
    blocks.push(`<${tag}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${tag}>`);
    listItems = [];
    listType = "";
  }

  function flushCode() {
    if (!codeLines.length) return;
    blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    codeLines = [];
  }

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length + 2;
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const nextType = ordered ? "ol" : "ul";
      if (listType && listType !== nextType) flushList();
      listType = nextType;
      listItems.push((unordered || ordered)[1]);
      continue;
    }

    if (line.startsWith(">")) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${renderInlineMarkdown(line.replace(/^>\s?/, ""))}</blockquote>`);
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  flushCode();
  flushParagraph();
  flushList();

  return blocks.join("");
}

async function loadDocuments() {
  if (!hasToken.value) return;

  loadingDocuments.value = true;
  documentsError.value = "";
  try {
    const payload = await apiFetch("/api/documents?only_active=false&limit=200");
    documents.value = payload.items || [];
  } catch (error) {
    documentsError.value = error.message || String(error);
  } finally {
    loadingDocuments.value = false;
  }
}

const availableYears = computed(() => {
  return [...new Set(documents.value.map((item) => item.doc_year).filter(Boolean))].sort((a, b) => b - a);
});

const availableCategories = computed(() => {
  return [...new Set(documents.value.flatMap((item) => item.categories || []))].sort((a, b) => a.localeCompare(b, "ru"));
});

const filteredDocuments = computed(() => {
  const filtered = documents.value.filter((item) => {
    if (documentFilters.value.year && String(item.doc_year || "") !== String(documentFilters.value.year)) return false;
    if (documentFilters.value.category && !(item.categories || []).includes(documentFilters.value.category)) return false;
    if (documentFilters.value.active === "active" && !item.is_active) return false;
    if (documentFilters.value.active === "inactive" && item.is_active) return false;
    return true;
  });

  return filtered.sort((a, b) => {
    const aPinned = pinnedDocumentIds.value.includes(a.id);
    const bPinned = pinnedDocumentIds.value.includes(b.id);
    if (aPinned !== bPinned) return aPinned ? -1 : 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
});

function selectDocument(item) {
  selectedDocumentId.value = item?.id || "";
  selectedDocumentLabel.value = item?.file_name || "";
}

function togglePinnedDocument(item) {
  const next = new Set(pinnedDocumentIds.value);
  if (next.has(item.id)) {
    next.delete(item.id);
  } else {
    next.add(item.id);
  }
  pinnedDocumentIds.value = [...next];
  localStorage.setItem("bki-pinned-context-documents", JSON.stringify(pinnedDocumentIds.value));
}

function openSourceReference(source) {
  if (!source?.source_document_id || source.page_number == null) {
    return;
  }

  sessionStorage.setItem(`chat-source:${source.chunk_id}`, JSON.stringify(source));
  router.push({
    path: "/documents",
    query: {
      documentId: source.source_document_id,
      page: String(source.page_number),
      chunkId: source.chunk_id,
    },
  });
}

async function sendChatMessage() {
  const message = chatInput.value.trim();
  if (!message || chatLoading.value || !hasToken.value) return;

  chatMessages.value.push({
    role: "user",
    content: message,
    sources: [],
  });
  chatInput.value = "";
  chatLoading.value = true;

  try {
    const payload = await apiFetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        history: chatMessages.value.map((item) => ({
          role: item.role,
          content: item.content,
        })),
        source_document_id: selectedDocumentId.value || null,
        doc_year_from: !selectedDocumentId.value && documentFilters.value.year ? Number(documentFilters.value.year) : null,
        doc_year_to: !selectedDocumentId.value && documentFilters.value.year ? Number(documentFilters.value.year) : null,
        doc_category: !selectedDocumentId.value && documentFilters.value.category ? documentFilters.value.category : null,
        answer_mode: answerMode.value,
      }),
    });

    chatMessages.value.push({
      role: "assistant",
      content: payload.answer_text,
      sources: payload.sources || [],
    });
  } catch (error) {
    chatMessages.value.push({
      role: "assistant",
      content: `Ошибка запроса: ${error.message || String(error)}`,
      sources: [],
    });
  } finally {
    chatLoading.value = false;
  }
}

onMounted(async () => {
  await loadDocuments();
});
</script>

<template>
  <section class="page-grid">
    <aside class="page-panel selector">
      <div class="panel-head">
        <div>
          <p class="section-tag">Main</p>
          <h2>Контекст для чата</h2>
        </div>
        <button class="ghost" :disabled="!hasToken || loadingDocuments" @click="loadDocuments">
          Обновить
        </button>
      </div>

      <p class="hint">
        На этой странице остаётся только выбор документа для контекста и диалог с моделью.
      </p>

      <div class="filters-grid">
        <select v-model="documentFilters.year">
          <option value="">Все годы</option>
          <option v-for="year in availableYears" :key="year" :value="year">{{ year }}</option>
        </select>
        <select v-model="documentFilters.category">
          <option value="">Все категории</option>
          <option v-for="category in availableCategories" :key="category" :value="category">{{ category }}</option>
        </select>
        <select v-model="documentFilters.active">
          <option value="active">Активные</option>
          <option value="inactive">Неактивные</option>
          <option value="all">Все статусы</option>
        </select>
      </div>

      <button
        class="document-item clear"
        :class="{ selected: !selectedDocumentId }"
        :disabled="!hasToken"
        @click="selectDocument(null)"
      >
        Вся база документов
      </button>

      <button
        v-for="item in filteredDocuments"
        :key="item.id"
        class="document-item"
        :class="{ selected: selectedDocumentId === item.id }"
        :disabled="!hasToken"
        @click="selectDocument(item)"
      >
        <span class="document-title-line">
          <strong>{{ item.file_name }}</strong>
          <button
            class="pin-button"
            :class="{ pinned: pinnedDocumentIds.includes(item.id) }"
            type="button"
            :title="pinnedDocumentIds.includes(item.id) ? 'Открепить' : 'Закрепить сверху'"
            @click.stop="togglePinnedDocument(item)"
          >
            {{ pinnedDocumentIds.includes(item.id) ? "★" : "☆" }}
          </button>
        </span>
        <span>{{ item.doc_category || "Без категории" }}</span>
        <small>{{ item.doc_year || "Без года" }} · {{ item.is_active ? "Активен" : "Неактивен" }}</small>
      </button>

      <p v-if="documentsError" class="error-text">{{ documentsError }}</p>
      <p v-if="!hasToken" class="empty-state">Войдите, чтобы выбирать документ для контекста.</p>
    </aside>

    <section class="page-panel chat-panel">
      <div class="panel-head">
        <div>
          <p class="section-tag">Chat</p>
          <h2>Вопросы к модели</h2>
        </div>
        <div class="context-badge">
          {{ selectedDocumentLabel ? `Контекст: ${selectedDocumentLabel}` : "Контекст: вся база" }}
        </div>
      </div>

      <div class="chat-log">
        <article
          v-for="(message, index) in chatMessages"
          :key="`${message.role}-${index}`"
          class="message-card"
          :class="message.role"
        >
          <span class="message-role">{{ message.role === "assistant" ? "Ассистент" : "Вы" }}</span>
          <div class="markdown-body" v-html="renderMarkdown(message.content)"></div>
          <div v-if="message.sources?.length" class="source-list">
            <button
              v-for="source in message.sources"
              :key="source.chunk_id"
              class="source-card"
              @click="openSourceReference(source)"
            >
              <strong>{{ source.file_name }} · стр. {{ source.page_number }}</strong>
              <span>{{ source.chunk_text }}</span>
            </button>
          </div>
        </article>
      </div>

      <div class="compose-box">
        <div class="mode-row">
          <button
            v-for="mode in answerModes"
            :key="mode.value"
            class="mode-button"
            :class="{ selected: answerMode === mode.value }"
            type="button"
            @click="answerMode = mode.value"
          >
            {{ mode.label }}
          </button>
        </div>
        <textarea
          v-model="chatInput"
          placeholder="Например: кратко объясни ключевые положения выбранного документа"
          :disabled="!hasToken || chatLoading"
          @keyup.ctrl.enter="sendChatMessage"
        />
        <div class="compose-actions">
          <small>`Ctrl+Enter` тоже отправляет сообщение</small>
          <button class="primary" :disabled="!hasToken || chatLoading" @click="sendChatMessage">
            {{ chatLoading ? "Отправка..." : "Спросить модель" }}
          </button>
        </div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.page-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(0, 1.6fr);
  gap: 12px;
}

.page-panel {
  border: 1px solid var(--border);
  background: var(--surface);
  padding: 20px;
  color: var(--text);
}

.selector,
.chat-panel {
  display: grid;
  gap: 14px;
  align-content: start;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.section-tag {
  margin: 0 0 6px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 0.75rem;
  color: var(--accent);
}

.hint,
.empty-state,
.error-text,
.context-badge,
small {
  color: var(--muted);
}

.context-badge {
  padding: 8px 12px;
  border: 1px solid var(--border);
  background: var(--accent-soft);
}

.document-item,
.primary,
.ghost,
select,
.mode-button {
  padding: 12px 14px;
  font: inherit;
}

.document-item {
  display: grid;
  gap: 4px;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--surface-soft);
  color: var(--text);
  cursor: pointer;
}

.document-item span {
  color: var(--muted);
}

.document-title-line {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.pin-button {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--muted);
  width: 32px;
  height: 32px;
  cursor: pointer;
}

.pin-button.pinned {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
}

.document-item.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
}

.document-item.selected span {
  color: var(--muted);
}

.clear {
  font-weight: 700;
}

.chat-log {
  display: grid;
  gap: 12px;
  max-height: 58vh;
  overflow: auto;
  padding-right: 4px;
}

.message-card {
  border: 1px solid var(--border);
  background: var(--surface);
  padding: 16px;
}

.message-card.user {
  background: var(--accent-soft);
}

.message-card.assistant {
  background: var(--surface-soft);
}

.message-role {
  display: block;
  margin-bottom: 8px;
  text-transform: uppercase;
  font-size: 0.8rem;
  letter-spacing: 0.08em;
  color: var(--accent);
}

.markdown-body {
  color: var(--text);
  line-height: 1.58;
}

.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol),
.markdown-body :deep(blockquote),
.markdown-body :deep(pre),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5) {
  margin: 0 0 12px;
}

.markdown-body :deep(p:last-child),
.markdown-body :deep(ul:last-child),
.markdown-body :deep(ol:last-child),
.markdown-body :deep(blockquote:last-child),
.markdown-body :deep(pre:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5) {
  color: var(--text);
  line-height: 1.25;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 22px;
}

.markdown-body :deep(li + li) {
  margin-top: 6px;
}

.markdown-body :deep(code) {
  border: 1px solid var(--border);
  background: var(--surface-muted);
  color: var(--text);
  padding: 2px 5px;
  font-family: "Consolas", "Lucida Console", monospace;
  font-size: 0.92em;
}

.markdown-body :deep(pre) {
  overflow: auto;
  border: 1px solid var(--border);
  background: var(--surface);
  padding: 12px;
}

.markdown-body :deep(pre code) {
  border: 0;
  background: transparent;
  padding: 0;
  white-space: pre;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--accent);
  padding-left: 12px;
  color: var(--muted);
}

.markdown-body :deep(.source-ref) {
  display: inline-block;
  border: 1px solid var(--border);
  background: var(--accent-soft);
  color: var(--accent);
  padding: 0 5px;
  font-weight: 700;
}

.source-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.source-card {
  display: grid;
  gap: 6px;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--surface-muted);
  padding: 12px 14px;
  cursor: pointer;
  color: var(--text);
  font: inherit;
}

.source-card span {
  color: var(--muted);
  line-height: 1.45;
}

.compose-box {
  display: grid;
  gap: 12px;
}

.filters-grid,
.mode-row {
  display: grid;
  gap: 8px;
}

.filters-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

select {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
}

.mode-row {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.mode-button {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  font-weight: 700;
}

.mode-button.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
}

textarea {
  min-height: 110px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  padding: 14px;
  resize: vertical;
  font: inherit;
}

.compose-actions {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.primary,
.ghost {
  border: 1px solid transparent;
  cursor: pointer;
  font-weight: 700;
}

.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--inverse);
}

.ghost {
  background: var(--surface);
  border-color: var(--border);
  color: var(--text);
}

.error-text {
  color: var(--danger);
}

@media (max-width: 1100px) {
  .page-grid {
    grid-template-columns: 1fr;
  }

  .filters-grid,
  .mode-row {
    grid-template-columns: 1fr;
  }
}
</style>
