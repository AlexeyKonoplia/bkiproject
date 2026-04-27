from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["tester-ui"])


HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>BKI Service Tester</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: #fffaf3;
      --panel-strong: #fff;
      --text: #1f1a17;
      --muted: #6b625b;
      --accent: #0b6e4f;
      --accent-2: #d17b0f;
      --border: #dccfbe;
      --danger: #b42318;
      --shadow: 0 18px 45px rgba(51, 39, 24, 0.08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(209, 123, 15, 0.14), transparent 28%),
        radial-gradient(circle at top right, rgba(11, 110, 79, 0.12), transparent 24%),
        linear-gradient(180deg, #fbf7f1 0%, var(--bg) 100%);
    }

    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }

    .hero {
      margin-bottom: 24px;
      padding: 28px;
      border: 1px solid var(--border);
      border-radius: 24px;
      background: linear-gradient(135deg, rgba(255,255,255,0.92), rgba(255,250,243,0.96));
      box-shadow: var(--shadow);
    }

    h1, h2 {
      margin: 0 0 10px;
      line-height: 1.1;
    }

    h1 { font-size: clamp(2rem, 4vw, 3.6rem); }
    h2 { font-size: 1.15rem; }

    p, label, small {
      color: var(--muted);
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 18px;
    }

    .card {
      border: 1px solid var(--border);
      border-radius: 22px;
      background: rgba(255, 255, 255, 0.82);
      backdrop-filter: blur(8px);
      box-shadow: var(--shadow);
      padding: 18px;
    }

    .row {
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }

    input, textarea, button {
      width: 100%;
      border-radius: 14px;
      border: 1px solid var(--border);
      padding: 12px 14px;
      font: inherit;
      background: var(--panel-strong);
      color: var(--text);
    }

    textarea {
      min-height: 120px;
      resize: vertical;
    }

    button {
      cursor: pointer;
      font-weight: 600;
      border: none;
      color: white;
      background: linear-gradient(135deg, var(--accent), #095a41);
      transition: transform 0.15s ease, opacity 0.15s ease;
    }

    button.secondary {
      background: linear-gradient(135deg, var(--accent-2), #a65f0b);
    }

    button.ghost {
      color: var(--text);
      background: #efe6d9;
    }

    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.6; cursor: wait; transform: none; }

    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .actions button {
      width: auto;
      min-width: 140px;
    }

    .status {
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      background: #f6efe5;
      color: var(--text);
      font-size: 0.95rem;
    }

    .status.error {
      background: #fdecea;
      color: var(--danger);
    }

    .pill {
      display: inline-block;
      margin-top: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #e7f4ef;
      color: var(--accent);
      font-size: 0.85rem;
      font-weight: 700;
    }

    pre {
      margin: 12px 0 0;
      padding: 14px;
      min-height: 150px;
      overflow: auto;
      border-radius: 16px;
      border: 1px solid #e5d8c8;
      background: #1f2329;
      color: #f5f7fa;
      font-size: 0.9rem;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .token-box {
      min-height: 78px;
      font-family: Consolas, monospace;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Проверка сервиса BKI</h1>
      <p>Эта страница помогает вручную проверить основные функции сервиса: авторизацию, health-check, загрузку документов, вопрос по документам и feedback.</p>
      <span class="pill">Откройте: /tester</span>
    </section>

    <div class="grid">
      <section class="card">
        <h2>1. Авторизация</h2>
        <p>Сначала получите JWT через <code>/auth/login</code>. Токен сохранится в браузере и будет подставляться в защищённые запросы.</p>
        <div class="row">
          <input id="username" type="text" placeholder="Логин" value="admin" />
          <input id="password" type="password" placeholder="Пароль" value="admin" />
          <div class="actions">
            <button id="login-btn">Войти</button>
            <button id="logout-btn" class="ghost" type="button">Очистить токен</button>
          </div>
          <div id="auth-status" class="status">Токен ещё не получен.</div>
          <textarea id="token" class="token-box" placeholder="JWT token"></textarea>
        </div>
      </section>

      <section class="card">
        <h2>2. Базовая проверка</h2>
        <p>Быстрый smoke test сервиса. Этот запрос не требует авторизации.</p>
        <div class="row">
          <div class="actions">
            <button id="health-btn" class="secondary">Проверить /healthz</button>
          </div>
          <pre id="health-result">Здесь появится ответ health-check.</pre>
        </div>
      </section>

      <section class="card">
        <h2>3. Загрузка документа</h2>
        <p>Нужен токен администратора. Поддерживаются <code>.pdf</code> и <code>.docx</code>.</p>
        <div class="row">
          <input id="upload-file" type="file" accept=".pdf,.docx" />
          <input id="doc-year" type="number" placeholder="Год документа, например 2025" />
          <input id="doc-category" type="text" placeholder="Категория, например instructions" />
          <label><input id="is-active" type="checkbox" checked style="width:auto;margin-right:8px;" />Активный документ</label>
          <div class="actions">
            <button id="upload-btn">Отправить документ</button>
          </div>
          <pre id="upload-result">Здесь будет результат загрузки документа.</pre>
        </div>
      </section>

      <section class="card">
        <h2>4. Вопрос к сервису</h2>
        <p>После загрузки документа можно задать вопрос и проверить, что сервис вернул ответ и источники.</p>
        <div class="row">
          <textarea id="question" placeholder="Например: О чем этот документ?"></textarea>
          <input id="top-k" type="number" value="5" min="1" max="25" />
          <input id="ask-year-from" type="number" placeholder="Год от" />
          <input id="ask-year-to" type="number" placeholder="Год до" />
          <input id="ask-category" type="text" placeholder="Категория" />
          <div class="actions">
            <button id="ask-btn" class="secondary">Отправить вопрос</button>
          </div>
          <pre id="ask-result">Здесь будет ответ сервиса на ваш вопрос.</pre>
        </div>
      </section>

      <section class="card">
        <h2>5. Last query chunks</h2>
        <p>Separate request that returns the retrieved text chunks for the latest <code>/ask</code> call of the current user.</p>
        <div class="row">
          <div class="actions">
            <button id="last-chunks-btn" class="secondary">Load last chunks</button>
          </div>
          <pre id="last-chunks-result">The retrieved chunks for the latest ask request will appear here.</pre>
        </div>
      </section>

      <section class="card">
        <h2>6. Feedback</h2>
        <p>Если <code>/ask</code> вернул <code>ask_event_id</code>, можно сразу отправить оценку ответа.</p>
        <div class="row">
          <input id="ask-event-id" type="text" placeholder="ask_event_id" />
          <input id="vote" type="number" value="1" min="-1" max="1" />
          <textarea id="feedback-comment" placeholder="Комментарий к ответу"></textarea>
          <div class="actions">
            <button id="feedback-btn">Отправить feedback</button>
          </div>
          <pre id="feedback-result">Здесь будет результат отправки feedback.</pre>
        </div>
      </section>
    </div>
  </div>

  <script>
    const storageKey = "bki-service-token";

    const tokenField = document.getElementById("token");
    const authStatus = document.getElementById("auth-status");

    function setStatus(element, message, isError = false) {
      element.textContent = message;
      element.classList.toggle("error", isError);
    }

    function pretty(data) {
      if (typeof data === "string") {
        return data;
      }
      return JSON.stringify(data, null, 2);
    }

    function loadToken() {
      const saved = window.localStorage.getItem(storageKey) || "";
      tokenField.value = saved;
      if (saved) {
        setStatus(authStatus, "JWT сохранён и готов к использованию.");
      }
    }

    function saveToken(token) {
      window.localStorage.setItem(storageKey, token);
      tokenField.value = token;
      setStatus(authStatus, "Токен успешно получен.");
    }

    function clearToken() {
      window.localStorage.removeItem(storageKey);
      tokenField.value = "";
      setStatus(authStatus, "Токен очищен.");
    }

    function getToken() {
      return tokenField.value.trim();
    }

    async function parseResponse(response) {
      const text = await response.text();
      try {
        return text ? JSON.parse(text) : {};
      } catch {
        return text;
      }
    }

    async function apiRequest(path, options = {}, requiresAuth = false) {
      const headers = new Headers(options.headers || {});
      if (requiresAuth) {
        const token = getToken();
        if (!token) {
          throw new Error("Сначала получите JWT токен в блоке авторизации.");
        }
        headers.set("Authorization", `Bearer ${token}`);
      }

      const response = await fetch(path, { ...options, headers });
      const payload = await parseResponse(response);
      if (!response.ok) {
        throw new Error(pretty(payload));
      }
      return payload;
    }

    async function run(buttonId, targetId, work) {
      const button = document.getElementById(buttonId);
      const target = document.getElementById(targetId);
      button.disabled = true;
      target.textContent = "Запрос выполняется...";
      try {
        const result = await work();
        target.textContent = pretty(result);
        return result;
      } catch (error) {
        target.textContent = error.message || String(error);
      } finally {
        button.disabled = false;
      }
    }

    document.getElementById("login-btn").addEventListener("click", async () => {
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value;
      setStatus(authStatus, "Получаем токен...");

      try {
        const result = await apiRequest("/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        saveToken(result.access_token || "");
      } catch (error) {
        setStatus(authStatus, error.message || String(error), true);
      }
    });

    document.getElementById("logout-btn").addEventListener("click", clearToken);

    document.getElementById("health-btn").addEventListener("click", () =>
      run("health-btn", "health-result", () =>
        apiRequest("/healthz")
      )
    );

    document.getElementById("upload-btn").addEventListener("click", () =>
      run("upload-btn", "upload-result", async () => {
        const fileInput = document.getElementById("upload-file");
        if (!fileInput.files.length) {
          throw new Error("Выберите PDF или DOCX файл.");
        }

        const formData = new FormData();
        formData.append("file", fileInput.files[0]);

        const docYear = document.getElementById("doc-year").value.trim();
        const docCategory = document.getElementById("doc-category").value.trim();
        const isActive = document.getElementById("is-active").checked;

        if (docYear) formData.append("doc_year", docYear);
        if (docCategory) formData.append("doc_category", docCategory);
        formData.append("is_active", String(isActive));

        return apiRequest("/upload", {
          method: "POST",
          body: formData,
        }, true);
      })
    );

    document.getElementById("ask-btn").addEventListener("click", () =>
      run("ask-btn", "ask-result", async () => {
        const payload = {
          question: document.getElementById("question").value.trim(),
          top_k: Number(document.getElementById("top-k").value || 5),
        };

        if (!payload.question) {
          throw new Error("Введите вопрос.");
        }

        const yearFrom = document.getElementById("ask-year-from").value.trim();
        const yearTo = document.getElementById("ask-year-to").value.trim();
        const category = document.getElementById("ask-category").value.trim();

        if (yearFrom) payload.doc_year_from = Number(yearFrom);
        if (yearTo) payload.doc_year_to = Number(yearTo);
        if (category) payload.doc_category = category;

        const result = await apiRequest("/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }, true);

        if (result.ask_event_id) {
          document.getElementById("ask-event-id").value = result.ask_event_id;
        }

        return result;
      })
    );

    document.getElementById("last-chunks-btn").addEventListener("click", () =>
      run("last-chunks-btn", "last-chunks-result", () =>
        apiRequest("/ask/last-chunks", {
          method: "GET",
        }, true)
      )
    );

    document.getElementById("feedback-btn").addEventListener("click", () =>
      run("feedback-btn", "feedback-result", async () => {
        const askEventId = document.getElementById("ask-event-id").value.trim();
        const vote = Number(document.getElementById("vote").value);
        const comment = document.getElementById("feedback-comment").value.trim();

        if (!askEventId) {
          throw new Error("Укажите ask_event_id.");
        }

        return apiRequest("/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ask_event_id: askEventId,
            vote: vote,
            comment: comment || null,
          }),
        }, true);
      })
    );

    loadToken();
  </script>
</body>
</html>
"""


@router.get("/tester", response_class=HTMLResponse, include_in_schema=False)
async def tester_ui() -> HTMLResponse:
    return HTMLResponse(content=HTML_PAGE)
