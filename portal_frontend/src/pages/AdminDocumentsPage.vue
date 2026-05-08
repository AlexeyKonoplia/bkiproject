<script setup>
import { computed, onMounted, ref } from "vue";

import { apiFetch, hasToken, isAdmin } from "../lib/api";

const uploadForm = ref({
  file: null,
  docYear: "",
  categoriesText: "",
  description: "",
  isActive: true,
});
const uploadLoading = ref(false);
const uploadResult = ref("");

const documents = ref([]);
const loadingDocuments = ref(false);
const documentsError = ref("");
const actionLoadingId = ref("");
const categoryDrafts = ref({});
const metadataDrafts = ref({});
const documentFilters = ref({
  year: "",
  category: "",
  active: "all",
});

function parseCategoriesText(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function categoriesToText(categories) {
  return (categories || []).join(", ");
}

function syncCategoryDrafts(items) {
  const nextDrafts = {};
  const nextMetadataDrafts = {};
  for (const item of items) {
    nextDrafts[item.id] = categoriesToText(item.categories);
    nextMetadataDrafts[item.id] = {
      fileName: item.file_name || "",
      description: item.description || "",
      docYear: item.doc_year || "",
    };
  }
  categoryDrafts.value = nextDrafts;
  metadataDrafts.value = nextMetadataDrafts;
}

async function loadDocuments() {
  if (!hasToken.value || !isAdmin.value) return;
  loadingDocuments.value = true;
  documentsError.value = "";
  try {
    const payload = await apiFetch("/api/documents?only_active=false&limit=200");
    documents.value = payload.items || [];
    syncCategoryDrafts(documents.value);
  } catch (error) {
    documentsError.value = error.message || String(error);
  } finally {
    loadingDocuments.value = false;
  }
}

function onFileChange(event) {
  uploadForm.value.file = event.target.files?.[0] || null;
}

async function uploadDocument() {
  if (!uploadForm.value.file) {
    uploadResult.value = "Выберите PDF или DOCX файл.";
    return;
  }

  uploadLoading.value = true;
  uploadResult.value = "";
  try {
    const formData = new FormData();
    formData.append("file", uploadForm.value.file);
    if (uploadForm.value.docYear) {
      formData.append("doc_year", uploadForm.value.docYear);
    }

    const categories = parseCategoriesText(uploadForm.value.categoriesText);
    if (categories.length) {
      formData.append("doc_category", categories.join(", "));
    }
    if (uploadForm.value.description) {
      formData.append("description", uploadForm.value.description);
    }

    formData.append("is_active", String(uploadForm.value.isActive));

    const payload = await apiFetch("/api/documents/upload", {
      method: "POST",
      body: formData,
    });
    uploadResult.value = payload.status || "Документ добавлен.";
    uploadForm.value = {
      file: null,
      docYear: "",
      categoriesText: "",
      description: "",
      isActive: true,
    };
    await loadDocuments();
  } catch (error) {
    uploadResult.value = error.message || String(error);
  } finally {
    uploadLoading.value = false;
  }
}

const availableYears = computed(() => {
  return [...new Set(documents.value.map((item) => item.doc_year).filter(Boolean))].sort((a, b) => b - a);
});

const availableCategories = computed(() => {
  return [...new Set(documents.value.flatMap((item) => item.categories || []))].sort((a, b) => a.localeCompare(b, "ru"));
});

const filteredDocuments = computed(() => {
  return documents.value.filter((item) => {
    if (documentFilters.value.year && String(item.doc_year || "") !== String(documentFilters.value.year)) return false;
    if (documentFilters.value.category && !(item.categories || []).includes(documentFilters.value.category)) return false;
    if (documentFilters.value.active === "active" && !item.is_active) return false;
    if (documentFilters.value.active === "inactive" && item.is_active) return false;
    return true;
  });
});

async function toggleStatus(item) {
  actionLoadingId.value = item.id;
  try {
    await apiFetch(`/api/documents/${item.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({
        is_active: !item.is_active,
      }),
    });
    await loadDocuments();
  } finally {
    actionLoadingId.value = "";
  }
}

async function saveCategories(item) {
  actionLoadingId.value = item.id;
  try {
    const categories = parseCategoriesText(categoryDrafts.value[item.id] || "");
    await apiFetch(`/api/documents/${item.id}/categories`, {
      method: "PATCH",
      body: JSON.stringify({ categories }),
    });
    await loadDocuments();
  } finally {
    actionLoadingId.value = "";
  }
}

async function saveMetadata(item) {
  actionLoadingId.value = item.id;
  try {
    const draft = metadataDrafts.value[item.id] || {};
    await apiFetch(`/api/documents/${item.id}/metadata`, {
      method: "PATCH",
      body: JSON.stringify({
        file_name: draft.fileName || item.file_name,
        description: draft.description || null,
        doc_year: draft.docYear ? Number(draft.docYear) : null,
      }),
    });
    await loadDocuments();
  } finally {
    actionLoadingId.value = "";
  }
}

async function deleteDocument(item) {
  const confirmed = window.confirm(`Удалить документ "${item.file_name}"?`);
  if (!confirmed) return;

  actionLoadingId.value = item.id;
  try {
    await apiFetch(`/api/documents/${item.id}`, {
      method: "DELETE",
    });
    await loadDocuments();
  } finally {
    actionLoadingId.value = "";
  }
}

onMounted(async () => {
  await loadDocuments();
});
</script>

<template>
  <section class="admin-grid">
    <template v-if="hasToken && isAdmin">
      <section class="page-panel">
        <div class="panel-head">
          <div>
            <p class="section-tag">Admin</p>
            <h2>Добавление документов</h2>
          </div>
        </div>

        <div class="form-grid">
          <input type="file" accept=".pdf,.docx" @change="onFileChange" />
          <input v-model="uploadForm.docYear" type="number" placeholder="Год документа" />
          <input
            v-model="uploadForm.categoriesText"
            type="text"
            placeholder="Категории через запятую, например: кредит, договор, регламент"
          />
          <textarea
            v-model="uploadForm.description"
            placeholder="Описание документа"
          ></textarea>
          <label class="toggle">
            <input v-model="uploadForm.isActive" type="checkbox" />
            Сразу активный
          </label>
          <button class="primary" :disabled="uploadLoading" @click="uploadDocument">
            {{ uploadLoading ? "Загрузка..." : "Добавить документ" }}
          </button>
          <p v-if="uploadResult" class="result-text">{{ uploadResult }}</p>
        </div>
      </section>

      <section class="page-panel">
        <div class="panel-head">
          <div>
            <p class="section-tag">Manage</p>
            <h2>Управление документами</h2>
          </div>
          <button class="ghost" :disabled="loadingDocuments" @click="loadDocuments">Обновить</button>
        </div>

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
            <option value="all">Все статусы</option>
            <option value="active">Активные</option>
            <option value="inactive">Неактивные</option>
          </select>
        </div>

        <div class="table-list">
          <article v-for="item in filteredDocuments" :key="item.id" class="doc-row">
            <div class="doc-info">
              <strong>{{ item.file_name }}</strong>
              <small>{{ item.doc_year || "Без года" }} · {{ item.is_active ? "Активен" : "Неактивен" }}</small>
              <small>Загрузил: {{ item.uploaded_by_username || item.uploaded_by || "Не указано" }}</small>
              <p v-if="item.description" class="description-text">{{ item.description }}</p>
              <div class="chips">
                <span v-for="category in item.categories" :key="category" class="chip">{{ category }}</span>
                <span v-if="!item.categories.length" class="chip muted">Без категорий</span>
              </div>
              <div class="metadata-editor">
                <input
                  v-model="metadataDrafts[item.id].fileName"
                  type="text"
                  placeholder="Название документа"
                />
                <input
                  v-model="metadataDrafts[item.id].docYear"
                  type="number"
                  placeholder="Год"
                />
                <textarea
                  v-model="metadataDrafts[item.id].description"
                  placeholder="Описание"
                ></textarea>
                <button class="ghost" :disabled="actionLoadingId === item.id" @click="saveMetadata(item)">
                  Сохранить метаданные
                </button>
              </div>
              <div class="categories-editor">
                <input
                  v-model="categoryDrafts[item.id]"
                  type="text"
                  placeholder="Изменить категории через запятую"
                />
                <button class="ghost" :disabled="actionLoadingId === item.id" @click="saveCategories(item)">
                  Сохранить категории
                </button>
              </div>
            </div>
            <div class="doc-actions">
              <button class="ghost" :disabled="actionLoadingId === item.id" @click="toggleStatus(item)">
                {{ item.is_active ? "Деактивировать" : "Активировать" }}
              </button>
              <button class="danger" :disabled="actionLoadingId === item.id" @click="deleteDocument(item)">
                Удалить
              </button>
            </div>
          </article>
        </div>

        <p v-if="documentsError" class="error-text">{{ documentsError }}</p>
      </section>
    </template>

    <div v-else class="page-panel denied">
      Эта страница доступна только пользователям с ролью `admin`.
    </div>
  </section>
</template>

<style scoped>
.admin-grid {
  display: grid;
  gap: 12px;
}

.page-panel {
  border: 1px solid var(--border);
  background: var(--surface);
  padding: 20px;
  color: var(--text);
}

.panel-head,
.doc-actions,
.categories-editor {
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

.form-grid,
.table-list,
.doc-info,
.filters-grid,
.metadata-editor {
  display: grid;
  gap: 12px;
}

input,
button,
textarea,
select {
  font: inherit;
}

input,
textarea,
select {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  padding: 12px 14px;
}

textarea {
  min-height: 84px;
  resize: vertical;
}

.filters-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 12px;
}

.toggle {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--muted);
}

.toggle input {
  width: auto;
}

.doc-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  border: 1px solid var(--border);
  background: var(--surface-soft);
  padding: 16px;
}

.doc-info {
  flex: 1;
  color: var(--muted);
}

.doc-info strong {
  color: var(--text);
}

.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.chip {
  border: 1px solid var(--border);
  padding: 6px 10px;
  background: var(--surface-muted);
  color: var(--accent);
  font-size: 0.82rem;
  font-weight: 700;
}

.chip.muted {
  color: var(--muted);
}

.categories-editor input {
  flex: 1;
}

.metadata-editor {
  grid-template-columns: minmax(180px, 1fr) 120px;
}

.metadata-editor textarea,
.metadata-editor button {
  grid-column: 1 / -1;
}

.primary,
.ghost,
.danger {
  border: 1px solid transparent;
  padding: 12px 16px;
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

.danger {
  background: var(--danger-soft);
  border-color: var(--danger);
  color: var(--danger);
}

.result-text {
  color: var(--text);
}

.description-text {
  margin: 0;
  color: var(--text);
}

.error-text {
  color: var(--danger);
}

.denied {
  color: var(--muted);
}

@media (max-width: 900px) {
  .doc-row,
  .doc-actions,
  .categories-editor {
    flex-direction: column;
    align-items: stretch;
  }

  .filters-grid,
  .metadata-editor {
    grid-template-columns: 1fr;
  }
}
</style>
