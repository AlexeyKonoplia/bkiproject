import { computed, ref } from "vue";

const storageKey = "bki-document-portal-token";

export const token = ref(localStorage.getItem(storageKey) || "");
export const profile = ref(null);

export const hasToken = computed(() => Boolean(token.value));
export const isAdmin = computed(() => (profile.value?.roles || []).includes("admin"));

export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token.value) {
    headers.set("Authorization", `Bearer ${token.value}`);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...options,
    headers,
  });

  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = text;
  }

  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null ? payload.detail ?? payload : payload;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail, null, 2));
  }

  return payload;
}

export async function login(credentials) {
  const payload = await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
  token.value = payload.access_token || "";
  localStorage.setItem(storageKey, token.value);
  return payload;
}

export function logout() {
  token.value = "";
  profile.value = null;
  localStorage.removeItem(storageKey);
}

export async function loadProfile() {
  profile.value = await apiFetch("/api/auth/me");
  return profile.value;
}
