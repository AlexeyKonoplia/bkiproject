<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { apiFetch, hasToken } from "../lib/api";

const route = useRoute();

const documents = ref([]);
const loadingDocuments = ref(false);
const documentsError = ref("");
const selectedDocument = ref(null);
const contentQuery = ref("");
const matches = ref([]);
const focusedPage = ref(null);
const focusedSource = ref(null);
const documentFilters = ref({
  year: "",
  category: "",
  active: "active",
});

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function pageHtml(page) {
  const raw = page.text || "";
  const excerpt = focusedSource.value?.chunk_text || "";
  if (
    focusedPage.value !== page.page_number ||
    !excerpt ||
    !raw.includes(excerpt)
  ) {
    return escapeHtml(raw);
  }

  const parts = raw.split(excerpt);
  const escapedExcerpt = `<mark>${escapeHtml(excerpt)}</mark>`;
  return parts.map(escapeHtml).join(escapedExcerpt);
}

async function loadDocuments() {
  if (!hasToken.value) return;
  loadingDocuments.value = true;
  documentsError.value = "";
  try {
    const params = new URLSearchParams({
      only_active: documentFilters.value.active === "active" ? "true" : "false",
      limit: "200",
    });
    if (documentFilters.value.year) params.set("doc_year", documentFilters.value.year);
    if (documentFilters.value.category) params.set("doc_category", documentFilters.value.category);
    if (documentFilters.value.active !== "all") {
      params.set("is_active", documentFilters.value.active === "active" ? "true" : "false");
    }
    const payload = await apiFetch(`/api/documents?${params.toString()}`);
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

function formatDateTime(value) {
  if (!value) return "Не указано";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

async function openDocument(documentId, options = {}) {
  selectedDocument.value = await apiFetch(`/api/documents/${documentId}`);
  matches.value = [];
  contentQuery.value = "";

  focusedPage.value = options.pageNumber ?? null;
  focusedSource.value = options.source ?? null;

  await nextTick();
  if (focusedPage.value != null) {
    const pageElement = document.getElementById(`page-${focusedPage.value}`);
    pageElement?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function navigateFromRoute() {
  if (!hasToken.value) return;

  const requestedDocumentId = String(route.query.documentId || "").trim();
  const pageNumber = Number.parseInt(String(route.query.page || ""), 10);
  const chunkId = String(route.query.chunkId || "").trim();

  let source = null;
  if (chunkId) {
    const raw = sessionStorage.getItem(`chat-source:${chunkId}`);
    if (raw) {
      try {
        source = JSON.parse(raw);
      } catch {
        source = null;
      }
    }
  }

  if (requestedDocumentId) {
    await openDocument(requestedDocumentId, {
      pageNumber: Number.isNaN(pageNumber) ? null : pageNumber,
      source,
    });
    return;
  }

  if (!selectedDocument.value && documents.value.length) {
    await openDocument(documents.value[0].id);
  }
}

async function searchInsideDocument() {
  if (!selectedDocument.value || !contentQuery.value.trim()) {
    matches.value = [];
    return;
  }

  const query = encodeURIComponent(contentQuery.value.trim());
  matches.value = await apiFetch(`/api/documents/${selectedDocument.value.id}/search?query=${query}`);
}

onMounted(async () => {
  await loadDocuments();
  await navigateFromRoute();
});

watch(
  () => route.fullPath,
  async () => {
    await navigateFromRoute();
  },
);
</script>

<template>
  <section class="viewer-grid">
    <aside class="page-panel list-panel">
      <div class="panel-head">
        <div>
          <p class="section-tag">Viewer</p>
          <h2>Документы</h2>
        </div>
        <button class="ghost" :disabled="!hasToken || loadingDocuments" @click="loadDocuments">
          Обновить
        </button>
      </div>

      <div class="document-list">
        <div class="filters-grid">
          <select v-model="documentFilters.year" @change="loadDocuments">
            <option value="">Все годы</option>
            <option v-for="year in availableYears" :key="year" :value="year">{{ year }}</option>
          </select>
          <select v-model="documentFilters.category" @change="loadDocuments">
            <option value="">Все категории</option>
            <option v-for="category in availableCategories" :key="category" :value="category">{{ category }}</option>
          </select>
          <select v-model="documentFilters.active" @change="loadDocuments">
            <option value="active">Активные</option>
            <option value="inactive">Неактивные</option>
            <option value="all">Все статусы</option>
          </select>
        </div>

        <button
          v-for="item in documents"
          :key="item.id"
          class="document-item"
          :class="{ selected: selectedDocument?.id === item.id }"
          @click="openDocument(item.id)"
        >
          <strong>{{ item.file_name }}</strong>
          <span>{{ item.doc_category || "Без категории" }}</span>
          <small>{{ item.doc_year || "Без года" }} · {{ item.is_active ? "Активен" : "Неактивен" }}</small>
        </button>
      </div>

      <p v-if="documentsError" class="error-text">{{ documentsError }}</p>
      <p v-if="!hasToken" class="empty-state">Войдите, чтобы открыть страницу просмотра документов.</p>
    </aside>

    <section class="page-panel content-panel">
      <div class="panel-head">
        <div>
          <p class="section-tag">Content</p>
          <h2>{{ selectedDocument?.file_name || "Содержимое документа" }}</h2>
        </div>
      </div>

      <template v-if="selectedDocument">
        <div class="metadata-grid">
          <div>
            <span>Загрузил</span>
            <strong>{{ selectedDocument.uploaded_by_username || selectedDocument.uploaded_by || "Не указано" }}</strong>
          </div>
          <div>
            <span>Дата загрузки</span>
            <strong>{{ formatDateTime(selectedDocument.created_at) }}</strong>
          </div>
          <div>
            <span>Год</span>
            <strong>{{ selectedDocument.doc_year || "Не указан" }}</strong>
          </div>
          <div>
            <span>Статус</span>
            <strong>{{ selectedDocument.is_active ? "Активен" : "Неактивен" }}</strong>
          </div>
          <div class="metadata-wide">
            <span>Описание</span>
            <strong>{{ selectedDocument.description || "Описание не добавлено" }}</strong>
          </div>
        </div>

        <div v-if="focusedSource" class="focus-banner">
          <strong>Фрагмент из ответа модели</strong>
          <p>{{ focusedSource.chunk_text }}</p>
        </div>

        <div class="search-row">
          <input
            v-model="contentQuery"
            type="text"
            placeholder="Поиск по содержимому выбранного документа"
            @keyup.enter="searchInsideDocument"
          />
          <button class="ghost" @click="searchInsideDocument">Искать</button>
        </div>

        <div v-if="matches.length" class="matches">
          <article v-for="match in matches" :key="match.chunk_id" class="match-card">
            <strong>Страница {{ match.page_number + 1 }}</strong>
            <p>{{ match.snippet }}</p>
          </article>
        </div>

        <div class="pages">
          <article
            v-for="page in selectedDocument.pages"
            :id="`page-${page.page_number}`"
            :key="page.page_number"
            class="page-card"
            :class="{ focused: focusedPage === page.page_number }"
          >
            <div class="page-head">Страница {{ page.page_number + 1 }}</div>
            <pre v-html="pageHtml(page)"></pre>
          </article>
        </div>
      </template>

      <div v-else class="empty-state">
        Выберите документ слева, и справа откроется его полное содержимое.
      </div>
    </section>
  </section>
</template>

<style scoped>
.viewer-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.8fr) minmax(0, 1.6fr);
  gap: 12px;
}

.page-panel {
  border: 1px solid var(--border);
  background: var(--surface);
  padding: 20px;
  color: var(--text);
}

.panel-head,
.search-row {
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

.document-list,
.pages,
.matches {
  display: grid;
  gap: 12px;
}

.document-item,
.ghost,
input,
select {
  font: inherit;
}

.document-item {
  display: grid;
  gap: 4px;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--surface-soft);
  color: var(--text);
  padding: 12px 14px;
  cursor: pointer;
}

.document-item span {
  color: var(--muted);
}

.document-item.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
}

.document-item.selected span {
  color: var(--muted);
}

input {
  flex: 1;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  padding: 12px 14px;
}

select {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  padding: 12px 14px;
}

.filters-grid {
  display: grid;
  gap: 8px;
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.metadata-grid > div {
  border: 1px solid var(--border);
  background: var(--surface-soft);
  padding: 12px;
  display: grid;
  gap: 4px;
}

.metadata-grid span {
  color: var(--muted);
  font-size: 0.82rem;
}

.metadata-grid strong {
  color: var(--text);
  overflow-wrap: anywhere;
}

.metadata-wide {
  grid-column: 1 / -1;
}

.ghost {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  padding: 12px 16px;
  cursor: pointer;
  font-weight: 700;
}

.focus-banner,
.page-card,
.match-card {
  border: 1px solid var(--border);
  background: var(--surface);
  padding: 16px;
}

.focus-banner {
  margin-bottom: 12px;
  background: var(--accent-soft);
  border-color: #cfe0ff;
}

.page-card.focused {
  border-color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent);
}

.page-head {
  font-weight: 700;
  color: var(--accent);
}

pre {
  margin: 12px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "Consolas", "Lucida Console", monospace;
  color: var(--text);
}

:deep(mark) {
  background: #fff3b2;
  color: var(--text);
  padding: 0 2px;
}

.error-text {
  color: var(--danger);
}

.empty-state {
  color: var(--muted);
}

@media (max-width: 1100px) {
  .viewer-grid {
    grid-template-columns: 1fr;
  }

  .metadata-grid {
    grid-template-columns: 1fr;
  }
}
</style>
