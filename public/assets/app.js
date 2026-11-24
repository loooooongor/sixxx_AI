/* ═══════════════════════════════════════════════════════════════
   六爻 · 問卦 — 前端邏輯（無框架，原生 JS）
   版面：左側占問紀錄，右側對話；卦盤收在對話流裡。
   ═══════════════════════════════════════════════════════════════ */
"use strict";

/* ───────────── 狀態 ───────────── */

const S = {
  board: null,            // 目前卦盤
  boardEl: null,          // 目前卦盤卡（DOM）
  question: "",           // 目前占問
  answer: "",             // 目前解卦全文
  busy: false,            // 起卦／串流中
  epoch: 0,               // 換局計數：避免舊串流寫進新畫面
  config: null,           // LLM 設定（公開資訊）
  providers: [],
  glossary: {},
  history: [],            // localStorage 紀錄
  activeHistoryId: null,
  pendingRead: null,      // 設定金鑰後要補跑的解讀
};

const prefs = {
  mode: "coins",          // coins | manual
  yongshen: "",
  whenMode: "now",        // now | custom
  when: "",
  hexagram: "",
  moving: "",
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const HISTORY_KEY = "liuyao.history.v1";
const PREFS_KEY = "liuyao.prefs.v1";
const MAX_HISTORY = 40;
const DEFAULT_HINT = "Enter 送出　·　Shift + Enter 換行";

// 變卦舊資料不一定有 wx 欄位，前端自備地支五行對照
const ZHI_WX = {
  子: "水", 丑: "土", 寅: "木", 卯: "木", 辰: "土", 巳: "火",
  午: "火", 未: "土", 申: "金", 酉: "金", 戌: "土", 亥: "水",
};

let termPop = null;
let toastTimer = 0;

/* ───────────── 小工具 ───────────── */

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function pad2(n) { return String(n).padStart(2, "0"); }

function nowLocalInput() {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
       + `T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function relTime(iso) {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "";
  const diff = (Date.now() - t) / 1000;
  if (diff < 60) return "剛剛";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分鐘前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小時前`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`;
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function toast(msg) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("is-on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-on"), 2000);
}

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && !data.error) throw new Error(`HTTP ${res.status}`);
  return data;
}

function llmConfigured() {
  return !!(S.config && S.config.configured);
}

/* ───────────── 極簡 Markdown ───────────── */

function inlineMd(text) {
  let s = esc(text);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  s = s.replace(/「([^」]{1,12})」/g, '<span class="quote">「$1」</span>');
  return s;
}

function renderMd(md) {
  const lines = String(md || "").split("\n");
  const out = [];
  let list = null;
  let quote = null;
  let para = [];

  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${para.map(inlineMd).join("<br>")}</p>`);
      para = [];
    }
  };
  const flushList = () => {
    if (list) { out.push(`<${list.tag}>${list.items.join("")}</${list.tag}>`); list = null; }
  };
  const flushQuote = () => {
    if (quote) { out.push(`<blockquote>${quote.join("<br>")}</blockquote>`); quote = null; }
  };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) { flushPara(); flushList(); flushQuote(); continue; }

    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      flushPara(); flushList(); flushQuote();
      const lvl = Math.min(6, Math.max(2, m[1].length));
      out.push(`<h${lvl}>${inlineMd(m[2])}</h${lvl}>`);
      continue;
    }
    if ((m = line.match(/^>\s?(.*)$/))) {
      flushPara(); flushList();
      (quote = quote || []).push(inlineMd(m[1]));
      continue;
    }
    if ((m = line.match(/^\s*[-*·]\s+(.*)$/))) {
      flushPara(); flushQuote();
      if (!list || list.tag !== "ul") { flushList(); list = { tag: "ul", items: [] }; }
      list.items.push(`<li>${inlineMd(m[1])}</li>`);
      continue;
    }
    if ((m = line.match(/^\s*(\d+)[.、]\s+(.*)$/))) {
      flushPara(); flushQuote();
      if (!list || list.tag !== "ol") { flushList(); list = { tag: "ol", items: [] }; }
      list.items.push(`<li>${inlineMd(m[2])}</li>`);
      continue;
    }
    flushList(); flushQuote();
    para.push(line);
  }
  flushPara(); flushList(); flushQuote();
  return out.join("");
}

/* ───────────── 術語浮層 ───────────── */

function bindTerms(root) {
  $$("span.quote", root).forEach((el) => {
    const raw = el.textContent.replace(/[「」]/g, "");
    const def = S.glossary[raw];
    if (!def) return;
    el.classList.add("term");
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!termPop) return;
      termPop.innerHTML = `<h4>${esc(raw)}</h4>${esc(def)}`;
      termPop.hidden = false;
      const r = el.getBoundingClientRect();
      const w = termPop.offsetWidth, h = termPop.offsetHeight;
      let left = Math.min(r.left, innerWidth - w - 14);
      let top = r.bottom + 8;
      if (top + h > innerHeight - 10) top = r.top - h - 8;
      termPop.style.left = `${Math.max(10, left)}px`;
      termPop.style.top = `${Math.max(10, top)}px`;
    });
  });
}

/* ═══════════════════════════════════════════════════════════════
   初始化
   ═══════════════════════════════════════════════════════════════ */

function boot() {
  termPop = $("#termPop");
  loadPrefs();
  loadHistory();
  bindEvents();
  syncPrefsUI();
  autosize();
  $("#prefWhen").value = prefs.when || nowLocalInput();
  $("#prompt").placeholder = "寫下所問何事…";

  loadServerInfo();
}

async function loadServerInfo() {
  try {
    const [health, provRes, glosRes] = await Promise.all([
      api("/api/health"),
      api("/api/providers"),
      api("/api/glossary"),
    ]);
    S.config = health.llm;
    S.providers = provRes.providers || [];
    S.glossary = glosRes.glossary || {};
    renderLlmState();
    fillProviders();
    fillHexagramList();
  } catch (e) {
    const el = $("#llmState");
    if (el) {
      el.textContent = "未連線";
      el.className = "llm-state is-off";
      el.title = "無法連線到本機伺服器，請確認 ai/start.bat 正在執行";
    }
    console.error(e);
  }
}

function renderLlmState() {
  const el = $("#llmState");
  if (!el) return;
  if (!S.config) {
    el.textContent = "未連線";
    el.className = "llm-state is-off";
    el.title = "無法連線到本機伺服器";
    return;
  }
  if (S.config.configured) {
    el.textContent = S.config.model || S.config.provider_label;
    el.className = "llm-state is-ok";
    el.title = `已設定：${S.config.provider_label}／${S.config.model}`;
  } else {
    el.textContent = "未設定金鑰";
    el.className = "llm-state is-warn";
    el.title = "點「設定」填入 API 金鑰後才能解卦";
  }
}

/* ───────────── 事件 ───────────── */

function bindEvents() {
  $("#btnNew").addEventListener("click", resetChat);
  $("#btnSettings").addEventListener("click", openSettings);
  $("#btnCloseSettings").addEventListener("click", closeSettings);
  $("#sheetBackdrop").addEventListener("click", closeSettings);
  $("#btnSaveSettings").addEventListener("click", saveSettings);
  $("#btnClearKey").addEventListener("click", clearKey);
  $("#cfgProvider").addEventListener("change", onProviderChange);
  $("#cfgTemp").addEventListener("input", () => {
    $("#tempVal").textContent = Number($("#cfgTemp").value).toFixed(2);
  });
  $("#btnCopy").addEventListener("click", copyAnswer);

  $("#btnMenu").addEventListener("click", openNav);
  $("#navScrim").addEventListener("click", closeNav);

  $("#composer").addEventListener("submit", (e) => {
    e.preventDefault();
    handleSubmit();
  });
  $("#prompt").addEventListener("input", autosize);
  $("#prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      handleSubmit();
    }
  });

  $$("#prefMode .seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("#prefMode .seg-btn").forEach((b) => b.classList.toggle("is-on", b === btn));
      $("#prefManualWrap").hidden = btn.dataset.mode !== "manual";
    });
  });
  $$("#prefWhenMode .seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("#prefWhenMode .seg-btn").forEach((b) => b.classList.toggle("is-on", b === btn));
      const custom = btn.dataset.when === "custom";
      $("#prefWhenWrap").hidden = !custom;
      if (custom && !$("#prefWhen").value) $("#prefWhen").value = nowLocalInput();
    });
  });

  document.addEventListener("click", (e) => {
    if (termPop && !termPop.contains(e.target)) termPop.hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (termPop) termPop.hidden = true;
    if (!$("#settingsSheet").hidden) closeSettings();
    closeNav();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") persistAnswer();
  });
  window.addEventListener("beforeunload", persistAnswer);
}

function autosize() {
  const el = $("#prompt");
  if (!el || !el.style) return;
  el.style.height = "auto";
  const h = el.scrollHeight || 28;
  el.style.height = `${Math.min(Math.max(h, 28), 180)}px`;
}

function setBusyUI(busy, label) {
  S.busy = busy;
  const btn = $("#btnSend");
  const hint = $("#composerHint");
  if (btn) {
    btn.disabled = busy;
    btn.classList.toggle("is-busy", busy);
  }
  if (hint) hint.textContent = busy ? (label || "處理中…") : DEFAULT_HINT;
}

function flashWarn(msg, ms = 3600) {
  const el = $("#dockWarn");
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(flashWarn._t);
  flashWarn._t = setTimeout(() => { el.hidden = true; }, ms);
}

/* ═══════════════════════════════════════════════════════════════
   送出一問：先起卦，或接續追問
   ═══════════════════════════════════════════════════════════════ */

function handleSubmit() {
  const ta = $("#prompt");
  const text = ta.value.trim();
  if (!text) {
    flashWarn("先寫下所問何事。");
    ta.focus();
    return;
  }
  if (S.busy) return;
  if (!S.board) {
    if (prefs.mode === "manual" && !prefs.hexagram.trim()) {
      flashWarn("手動指定模式需要先設定卦名。");
      openSettings();
      return;
    }
    startCast(text);
  } else {
    sendFollowup(text);
  }
}

function buildCastBody(question) {
  const body = {
    question,
    yongshen: prefs.yongshen || null,
    use_coins: prefs.mode === "coins",
  };
  if (prefs.whenMode === "custom" && prefs.when) {
    const d = new Date(prefs.when);
    if (!Number.isNaN(d.getTime())) body.when = { iso: d.toISOString() };
  }
  if (prefs.mode === "manual") {
    body.hexagram = prefs.hexagram.trim();
    const raw = prefs.moving.trim();
    body.moving = raw
      ? raw.replace(/，/g, ",").split(",")
          .map((x) => parseInt(x.trim(), 10))
          .filter((n) => Number.isInteger(n) && n >= 1 && n <= 6)
      : [];
  }
  return body;
}

async function startCast(question) {
  if (S.busy) return;
  const epoch = ++S.epoch;
  setBusyUI(true, "起卦・排盤中…");
  $("#dockWarn").hidden = true;
  $("#empty").hidden = true;
  $("#thread").hidden = false;

  const pending = castingCard();
  $("#thread").appendChild(pending);
  scrollBottom(true);

  try {
    const [res] = await Promise.all([
      api("/api/cast", { method: "POST", body: JSON.stringify(buildCastBody(question)) }),
      sleep(420),
    ]);
    if (epoch !== S.epoch) return;
    if (!res || !res.ok) throw new Error((res && res.error) || "排盤失敗");

    const row = userRow(question, castStamp(res.board));
    $("#thread").insertBefore(row, pending);
    pending.remove();

    S.board = res.board;
    S.question = (res.meta && res.meta.question) || question;
    S.answer = "";

    const card = document.createElement("article");
    card.className = "board-card";
    card.innerHTML = renderBoard(res.board, res.meta || {});
    S.boardEl = card;
    $("#thread").appendChild(card);

    addHistory({
      id: `c${Date.now()}`,
      question: S.question,
      board: res.board,
      meta: res.meta || {},
      at: new Date().toISOString(),
    });

    $("#prompt").value = "";
    autosize();
    $("#prompt").placeholder = "針對此卦追問…";
    updateHeader();
    scrollBottom(true);

    if (!llmConfigured()) {
      setBusyUI(false);
      showSetupNotice();
      return;
    }
    await streamRead(res.board, S.question);
  } catch (e) {
    if (epoch !== S.epoch) return;
    pending.remove();
    setBusyUI(false);
    if (!S.board) {
      $("#thread").innerHTML = "";
      $("#thread").hidden = true;
      $("#empty").hidden = false;
    }
    flashWarn(e.message || String(e), 6000);
  }
}

async function sendFollowup(text) {
  if (S.busy) return;
  if (!llmConfigured()) {
    showSetupNotice();
    toast("尚未設定 API 金鑰");
    return;
  }
  const epoch = ++S.epoch;
  setBusyUI(true, "解讀中…");
  $("#prompt").value = "";
  autosize();

  $("#thread").appendChild(userRow(text, "追問"));
  const article = buildAnswerEl();
  $("#thread").appendChild(article);
  scrollBottom(true);

  const bodyEl = $(".answer-body", article);
  const modelEl = $(".answer-model", article);
  let acc = "";

  try {
    await ssePost("/api/followup", {
      board: S.board,
      question: S.question,
      prior_answer: S.answer,
      followup: text,
    }, {
      delta: (t) => {
        if (epoch !== S.epoch) return;
        removeThinking(article);
        acc += t;
        bodyEl.innerHTML = renderMd(acc) + '<span class="caret"></span>';
        bindTerms(bodyEl);
        scrollBottom(false);
      },
      done: () => {
        if (epoch !== S.epoch) return;
        bodyEl.innerHTML = renderMd(acc);
        bindTerms(bodyEl);
        modelEl.textContent = "答";
        removeThinking(article);
        scrollBottom(false);
      },
      error: (d) => { throw new Error(d.message || "追問失敗"); },
    });
  } catch (e) {
    if (epoch !== S.epoch) return;
    removeThinking(article);
    const err = document.createElement("div");
    err.className = "err-box";
    err.textContent = e.message || String(e);
    article.appendChild(err);
    scrollBottom(false);
  } finally {
    if (epoch === S.epoch) setBusyUI(false);
  }
}

/* ───────────── SSE 解讀 ───────────── */

function buildAnswerEl() {
  const wrap = document.createElement("article");
  wrap.className = "answer";
  wrap.innerHTML = `
    <div class="answer-head">
      <span class="answer-seal">斷</span>
      <span class="answer-label">解卦</span>
      <span class="answer-model">解讀中…</span>
    </div>
    <div class="thinking">
      <span class="thinking-dots"><i></i><i></i><i></i></span>
      <span class="thinking-text">依八步斷卦…</span>
    </div>
    <div class="answer-body"></div>`;
  return wrap;
}

function removeThinking(article) {
  const t = $(".thinking", article);
  if (t && t.remove) t.remove();
  else if (t) t.hidden = true;
}

async function streamRead(board, question) {
  const epoch = ++S.epoch;
  const article = buildAnswerEl();
  $("#thread").appendChild(article);
  scrollBottom(true);

  const bodyEl = $(".answer-body", article);
  const modelEl = $(".answer-model", article);
  let acc = "";

  try {
    await ssePost("/api/read", {
      board,
      question: board.question || question,
    }, {
      board: (data) => {
        if (epoch !== S.epoch) return;
        if (!sameCast(data, board)) {
          console.warn("[liuyao] 卦盤不一致，已同步為伺服器實際解讀的卦盤", { shown: board, used: data });
          S.board = data;
          if (S.boardEl) S.boardEl.innerHTML = renderBoard(data, {});
          const item = S.history.find((h) => h.id === S.activeHistoryId);
          if (item) { item.board = data; saveHistory(); }
          const note = document.createElement("div");
          note.className = "err-box";
          note.textContent = "注意：解讀所用的卦盤與原先排出的不同，畫面已同步為實際解讀的卦盤。";
          article.parentNode && article.parentNode.insertBefore(note, article);
        }
      },
      meta: (data) => {
        if (epoch !== S.epoch) return;
        modelEl.textContent = `${data.provider} · ${data.model}`;
        removeThinking(article);
      },
      delta: (text) => {
        if (epoch !== S.epoch) return;
        removeThinking(article);
        acc += text;
        bodyEl.innerHTML = renderMd(acc) + '<span class="caret"></span>';
        bindTerms(bodyEl);
        scrollBottom(false);
      },
      error: (data) => { throw new Error(data.message || "解卦失敗"); },
      done: () => {
        if (epoch !== S.epoch) return;
        bodyEl.innerHTML = renderMd(acc);
        bindTerms(bodyEl);
        removeThinking(article);
        S.answer = acc;
        persistAnswer();
        updateHeader();
        scrollBottom(false);
      },
    });
  } catch (e) {
    if (epoch !== S.epoch) return;
    removeThinking(article);
    if (acc) {
      bodyEl.innerHTML = renderMd(acc);
      bindTerms(bodyEl);
      S.answer = acc;
    }
    const err = document.createElement("div");
    err.className = "err-box";
    err.innerHTML = esc(e.message || String(e));
    if (e.needSettings || /API key|金鑰|設定/.test(e.message || "")) {
      err.innerHTML += '<div class="err-actions"><button class="btn-outline" type="button">前往設定</button></div>';
      const btn = $(".err-actions button", err);
      if (btn) btn.addEventListener("click", openSettings);
    }
    article.appendChild(err);
    scrollBottom(false);
  } finally {
    if (epoch === S.epoch) setBusyUI(false);
  }
}

function sameCast(a, b) {
  if (!a || !b) return false;
  const moving = (x) => (x.moving_positions || []).slice().sort((p, q) => p - q).join(",");
  return String(a.hexagram || "") === String(b.hexagram || "")
    && String(a.changed_hexagram || "") === String(b.changed_hexagram || "")
    && String(a.cast_time && a.cast_time.moment || "") === String(b.cast_time && b.cast_time.moment || "")
    && moving(a) === moving(b);
}

function ssePost(path, body, handlers) {
  return fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then(async (res) => {
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const err = new Error(data.error || `HTTP ${res.status}`);
      err.needSettings = !!data.need_settings;
      throw err;
    }
    if (!res.body) throw new Error("此瀏覽器不支援串流回應。");

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buf = "";

    const dispatch = (chunk) => {
      for (const block of chunk.split("\n\n")) {
        if (!block.trim()) continue;
        let event = "message";
        const dataLines = [];
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
          else if (line.startsWith("data:")) dataLines.push(line.slice(5));
        }
        if (!dataLines.length) continue;
        const raw = dataLines.join("\n");
        let payload = raw;
        try { payload = JSON.parse(raw); } catch { /* 純文字 */ }
        const h = handlers[event];
        if (h) h(payload);
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const idx = buf.lastIndexOf("\n\n");
      if (idx >= 0) {
        const ready = buf.slice(0, idx + 2);
        buf = buf.slice(idx + 2);
        dispatch(ready);
      }
    }
    if (buf.trim()) dispatch(buf);
  });
}

/* ═══════════════════════════════════════════════════════════════
   對話元素
   ═══════════════════════════════════════════════════════════════ */

function userRow(text, stamp) {
  const div = document.createElement("div");
  div.className = "row row-user";
  div.innerHTML = `<div class="user-bubble">${esc(text)}</div>`
    + (stamp ? `<div class="row-meta">${esc(stamp)}</div>` : "");
  return div;
}

function castStamp(board) {
  const ct = (board && board.cast_time) || {};
  if (!ct.moment_display) return "起卦";
  return `${ct.moment_display}　${ct.shichen || ""}時　起卦`;
}

function castingCard() {
  const div = document.createElement("div");
  div.className = "casting";
  div.innerHTML = `
    <div class="casting-label">擲錢・排盤</div>
    <div class="casting-hex">
      <span class="casting-bar"></span><span class="casting-bar"></span>
      <span class="casting-bar"></span><span class="casting-bar"></span>
      <span class="casting-bar"></span><span class="casting-bar"></span>
    </div>`;
  return div;
}

function showSetupNotice() {
  if (!S.board) return;
  $$(".notice", $("#thread")).forEach((el) => el.remove());
  const el = document.createElement("div");
  el.className = "notice";
  el.innerHTML = `
    <span class="notice-mark">!</span>
    <div class="notice-body">
      <b>卦盤已排好，尚未設定 API 金鑰</b>
      <p>到「設定」填入金鑰，就能解這一卦；卦已定，不會重擲。</p>
    </div>
    <button class="btn-outline" type="button">前往設定</button>`;
  const btn = $("button", el);
  if (btn) {
    btn.addEventListener("click", () => {
      S.pendingRead = () => {
        if (!S.board) return;
        if (el.remove) el.remove();
        streamRead(S.board, S.question);
      };
      openSettings();
    });
  }
  $("#thread").appendChild(el);
  scrollBottom(true);
}

function scrollBottom(force) {
  const vp = $("#viewport");
  if (!vp) return;
  const gap = vp.scrollHeight - vp.scrollTop - vp.clientHeight;
  if (force || gap < 180) vp.scrollTop = vp.scrollHeight;
}

function updateHeader() {
  const title = S.question || "新的占問";
  const titleEl = $("#chatTitle");
  if (titleEl) {
    titleEl.textContent = title;
    titleEl.title = title;
  }
  const sub = $("#chatSub");
  if (sub) {
    if (S.board) {
      const b = S.board;
      const ct = b.cast_time || {};
      const gua = b.hexagram + (b.changed_hexagram && b.changed_hexagram !== b.hexagram ? " → " + b.changed_hexagram : "");
      sub.textContent = `${gua}　·　${ct.month_gz || ""}月${ct.day_gz || ""}日`;
      sub.hidden = false;
    } else {
      sub.textContent = "";
      sub.hidden = true;
    }
  }
  const copy = $("#btnCopy");
  if (copy) copy.hidden = !S.answer;
}

/* ═══════════════════════════════════════════════════════════════
   卦盤渲染（輸出寫入 #boardContent，再掛成卡片）
   ═══════════════════════════════════════════════════════════════ */

function renderBoard(board, meta) {
  const ct = board.cast_time || {};
  const changed = board.changed_hexagram && board.changed_hexagram !== board.hexagram
    ? board.changed_hexagram
    : "";
  const lines = board.lines || [];
  const changedByPos = new Map((board.changed_lines || []).map((l) => [l.pos, l]));

  const barHtml = (yinYang) => {
    const yin = yinYang === "陰";
    return yin
      ? '<div class="h-bars yin"><span class="h-bar"></span><span class="h-bar"></span></div>'
      : '<div class="h-bars yang"><span class="h-bar"></span></div>';
  };

  const mainRows = lines.map((ln) => {
    const flag = ln.pos === board.world_pos ? "世" : ln.pos === board.response_pos ? "應" : "";
    return `
      <div class="brow main ${ln.is_moving ? "is-moving" : ""}">
        <span class="b-shen">${esc(ln.shen)}</span>
        <span class="b-qin">${esc(ln.qin)}</span>
        <span class="b-najia">${esc(ln.gan)}${esc(ln.zhi)}${esc(ln.wx)}</span>
        <span class="b-bars-wrap">
          <span class="b-bars">${barHtml(ln.yin_yang)}</span>
          <span class="b-mark">${flag}</span>
        </span>
      </div>`;
  }).join("");

  const changedRows = changed
    ? lines.map((ln) => {
        const ch = changedByPos.get(ln.pos);
        if (!ch) return "";
        const wx = ch.wx || ZHI_WX[ch.zhi] || "";
        return `
          <div class="brow changed ${ln.is_moving ? "is-moving" : ""}">
            <span class="b-qin">${esc(ch.qin)}</span>
            <span class="b-najia">${esc(ch.gan)}${esc(ch.zhi)}${esc(wx)}</span>
            <span class="b-bars">${barHtml(ch.yin_yang)}</span>
          </div>`;
      }).join("")
    : "";

  const html = `
    <header class="b-head">
      <span class="b-four-label">四值</span>
      <span class="b-when">${esc(ct.year_gz)}年　${esc(ct.month_gz)}月　${esc(ct.day_gz)}日　${esc(ct.shichen)}時</span>
    </header>

    <div class="b-split${changed ? "" : " solo"}">
      <section class="b-side">
        <div class="b-col-head">
          <span class="b-col-name">${esc(board.hexagram)}</span>
          <span class="b-col-sub">${esc(board.palace)}宮 · ${esc(board.palace_wx)}</span>
        </div>
        <div class="b-rows">${mainRows}</div>
      </section>
      ${changed ? `<section class="b-side b-side-changed">
        <div class="b-col-head">
          <span class="b-col-name">${esc(changed)}</span>
          <span class="b-col-sub">變卦</span>
        </div>
        <div class="b-rows">${changedRows}</div>
      </section>` : ""}
    </div>`;

  const host = $("#boardContent");
  if (host) host.innerHTML = html;
  return html;
}

/* ═══════════════════════════════════════════════════════════════
   設定與占問偏好
   ═══════════════════════════════════════════════════════════════ */

function fillProviders() {
  const sel = $("#cfgProvider");
  if (!sel) return;
  sel.innerHTML = S.providers
    .map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`)
    .join("");
  if (S.config) sel.value = S.config.provider;
}

function fillHexagramList() {
  const names = [
    "乾為天", "坤為地", "水雷屯", "山水蒙", "水天需", "天水訟", "地水師", "水地比",
    "風天小畜", "天澤履", "地天泰", "天地否", "天火同人", "火天大有", "地山謙", "雷地豫",
    "澤雷隨", "山風蠱", "地澤臨", "風地觀", "火雷噬嗑", "山火賁", "山地剝", "地雷復",
    "天雷無妄", "山天大畜", "山雷頤", "澤風大過", "坎為水", "離為火", "澤山咸", "雷風恆",
    "天山遁", "雷天大壯", "火地晉", "地火明夷", "風火家人", "火澤睽", "水山蹇", "雷水解",
    "山澤損", "風雷益", "澤天夬", "天風姤", "澤地萃", "地風升", "澤水困", "水風井",
    "澤火革", "火風鼎", "震為雷", "艮為山", "風山漸", "雷澤歸妹", "雷火豐", "火山旅",
    "巽為風", "兌為澤", "風水渙", "水澤節", "風澤中孚", "雷山小過", "水火既濟", "火水未濟",
  ];
  const list = $("#hexList");
  if (list) list.innerHTML = names.map((n) => `<option value="${n}">`).join("");
}

function loadPrefs() {
  try {
    const raw = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
    if (raw.mode === "coins" || raw.mode === "manual") prefs.mode = raw.mode;
    if (typeof raw.yongshen === "string") prefs.yongshen = raw.yongshen;
    if (raw.whenMode === "now" || raw.whenMode === "custom") prefs.whenMode = raw.whenMode;
    if (typeof raw.when === "string") prefs.when = raw.when;
    if (typeof raw.hexagram === "string") prefs.hexagram = raw.hexagram;
    if (typeof raw.moving === "string") prefs.moving = raw.moving;
  } catch {
    /* 忽略壞資料 */
  }
}

function savePrefs() {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch (e) {
    console.warn("無法寫入本機偏好", e);
  }
}

function syncPrefsUI() {
  $$("#prefMode .seg-btn").forEach((b) => b.classList.toggle("is-on", b.dataset.mode === prefs.mode));
  $$("#prefWhenMode .seg-btn").forEach((b) => b.classList.toggle("is-on", b.dataset.when === prefs.whenMode));
  const ys = $("#prefYongshen");
  if (ys) ys.value = prefs.yongshen;
  const hex = $("#prefHex");
  if (hex) hex.value = prefs.hexagram;
  const mv = $("#prefMoving");
  if (mv) mv.value = prefs.moving;
  const when = $("#prefWhen");
  if (when && prefs.when) when.value = prefs.when;
  const whenWrap = $("#prefWhenWrap");
  if (whenWrap) whenWrap.hidden = prefs.whenMode !== "custom";
  const manualWrap = $("#prefManualWrap");
  if (manualWrap) manualWrap.hidden = prefs.mode !== "manual";
  updateDockNote();
}

function updateDockNote() {
  const el = $("#dockNote");
  if (!el) return;
  const bits = [];
  if (prefs.mode === "manual") {
    bits.push(prefs.hexagram ? `手動指定：${prefs.hexagram}` : "手動指定");
  }
  if (prefs.yongshen) bits.push(`用神 ${prefs.yongshen}`);
  if (prefs.whenMode === "custom" && prefs.when) {
    bits.push(`指定時間 ${prefs.when.replace("T", " ")}`);
  }
  el.textContent = bits.join("　·　");
  el.hidden = bits.length === 0;
}

function activeSeg(sel) {
  const on = $(`${sel} .seg-btn.is-on`);
  return on ? on.dataset : {};
}

function openSettings() {
  if (!S.config) {
    toast("伺服器未連線，無法開啟設定");
    return;
  }
  syncSettingsForm();
  const err = $("#sheetError");
  if (err) err.hidden = true;
  $("#sheetBackdrop").hidden = false;
  $("#settingsSheet").hidden = false;
  const sheet = $("#settingsSheet");
  if (sheet && sheet.focus) setTimeout(() => sheet.focus(), 30);
  closeNav();
}

function syncSettingsForm() {
  if (!S.config) return;
  $("#cfgProvider").value = S.config.provider;
  $("#cfgModel").value = S.config.model || "";
  $("#cfgKey").value = "";
  $("#cfgKey").placeholder = S.config.has_key ? "已設定，留空不變" : "貼上 API key";
  const keyHint = $("#cfgKeyHint");
  if (keyHint) {
    keyHint.textContent = S.config.has_key
      ? `已設定（${S.config.key_hint || "已儲存"}）；留空則不變。`
      : "";
  }
  $("#cfgBase").value = S.config.base_url || "";
  $("#cfgBaseWrap").hidden = S.config.provider !== "custom";
  $("#cfgTemp").value = S.config.temperature;
  $("#tempVal").textContent = Number(S.config.temperature).toFixed(2);
  $("#cfgMax").value = S.config.max_tokens;

  const spec = S.providers.find((p) => p.id === S.config.provider);
  const list = $("#modelList");
  if (list) list.innerHTML = ((spec && spec.models) || []).map((m) => `<option value="${esc(m)}">`).join("");

  updateCfgNote();
  syncPrefsUI();
  if (!$("#prefWhen").value) $("#prefWhen").value = nowLocalInput();
}

function updateCfgNote() {
  const note = $("#cfgNote");
  if (!note) return;
  const pid = $("#cfgProvider").value;
  const meta = S.config && S.config.provider === pid ? S.config : null;
  const url = (meta && meta.key_url) || "";
  note.innerHTML = [
    "金鑰只儲存在本機 <code>ai/config/llm.json</code>，不會上傳到任何第三方。",
    url ? `取得金鑰：<a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a>` : "",
    meta && meta.env_key ? `也可改用環境變數 <code>${esc(meta.env_key)}</code>。` : "",
  ].filter(Boolean).join("<br>");
}

function closeSettings() {
  $("#sheetBackdrop").hidden = true;
  $("#settingsSheet").hidden = true;
}

function onProviderChange() {
  const pid = $("#cfgProvider").value;
  const p = S.providers.find((x) => x.id === pid);
  if (!p) return;
  $("#cfgModel").value = p.default_model || "";
  const list = $("#modelList");
  if (list) list.innerHTML = (p.models || []).map((m) => `<option value="${esc(m)}">`).join("");
  $("#cfgBaseWrap").hidden = pid !== "custom";
  // 切換供應商後，舊供應商的端點與金鑰不可沿用到新供應商
  $("#cfgBase").value = "";
  $("#cfgKey").value = "";
  $("#cfgKey").placeholder = "貼上 API key";
  const hint = $("#cfgKeyHint");
  if (hint) hint.textContent = "";
  updateCfgNote();
}

function showSheetError(msg) {
  const el = $("#sheetError");
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
}

async function saveSettings() {
  if (!S.config) return;

  const mode = (activeSeg("#prefMode").mode) || "coins";
  const whenMode = (activeSeg("#prefWhenMode").when) || "now";
  const hex = $("#prefHex").value.trim();
  const whenVal = $("#prefWhen").value;

  if (mode === "manual" && !hex) {
    showSheetError("手動指定需要填卦名（例：地澤臨，或只填「臨」）。");
    return;
  }
  if (whenMode === "custom" && !whenVal) {
    showSheetError("請指定占卦時間，或改回「現在」。");
    return;
  }

  const pid = $("#cfgProvider").value;
  const p = S.providers.find((x) => x.id === pid);
  const baseUrl = $("#cfgBase").value.trim();
  const modelVal = $("#cfgModel").value.trim();
  if (pid === "custom" && !baseUrl) {
    showSheetError("自訂端點需要填 Base URL（例：https://your-endpoint/v1）。");
    return;
  }
  if (pid === "custom" && !modelVal) {
    showSheetError("自訂端點需要填模型名稱（例：deepseek-chat）。");
    return;
  }
  const payload = {
    provider: pid,
    model: modelVal || (p && p.default_model) || "",
    base_url: pid === "custom" ? baseUrl : "",
    temperature: Number($("#cfgTemp").value),
    max_tokens: Number($("#cfgMax").value),
  };
  const key = $("#cfgKey").value.trim();
  if (key) payload.api_key = key;

  const btn = $("#btnSaveSettings");
  btn.disabled = true;
  btn.textContent = "儲存中…";
  const errEl = $("#sheetError");
  if (errEl) errEl.hidden = true;

  try {
    const res = await api("/api/settings", { method: "POST", body: JSON.stringify(payload) });
    if (!res.ok) throw new Error(res.error || "儲存失敗");
    S.config = res.settings;

    prefs.mode = mode;
    prefs.yongshen = $("#prefYongshen").value;
    prefs.whenMode = whenMode;
    prefs.when = whenVal;
    prefs.hexagram = hex;
    prefs.moving = $("#prefMoving").value.trim();
    savePrefs();
    updateDockNote();
    renderLlmState();
    closeSettings();
    toast("設定已儲存");

    if (S.pendingRead && llmConfigured()) {
      const fn = S.pendingRead;
      S.pendingRead = null;
      setTimeout(fn, 120);
    }
  } catch (e) {
    showSheetError(e.message || String(e));
  } finally {
    btn.disabled = false;
    btn.textContent = "儲存設定";
  }
}

async function clearKey() {
  if (!S.config) return;
  const btn = $("#btnClearKey");
  btn.disabled = true;
  try {
    const res = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({ clear_key: true }),
    });
    if (!res.ok) throw new Error(res.error || "清除失敗");
    S.config = res.settings;
    $("#cfgKey").value = "";
    $("#cfgKey").placeholder = "貼上 API key";
    $("#cfgKeyHint").textContent = "金鑰已清除。";
    renderLlmState();
    toast("金鑰已清除");
  } catch (e) {
    showSheetError(e.message || String(e));
  } finally {
    btn.disabled = false;
  }
}

/* ═══════════════════════════════════════════════════════════════
   占問紀錄（localStorage）
   ═══════════════════════════════════════════════════════════════ */

function loadHistory() {
  try {
    S.history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    if (!Array.isArray(S.history)) S.history = [];
  } catch {
    S.history = [];
  }
  S.history = S.history.filter((h) => h && h.board && h.board.hexagram);
  renderHistory();
}

function saveHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(S.history.slice(0, MAX_HISTORY)));
  } catch (e) {
    console.warn("無法寫入本機紀錄", e);
  }
}

function addHistory(entry) {
  S.history = [entry, ...S.history.filter((h) => h.id !== entry.id)].slice(0, MAX_HISTORY);
  saveHistory();
  S.activeHistoryId = entry.id;
  renderHistory();
}

function renderHistory() {
  const ul = $("#history");
  if (!ul) return;
  const empty = $("#historyEmpty");
  if (empty) empty.hidden = S.history.length > 0;
  const count = $("#historyCount");
  if (count) count.textContent = S.history.length ? String(S.history.length) : "";

  ul.innerHTML = S.history.map((h) => {
    const b = h.board || {};
    const label = `${b.hexagram || ""}${b.changed_hexagram && b.changed_hexagram !== b.hexagram ? " → " + b.changed_hexagram : ""}`;
    return `<li>
      <button class="history-btn ${h.id === S.activeHistoryId ? "is-on" : ""}"
        data-id="${esc(h.id)}" type="button">
        <span class="history-title">${esc(h.question || "（未命名占問）")}</span>
        <span class="history-meta">${esc(label)}<i>·</i>${esc(relTime(h.at))}</span>
      </button>
      <button class="history-del" type="button" data-del="${esc(h.id)}"
        title="刪除這筆紀錄" aria-label="刪除這筆占問紀錄">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 7h16M10 11v6M14 11v6M6.5 7l.9 13h9.2l.9-13M9 7V4.5A.5.5 0 0 1 9.5 4h5a.5.5 0 0 1 .5.5V7"/>
        </svg>
      </button>
    </li>`;
  }).join("");

  $$(".history-btn", ul).forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = S.history.find((h) => h.id === btn.dataset.id);
      if (item) restoreHistory(item);
    });
  });
  $$(".history-del", ul).forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteHistory(btn.dataset.del);
    });
  });
}

function deleteHistory(id) {
  const item = S.history.find((h) => h.id === id);
  if (!item) return;
  const wasActive = S.activeHistoryId === id;
  S.history = S.history.filter((h) => h.id !== id);
  saveHistory();
  if (wasActive) {
    resetChat();
  } else {
    renderHistory();
  }
  toast("已刪除占問紀錄");
}

function restoreHistory(item) {
  if (S.busy) {
    toast("解讀進行中，請稍候");
    return;
  }
  S.epoch++;
  S.board = item.board;
  S.question = item.question;
  S.answer = (item.meta && item.meta.answer) || item.answer || "";
  S.activeHistoryId = item.id;
  S.boardEl = null;

  $("#empty").hidden = true;
  $("#thread").hidden = false;
  $("#thread").innerHTML = "";
  $("#thread").appendChild(userRow(item.question, castStamp(item.board)));

  const card = document.createElement("article");
  card.className = "board-card";
  card.innerHTML = renderBoard(item.board, item.meta || {});
  S.boardEl = card;
  $("#thread").appendChild(card);

  if (S.answer) {
    const article = document.createElement("article");
    article.className = "answer";
    article.innerHTML = `
      <div class="answer-head">
        <span class="answer-seal">斷</span>
        <span class="answer-label">解卦</span>
        <span class="answer-model">${esc((item.meta && item.meta.provider_label) || "已存解讀")}</span>
      </div>
      <div class="answer-body">${renderMd(S.answer)}</div>`;
    $("#thread").appendChild(article);
    bindTerms(article);
  }

  $("#prompt").placeholder = "針對此卦追問…";
  $("#prompt").value = "";
  autosize();
  updateHeader();
  renderHistory();
  closeNav();
  scrollBottom(true);
  setBusyUI(false);
}

/* 保存解卦結果到紀錄 */
function persistAnswer() {
  if (!S.activeHistoryId || !S.answer) return;
  const item = S.history.find((h) => h.id === S.activeHistoryId);
  if (!item) return;
  item.answer = S.answer;
  item.meta = item.meta || {};
  item.meta.answer = S.answer;
  item.meta.provider = S.config ? S.config.provider_label : "";
  item.meta.provider_label = S.config ? S.config.provider_label : "";
  saveHistory();
  const copy = $("#btnCopy");
  if (copy) copy.hidden = false;
}

/* ═══════════════════════════════════════════════════════════════
   新局、複製、側欄
   ═══════════════════════════════════════════════════════════════ */

function resetChat() {
  S.epoch++;
  S.board = null;
  S.boardEl = null;
  S.question = "";
  S.answer = "";
  S.activeHistoryId = null;
  S.pendingRead = null;
  S.busy = false;

  const thread = $("#thread");
  thread.innerHTML = "";
  thread.hidden = true;
  $("#empty").hidden = false;
  $("#prompt").value = "";
  $("#prompt").placeholder = "寫下所問何事…";
  autosize();
  updateHeader();
  renderHistory();
  setBusyUI(false);
  $("#dockWarn").hidden = true;
  closeNav();
  const vp = $("#viewport");
  if (vp) vp.scrollTop = 0;
  $("#prompt").focus();
}

async function copyAnswer() {
  if (!S.answer) return;
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(S.answer);
    } else {
      const ta = document.createElement("textarea");
      ta.value = S.answer;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      if (ta.remove) ta.remove();
    }
    toast("已複製解卦內容");
  } catch {
    toast("複製失敗，請手動選取");
  }
}

function openNav() {
  document.body.classList.add("nav-open");
  const scrim = $("#navScrim");
  if (scrim) scrim.hidden = false;
}

function closeNav() {
  document.body.classList.remove("nav-open");
  const scrim = $("#navScrim");
  if (scrim) scrim.hidden = true;
}

/* ───────────── 啟動 ───────────── */

boot();
