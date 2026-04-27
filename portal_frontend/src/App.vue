<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import { hasToken, isAdmin, loadProfile, login, logout, profile } from "./lib/api";

const route = useRoute();

const credentials = ref({
  username: "",
  password: "",
});
const authLoading = ref(false);
const authError = ref("");

const pageTitle = computed(() => {
  if (route.name === "documents") return "Просмотр документов";
  if (route.name === "admin-documents") return "Админ-документы";
  return "Основная страница";
});
const viewKey = computed(() => `${route.fullPath}-${hasToken.value ? "auth" : "guest"}`);

async function submitLogin() {
  authLoading.value = true;
  authError.value = "";
  try {
    await login(credentials.value);
    await loadProfile();
  } catch (error) {
    authError.value = error.message || String(error);
  } finally {
    authLoading.value = false;
  }
}

function submitLogout() {
  logout();
}

onMounted(async () => {
  if (hasToken.value) {
    try {
      await loadProfile();
    } catch {
      logout();
    }
  }
});
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <section class="brand-panel">
        <p class="eyebrow">Document Access Portal</p>
        <h1>Портал поддержки</h1>
        <p class="subtitle">
          Единая точка доступа к работе с документами, обращениям и административным сценариям.
        </p>
      </section>

      <nav class="menu-panel">
        <p class="eyebrow">Menu</p>
        <RouterLink class="nav-link" to="/">Основная страница</RouterLink>
        <RouterLink class="nav-link" to="/documents">Просмотр документов</RouterLink>
        <RouterLink v-if="isAdmin" class="nav-link" to="/admin/documents">
          Админ-документы
        </RouterLink>
      </nav>

      <section class="auth-card">
        <p class="eyebrow">Access</p>
        <template v-if="!hasToken">
          <label>
            Логин
            <input
              v-model="credentials.username"
              type="text"
              placeholder="login"
              autocomplete="off"
            />
          </label>
          <label>
            Пароль
            <input
              v-model="credentials.password"
              type="password"
              placeholder="password"
              autocomplete="off"
            />
          </label>
          <button class="primary" :disabled="authLoading" @click="submitLogin">
            {{ authLoading ? "Вход..." : "Войти" }}
          </button>
          <p v-if="authError" class="error-text">{{ authError }}</p>
        </template>
        <template v-else>
          <p class="signed-in">Сессия активна</p>
          <strong>{{ profile?.username || "user" }}</strong>
          <small>Роли: {{ (profile?.roles || []).join(", ") }}</small>
          <button class="ghost" @click="submitLogout">Выйти</button>
        </template>
      </section>
    </aside>

    <main class="content-area">
      <section class="page-header">
        <p class="section-tag">Workspace</p>
        <h2>{{ pageTitle }}</h2>
      </section>

      <RouterView :key="viewKey" />
    </main>
  </div>
</template>

<style>
:root {
  color-scheme: light;
  --bg: #eef1f5;
  --sidebar: #2b2f36;
  --sidebar-soft: #363c45;
  --sidebar-border: #434a54;
  --sidebar-text: #f4f7fb;
  --surface: #ffffff;
  --surface-soft: #f7f9fc;
  --surface-muted: #f2f5f9;
  --panel: var(--surface);
  --panel-strong: var(--surface);
  --panel-soft: var(--surface-soft);
  --panel-muted: var(--surface-muted);
  --border: #d9e0e8;
  --border-strong: #bcc7d3;
  --text: #1f2a37;
  --muted: #708090;
  --inverse: #ffffff;
  --accent: #2d63d5;
  --accent-soft: #edf3ff;
  --shadow: none;
  --danger: #d14343;
  --danger-soft: #fff1f1;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  min-height: 100%;
}

body {
  margin: 0;
  min-width: 320px;
  font-family: "Segoe UI", "Bahnschrift", "Trebuchet MS", sans-serif;
  color: var(--text);
  background: var(--bg);
}

button,
input,
textarea {
  font: inherit;
  border-radius: 0;
}

button:focus-visible,
input:focus-visible,
textarea:focus-visible,
a:focus-visible {
  outline: 2px solid var(--text);
  outline-offset: 2px;
}

.shell {
  width: 100%;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: 286px minmax(0, 1fr);
  gap: 4px;
  min-height: 100vh;
}

.sidebar,
.content-area {
  min-width: 0;
}

.sidebar {
  display: grid;
  gap: 0;
  align-content: start;
  position: sticky;
  top: 0;
  align-self: start;
  min-height: 100vh;
  background: var(--sidebar);
  border-right: 1px solid var(--sidebar-border);
}

.brand-panel,
.menu-panel,
.auth-card,
.page-header {
  border: 0;
  box-shadow: none;
}

.brand-panel {
  padding: 18px 20px;
  background: var(--accent);
  color: var(--inverse);
}

.menu-panel {
  display: grid;
  gap: 2px;
  padding: 12px 0 0;
  background: var(--sidebar);
}

.auth-card {
  display: grid;
  gap: 12px;
  margin-top: auto;
  padding: 18px 20px 22px;
  background: var(--sidebar);
  border-top: 1px solid var(--sidebar-border);
}

.content-area {
  display: grid;
  gap: 12px;
  align-content: start;
  padding: 4px 10px 18px 0;
}

.eyebrow,
.section-tag {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.72rem;
  color: var(--muted);
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: 1.75rem;
  line-height: 1.1;
  max-width: none;
}

h2 {
  font-size: 1.55rem;
}

.subtitle {
  margin-top: 10px;
  color: rgba(255, 255, 255, 0.82);
  line-height: 1.5;
  font-size: 0.95rem;
}

.nav-link {
  display: block;
  padding: 12px 20px;
  border-left: 3px solid transparent;
  color: rgba(244, 247, 251, 0.9);
  text-decoration: none;
  background: transparent;
  font-weight: 500;
  letter-spacing: 0.02em;
  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease;
}

.nav-link:hover {
  background: var(--sidebar-soft);
  color: var(--sidebar-text);
}

.nav-link.router-link-active {
  background: rgba(255, 255, 255, 0.08);
  color: var(--sidebar-text);
  border-color: var(--accent);
}

.auth-card label {
  display: grid;
  gap: 8px;
  color: rgba(244, 247, 251, 0.74);
}

.auth-card input {
  width: 100%;
  border: 1px solid var(--sidebar-border);
  background: rgba(255, 255, 255, 0.06);
  color: var(--sidebar-text);
  padding: 12px 14px;
}

.auth-card input::placeholder {
  color: rgba(244, 247, 251, 0.42);
}

.primary,
.ghost {
  padding: 12px 16px;
  cursor: pointer;
  font-weight: 700;
  transition:
    background-color 160ms ease,
    color 160ms ease,
    border-color 160ms ease,
    opacity 160ms ease;
}

.primary:disabled,
.ghost:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.primary {
  border: 1px solid var(--accent);
  color: var(--inverse);
  background: var(--accent);
}

.ghost {
  border: 1px solid var(--border);
  color: var(--text);
  background: var(--surface);
}

.signed-in {
  color: rgba(244, 247, 251, 0.62);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.78rem;
}

.auth-card strong,
.auth-card small,
.brand-panel .eyebrow {
  color: var(--sidebar-text);
}

.page-header {
  padding: 18px 22px;
  border: 1px solid var(--border);
  background: var(--surface);
}

.error-text {
  color: var(--danger);
}

small {
  color: var(--muted);
}

@media (max-width: 980px) {
  .shell {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .sidebar {
    position: static;
    min-height: auto;
  }

  .content-area {
    padding: 4px 10px 16px;
  }
}
</style>
