(() => {
  "use strict";

  const ARMS = ["base", "structured", "dynamic"];
  const ARM_DESCRIPTIONS = {
    base: "Conversational baseline with no inquiry protocol.",
    structured: "Fixed history-of-present-illness sequence over 4–5 turns (location, onset, severity, quality…).",
    dynamic: "Adaptive questioning: 3–4 targeted follow-ups chosen to separate competing diagnoses.",
  };
  const CHAT_TIMEOUT_MS = 90000;   // free-tier backends can take ~60s to wake up
  const HEALTH_TIMEOUT_MS = 70000;
  const HEALTH_RETRY_MS = 5000;
  const HEALTH_MAX_ATTEMPTS = 24;  // ~2+ minutes of retries during a cold start

  // --- API base URL -------------------------------------------------------
  function resolveApiBase() {
    const configured = (window.SYMPTOMCHECK_CONFIG && window.SYMPTOMCHECK_CONFIG.apiUrl) || "";
    let base = configured.trim();
    if (!base) {
      const host = location.hostname;
      if (!host || host === "localhost" || host === "127.0.0.1") base = "http://127.0.0.1:8000";
    }
    // Accept URLs pasted with the endpoint path, e.g. https://x.onrender.com/chat
    return base.replace(/\/+$/, "").replace(/\/(chat|health)$/, "");
  }
  const API_BASE = resolveApiBase();

  // --- State ---------------------------------------------------------------
  const state = {
    armChoice: "random",
    arm: randomArm(),
    messages: [],      // { role: "patient" | "assistant", content }
    ddx: null,
    busy: false,
  };

  // --- Elements ------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const el = {
    status: $("status"), statusText: $("status-text"),
    armSelect: $("arm-select"), activeArm: $("active-arm"), armNote: $("arm-note"), armDesc: $("arm-desc"),
    reset: $("reset-btn"), messages: $("messages"), empty: $("empty-state"),
    error: $("error"), composer: $("composer"), input: $("input"), send: $("send-btn"),
    tabChat: $("tab-chat"), tabResults: $("tab-results"),
    panelChat: $("panel-chat"), panelResults: $("panel-results"),
    summary: $("summary"), casesTable: $("cases-table"),
    chart: $("chart"), chartMissing: $("chart-missing"),
  };

  function randomArm() {
    return ARMS[Math.floor(Math.random() * ARMS.length)];
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  async function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  // --- Backend status ------------------------------------------------------
  function setStatus(kind, text) {
    el.status.className = `status status-${kind}`;
    el.statusText.textContent = text;
  }

  let mockMode = false;
  let backendOnline = false;

  function markOnline() {
    backendOnline = true;
    setStatus("ok", mockMode ? "Online · mock LLM mode" : "Online");
  }

  // Free-tier hosts answer with 502/503 while the backend wakes up, so keep
  // retrying for a few minutes instead of giving up after the first failure.
  async function checkHealth(attempt = 1) {
    if (!API_BASE) {
      setStatus("bad", "Backend URL not configured");
      showError("This deployment has no BACKEND_URL set. Add it in your hosting provider's environment variables and redeploy.");
      return;
    }
    if (backendOnline) return;
    if (attempt === 1) setStatus("pending", "Connecting to backend…");
    const slowHint = setTimeout(() => setStatus("pending", "Waking up backend (can take ~1 min)…"), 4000);
    try {
      const res = await fetchWithTimeout(`${API_BASE}/health`, {}, HEALTH_TIMEOUT_MS);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      mockMode = Boolean(data.mock_mode);
      markOnline();
    } catch {
      if (backendOnline) return;
      if (attempt < HEALTH_MAX_ATTEMPTS) {
        setStatus("pending", "Waking up backend (can take ~1 min)…");
        setTimeout(() => checkHealth(attempt + 1), HEALTH_RETRY_MS);
      } else {
        setStatus("bad", "Backend offline");
      }
    } finally {
      clearTimeout(slowHint);
    }
  }

  // --- Chat rendering ------------------------------------------------------
  function renderArm() {
    el.activeArm.textContent = state.arm;
    el.armNote.textContent = state.armChoice === "random" ? "(randomized)" : "";
    el.armDesc.textContent = ARM_DESCRIPTIONS[state.arm];
  }

  function renderMessages() {
    el.messages.replaceChildren();
    if (!state.messages.length && !state.busy) {
      el.messages.append(el.empty);
    }

    state.messages.forEach((m, i) => {
      const isFinal = state.ddx && i === state.messages.length - 1 && m.role === "assistant";
      const wrap = make("div", `msg msg-${m.role === "patient" ? "patient" : "assistant"}`);
      const text = isFinal ? "Thanks — I have enough information. Here is the differential diagnosis." : m.content;
      wrap.append(make("div", "bubble", text));
      if (m.role !== "patient") {
        wrap.append(make("div", "msg-meta", "Educational demo only — not medical advice."));
      }
      el.messages.append(wrap);
    });

    if (state.busy) {
      const typing = make("div", "msg msg-assistant typing");
      const bubble = make("div", "bubble");
      bubble.setAttribute("aria-label", "Assistant is typing");
      bubble.append(make("span"), make("span"), make("span"));
      typing.append(bubble);
      el.messages.append(typing);
    }

    if (state.ddx) el.messages.append(renderDdx(state.ddx));

    el.messages.scrollTop = el.messages.scrollHeight;

    const done = Boolean(state.ddx);
    el.input.disabled = state.busy || done;
    el.send.disabled = state.busy || done;
    el.input.placeholder = done ? "Consultation complete — reset to start a new one." : "Describe your symptoms…";
  }

  function renderDdx(ddx) {
    const card = make("div", "ddx");
    card.append(make("h3", null, "Differential diagnosis"));
    if (ddx.history_summary) {
      const p = make("p", "small");
      p.append(make("strong", null, "History summary: "), document.createTextNode(ddx.history_summary));
      card.append(p);
    }
    const list = make("ol");
    (ddx.differential || []).forEach((item) => {
      const li = make("li");
      li.append(make("span", "dx-name", item.diagnosis || item.condition_name || "Unnamed"));
      if (item.rationale) li.append(make("span", "dx-why", item.rationale));
      list.append(li);
    });
    card.append(list);
    card.append(make("p", "dx-disclaimer", ddx.disclaimer || "Educational demo only. Not a medical device."));
    return card;
  }

  function showError(message) {
    el.error.textContent = message;
    el.error.hidden = false;
  }

  function clearError() {
    el.error.hidden = true;
    el.error.textContent = "";
  }

  // --- Chat actions --------------------------------------------------------
  async function sendMessage(text) {
    clearError();
    state.messages.push({ role: "patient", content: text });
    state.busy = true;
    renderMessages();

    try {
      const res = await fetchWithTimeout(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arm: state.arm, messages: state.messages }),
      }, CHAT_TIMEOUT_MS);

      if (res.status === 429) throw new Error("Rate limit reached (10 messages per minute). Wait a moment and try again.");
      if (!res.ok) throw new Error(`The backend returned an error (HTTP ${res.status}).`);

      const data = await res.json();
      markOnline();
      state.messages.push({ role: "assistant", content: data.message || "" });
      if (data.complete && data.ddx_result) state.ddx = data.ddx_result;
    } catch (err) {
      // Roll back the unanswered message so the conversation history stays consistent.
      state.messages.pop();
      el.input.value = text;
      const message = err.name === "AbortError"
        ? "The backend took too long to respond. It may be waking up — please try again."
        : err instanceof TypeError
          ? "Couldn't reach the backend. Check that it's running and that BACKEND_URL is correct."
          : err.message;
      showError(message);
    } finally {
      state.busy = false;
      renderMessages();
      autoGrow();
      if (!state.ddx) el.input.focus();
    }
  }

  function resetConsultation() {
    state.messages = [];
    state.ddx = null;
    state.arm = state.armChoice === "random" ? randomArm() : state.armChoice;
    clearError();
    el.input.value = "";
    autoGrow();
    renderArm();
    renderMessages();
    el.input.focus();
  }

  function autoGrow() {
    el.input.style.height = "auto";
    el.input.style.height = `${Math.min(el.input.scrollHeight, 160)}px`;
    el.input.style.overflowY = el.input.scrollHeight > 160 ? "auto" : "hidden";
  }

  // --- Results tab ---------------------------------------------------------
  let resultsLoaded = false;

  function parseCsv(text) {
    const lines = text.trim().split(/\r?\n/);
    const headers = lines.shift().split(",").map((h) => h.trim());
    return lines.filter(Boolean).map((line) => {
      const cells = line.split(",");
      return Object.fromEntries(headers.map((h, i) => [h, (cells[i] || "").trim()]));
    });
  }

  function pct(n, d) {
    return d ? (100 * n) / d : 0;
  }

  async function loadResults() {
    if (resultsLoaded) return;
    resultsLoaded = true;

    let rows;
    try {
      const res = await fetch("results/results.csv", { cache: "no-cache" });
      if (!res.ok) throw new Error();
      rows = parseCsv(await res.text());
    } catch {
      el.summary.replaceChildren(make("p", "muted", "No results found. Run python eval/run_eval.py and redeploy."));
      return;
    }

    const byArm = new Map(ARMS.map((a) => [a, []]));
    rows.forEach((r) => {
      if (!byArm.has(r.arm)) byArm.set(r.arm, []);
      byArm.get(r.arm).push(r);
    });

    const table = make("table");
    const head = make("tr");
    [["Arm"], ["Cases", "num"], ["Top-1", "num"], ["Top-5", "num"], ["Avg turns", "num"]]
      .forEach(([t, c]) => head.append(make("th", c, t)));
    table.append(head);

    byArm.forEach((list, arm) => {
      if (!list.length) return;
      const pos = list.map((r) => Number(r.position));
      const top1 = pct(pos.filter((p) => p === 1).length, list.length);
      const top5 = pct(pos.filter((p) => p >= 1 && p <= 5).length, list.length);
      const turns = list.reduce((s, r) => s + Number(r.turn_count || 0), 0) / list.length;

      const tr = make("tr");
      const armCell = make("td");
      armCell.append(make("code", null, arm));
      tr.append(armCell, make("td", "num", String(list.length)));
      [top1, top5].forEach((v) => {
        const td = make("td", "num", `${v.toFixed(1)}%`);
        const bar = make("div", "bar");
        const fill = make("span");
        fill.style.width = `${v}%`;
        bar.append(fill);
        td.append(bar);
        tr.append(td);
      });
      tr.append(make("td", "num", turns.toFixed(1)));
      table.append(tr);
    });
    el.summary.replaceChildren(table);

    const caseHead = make("tr");
    [["Case"], ["Arm"], ["Rank of true dx", "num"], ["Turns", "num"]]
      .forEach(([t, c]) => caseHead.append(make("th", c, t)));
    el.casesTable.replaceChildren(caseHead);
    rows.forEach((r) => {
      const tr = make("tr");
      const p = Number(r.position);
      const hit = p >= 1 && p <= 5;
      tr.append(
        make("td", null, r.case_id),
        make("td", null, r.arm),
        make("td", `num ${hit ? "hit" : "miss"}`, hit ? `#${p}` : "not in top 5"),
        make("td", "num", r.turn_count),
      );
      el.casesTable.append(tr);
    });
  }

  function selectTab(which) {
    const chat = which === "chat";
    el.tabChat.classList.toggle("active", chat);
    el.tabResults.classList.toggle("active", !chat);
    el.tabChat.setAttribute("aria-selected", String(chat));
    el.tabResults.setAttribute("aria-selected", String(!chat));
    el.panelChat.hidden = !chat;
    el.panelResults.hidden = chat;
    if (!chat) loadResults();
  }

  // --- Wire up -------------------------------------------------------------
  el.composer.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = el.input.value.trim();
    if (!text || state.busy || state.ddx) return;
    el.input.value = "";
    autoGrow();
    sendMessage(text);
  });

  el.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      el.composer.requestSubmit();
    }
  });
  el.input.addEventListener("input", autoGrow);

  el.armSelect.addEventListener("change", () => {
    const hasConversation = state.messages.length > 0;
    if (hasConversation && !confirm("Changing the arm starts a new consultation. Continue?")) {
      el.armSelect.value = state.armChoice;
      return;
    }
    state.armChoice = el.armSelect.value;
    resetConsultation();
  });

  el.reset.addEventListener("click", resetConsultation);
  el.tabChat.addEventListener("click", () => selectTab("chat"));
  el.tabResults.addEventListener("click", () => selectTab("results"));
  el.chart.addEventListener("error", () => {
    el.chart.hidden = true;
    el.chartMissing.hidden = false;
  });

  renderArm();
  renderMessages();
  checkHealth();
})();
