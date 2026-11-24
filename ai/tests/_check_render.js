/**
 * 前端渲染單元測試：在 Node 裡以極簡 DOM 模擬執行 app.js，
 * 驗證 renderMd / renderBoard 的輸出正確（不啟動瀏覽器）。
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP = path.join(__dirname, "..", "web", "assets", "app.js");
const code = fs.readFileSync(APP, "utf8");

/* ───────── 極簡 DOM 模擬 ───────── */

class El {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.attrs = {};
    this._html = "";
    this._text = "";
    this.classList = {
      _s: new Set(),
      add(...c) { c.forEach((x) => this._s.add(x)); },
      remove(...c) { c.forEach((x) => this._s.delete(x)); },
      contains(c) { return this._s.has(c); },
      toggle(c, force) {
        const on = force === undefined ? !this._s.has(c) : force;
        on ? this._s.add(c) : this._s.delete(c);
        return on;
      },
    };
    this.style = {};
    this.dataset = {};
    this.hidden = false;
    this.value = "";
    this.disabled = false;
    this.listeners = {};
  }
  set innerHTML(v) { this._html = String(v); }
  get innerHTML() { return this._html; }
  set textContent(v) { this._text = String(v); }
  get textContent() { return this._text; }
  appendChild(c) { this.children.push(c); return c; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  removeEventListener() {}
  getBoundingClientRect() { return { left: 0, top: 0, right: 100, bottom: 20, width: 100, height: 20 }; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  focus() {}
  scrollTo() {}
  click() {}
  contains() { return false; }
}

const registry = new Map();
function makeEl(sel) {
  if (!registry.has(sel)) registry.set(sel, new El("div"));
  return registry.get(sel);
}

const documentStub = {
  querySelector: (s) => makeEl(s),
  querySelectorAll: () => [],
  createElement: (t) => new El(t),
  addEventListener: () => {},
  body: new El("body"),
  visibilityState: "visible",
};

const storage = {
  _d: {},
  getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};

const sandbox = {
  document: documentStub,
  window: { addEventListener: () => {}, scrollTo: () => {}, innerWidth: 1560, innerHeight: 1000 },
  localStorage: storage,
  fetch: () => Promise.reject(new Error("no network in test")),
  console,
  setTimeout, clearTimeout, setInterval, clearInterval,
  Date, JSON, Math, String, Number, Array, Object, Promise, Error,
  TextDecoder,
  innerWidth: 1560, innerHeight: 1000,
};
sandbox.globalThis = sandbox;
sandbox.window.document = documentStub;

/* 執行 app.js（它會自動 boot()，fetch 會失敗但被 catch） */
/* 執行 app.js（它會自動 boot()；以假 fetch 回應，避免未捕捉的 rejection 噪音） */
const fakeResponse = {
  ok: true,
  status: 200,
  json: async () => ({
    ok: true, llm: { configured: false, provider_label: "DeepSeek", model: "",
                     provider: "deepseek", has_key: false, key_hint: "",
                     base_url: "", temperature: 0.7, max_tokens: 4000,
                     models: [], env_key: "", key_url: "" },
    sections_indexed: 192, docs_indexed: 13,
    providers: [{ id: "deepseek", label: "DeepSeek", models: [], default_model: "deepseek-chat" }],
    glossary: { 暗動: "旺相之靜爻被日辰沖，激發起用。" },
    settings: { provider: "deepseek", provider_label: "DeepSeek", model: "deepseek-chat",
                base_url: "https://api.deepseek.com", temperature: 0.7, max_tokens: 4000,
                configured: false, has_key: false, key_hint: "", env_key: "", key_url: "", models: [] },
  }),
};
sandbox.fetch = () => Promise.resolve(fakeResponse);

const ctx = vm.createContext(sandbox);
vm.runInContext(code, ctx, { filename: "app.js" });

/* 取得內部函式（app.js 用 const 宣告在頂層，vm 中需以 eval 取用） */
const get = (name) => vm.runInContext(name, ctx);

let fails = [];
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
  console.log(`${ok ? "OK  " : "FAIL"} ${label}: ${JSON.stringify(got)}`);
}

/* ───────── 1. Markdown 渲染 ───────── */

console.log("=== 1. Markdown 渲染 ===");
const renderMd = get("renderMd");

const md = `## 一、總斷

此緣**本質相生**，然*時機未至*。

- 第一點
- 第二點

> 引文一句

1. 步驟一
2. 步驟二
`;
const html = renderMd(md);
check("產生 h2", html.includes("<h2>一、總斷</h2>"));
check("粗體", html.includes("<strong>本質相生</strong>"));
check("斜體", html.includes("<em>時機未至</em>"));
check("清單", html.includes("<ul><li>第一點</li>"));
check("有序清單", html.includes("<ol><li>步驟一</li>"));
check("引文", html.includes("<blockquote>"));
check("段落", html.includes("<p>"));
check("不含未轉義標記", !html.includes("**"));
console.log("      樣本：", html.slice(0, 120).replace(/\n/g, " "));

console.log("\n=== 2. XSS 轉義 ===");
const evil = renderMd(`<script>alert(1)</script> 與 <img src=x onerror=alert(2)>`);
check("script 被轉義", evil.includes("&lt;script&gt;"));
check("img 被轉義", evil.includes("&lt;img"));
check("無原始 script 標籤", !evil.includes("<script>"));

/* ───────── 3. 卦盤渲染 ───────── */

console.log("\n=== 3. 卦盤渲染 ===");
const renderBoard = get("renderBoard");
const board = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "board_lilin.json"), "utf8"));
const boardEl = makeEl("#boardContent");
const emptyEl = makeEl("#boardEmpty");

renderBoard(board, {});

const out = boardEl.innerHTML;
check("有主卦名", out.includes("地澤臨"));
check("有變卦名", out.includes("地雷復"));
check("有主卦六列", (out.match(/class="brow main/g) || []).length === 6);
check("有變卦六列", (out.match(/class="brow changed/g) || []).length === 6);
check("標出動爻", out.includes("is-moving"));
check("有世應獨立欄", (out.match(/class="b-mark"/g) || []).length === 6);
check("世應有值", out.includes('class="b-mark">世<') && out.includes('class="b-mark">應<'));
check("不用動爻圓圈", !out.includes("b-move"));
check("有四值月柱", out.includes("乙未月"));
check("有四值日柱", out.includes("辛卯日"));
check("有六神", out.includes("螣蛇"));
check("有六親", out.includes("子孫"));
check("有世應", out.includes("世") && out.includes("應"));
check("有納甲", out.includes("癸酉金"));
check("有變卦納甲", out.includes("庚子水"));
check("不顯示旬空", !out.includes("旬空"));
check("不顯示暗動標籤", !out.includes("暗動"));
check("不顯示化退神", !out.includes("化退神"));
check("不顯示卦辭", !out.includes("元，亨，利，貞"));
check("不顯示技術細節", !out.includes("完整卦盤"));
console.log(`      輸出長度 ${out.length} 字，主卦 ${(out.match(/class="brow main/g) || []).length} 列，變卦 ${(out.match(/class="brow changed/g) || []).length} 列`);

/* ───────── 4. 爻名與陰陽條 ───────── */

console.log("\n=== 4. 陰陽爻渲染 ===");
check("陽爻條", out.includes('class="h-bars yang"'));
check("陰爻條", out.includes('class="h-bars yin"'));

/* ───────── 5. 歷史紀錄 ───────── */

console.log("\n=== 5. 本機紀錄 ===");
const addHistory = get("addHistory");
addHistory({
  id: "t1", question: "測試占問", board,
  meta: { answer: "測試解答" }, at: new Date().toISOString(),
});
const raw = storage.getItem("liuyao.history.v1");
check("已寫入 localStorage", !!raw);
const parsed = JSON.parse(raw);
check("紀錄有 1 筆", parsed.length === 1);
check("紀錄帶卦名", parsed[0].board.hexagram === "地澤臨");

const deleteHistory = get("deleteHistory");
const S = get("S");
deleteHistory("t1");
check("刪除後記憶體清空", S.history.length, 0);
check("刪除後 localStorage 清空", JSON.parse(storage.getItem("liuyao.history.v1")).length, 0);

console.log("\n" + "=".repeat(60));
if (fails.length) {
  console.log(`❌ ${fails.length} 項失敗：`);
  fails.forEach((f) => console.log("  -", f));
  process.exit(1);
}
console.log("✅ 全部通過");
