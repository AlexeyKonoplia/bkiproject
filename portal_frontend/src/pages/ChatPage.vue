<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { apiFetch, hasToken } from "../lib/api";

const router = useRouter();

const loadingDocuments = ref(false);
const documentsError = ref("");
const documents = ref([]);
const selectedDocumentId = ref("");
const selectedDocumentLabel = ref("");

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

async function loadDocuments() {
  if (!hasToken.value) return;

  loadingDocuments.value = true;
  documentsError.value = "";
  try {
    const payload = await apiFetch("/api/documents?only_active=true&limit=100");
    documents.value = payload.items || [];
  } catch (error) {
    documentsError.value = error.message || String(error);
  } finally {
    loadingDocuments.value = false;
  }
}

function selectDocument(item) {
  selectedDocumentId.value = item?.id || "";
  selectedDocumentLabel.value = item?.file_name || "";
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

      <button
        class="document-item clear"
        :class="{ selected: !selectedDocumentId }"
        :disabled="!hasToken"
        @click="selectDocument(null)"
      >
        Вся база документов
      </button>

      <button
        v-for="item in documents"
        :key="item.id"
        class="document-item"
        :class="{ selected: selectedDocumentId === item.id }"
        :disabled="!hasToken"
        @click="selectDocument(item)"
      >
        <strong>{{ item.file_name }}</strong>
        <span>{{ item.doc_category || "Без категории" }}</span>
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
          <p>{{ message.content }}</p>
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
.ghost {
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
}
</style>
