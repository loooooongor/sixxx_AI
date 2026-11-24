/**
 * 產生離線預覽頁：把「真實排盤資料」用正式 CSS 渲染成一份靜態 HTML。
 *
 * 用途：本機沙盒無法啟動 Chrome/Edge 截圖（需具名管道 IPC），
 * 故改以「實際 API 資料 + 實際 CSS + 實際渲染函式」產生可雙擊開啟的預覽，
 * 讓你能直接看到介面長相，且內容與真實結果一致。
 *
 * 用法：
 *   node tools/make_preview.js <api-base> <out-html>
 */

const fs = require("fs");
const path = require("path");
const http = require("http");

const API = process.argv[2] || "http://127.0.0.1:8848";
const OUT = process.argv[3] || path.join(__dirname, "..", "preview.html");
const ROOT = path.join(__dirname, "..");
const CSS = fs.readFileSync(path.join(ROOT, "web", "assets", "app.css"), "utf8");

function post(p, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(p, API);
    const data = JSON.stringify(body);
    const req = http.request(
      { hostname: url.hostname, port: url.port, path: url.pathname, method: "POST",
        headers: { "content-type": "application/json",
                   "content-length": Buffer.byteLength(data) } },
      (res) => {
        let buf = "";
        res.setEncoding("utf8");
        res.on("data", (d) => (buf += d));
        res.on("end", () => resolve(JSON.parse(buf)));
      });
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* ── 重用 app.js 的渲染邏輯（載入到 vm 需要 DOM，這裡改為精簡重寫） ── */

function renderLines(board) {
  return board.lines.map((ln, i) => {
    const yin = ln.yin_yang === "陰";
    const bars = yin
      ? '<div class="h-bars yin"><span class="h-bar"></span><span class="h-bar"></span></div>'
      : '<div class="h-bars yang"><span class="h-bar"></span></div>';
    const tags = (ln.tags || []).map((t) => {
      let cls = "h-tag";
      if (t === "世") cls += " shi";
      else if (t === "應") cls += " ying";
      else if (/動|破|暗動|空/.test(t)) cls += " warn";
      else if (/進|回頭生|臨月建|臨日建/.test(t)) cls += " good";
      return `<span class="${cls}">${esc(t)}</span>`;
    }).join("");
    let change = "";
    if (ln.is_moving && ln.change_zhi) {
      change = `<div class="h-change">動化 → <b>${esc(ln.change_gan)}${esc(ln.change_zhi)}</b>`
             + `（${esc(ln.change_qin)}）${ln.jin_tui ? "　" + esc(ln.jin_tui) : ""}</div>`;
    }
    return `<div class="hline ${ln.is_moving ? "is-moving" : ""}"
        style="animation-delay:${(5 - i) * 55}ms">
      <div class="h-meta"><span class="h-shen">${esc(ln.shen)}</span>
        <span class="h-qin">${esc(ln.qin)}</span></div>
      <div class="h-name">${esc(ln.yao_name)}<small>${esc(ln.gan)}${esc(ln.zhi)}${esc(ln.wx)}</small></div>
      ${bars}
      <div class="h-tags">${tags}</div>
      ${change}
    </div>`;
  }).join("");
}

function renderBoardPane(board) {
  const ct = board.cast_time;
  const gtags = [];
  if (board.is_liuhe_gua) gtags.push(["六合卦", "tag-jade"]);
  if (board.is_liuchong_gua) gtags.push(["六沖卦", ""]);
  if (board.changed_is_liuhe) gtags.push(["變卦六合", "tag-jade"]);
  if (board.fu_yin) gtags.push(["伏吟", "tag-gold"]);
  if (board.fan_yin) gtags.push(["反吟", "tag-gold"]);
  if (board.gua_bian && board.gua_bian !== "變卦未明") gtags.push([board.gua_bian, "tag-gold"]);

  const ci = [];
  if (board.gua_ci) {
    ci.push(`<div class="b-ci-item"><div class="b-ci-label">主卦 ${esc(board.hexagram)}</div>
      <div class="b-ci-text">${esc(board.gua_ci)}</div></div>`);
  }
  for (const pos of board.moving_positions || []) {
    const ln = board.lines.find((l) => l.pos === pos);
    const text = (board.yao_ci || {})[ln?.yao_name];
    if (text) {
      ci.push(`<div class="b-ci-item"><div class="b-ci-label">動爻 ${esc(ln.yao_name)}</div>
        <div class="b-ci-text">${esc(text)}</div></div>`);
    }
  }
  if (board.changed_hexagram && board.changed_gua_ci) {
    ci.push(`<div class="b-ci-item"><div class="b-ci-label">變卦 ${esc(board.changed_hexagram)}</div>
      <div class="b-ci-text">${esc(board.changed_gua_ci)}</div></div>`);
  }

  const ys = board.yongshen_qin
    ? `${board.yongshen_qin}（${board.yongshen_lines.map((l) => l.yao_name + "·" + l.gan + l.zhi).join("、")}）`
    : "未取";

  return `<div class="board-content">
    <div class="b-head">
      <div class="b-guas">
        <span class="b-gua">${esc(board.hexagram)}</span>
        ${board.changed_hexagram ? `<span class="b-arrow">→</span>
          <span class="b-gua b-gua-changed">${esc(board.changed_hexagram)}</span>` : ""}
      </div>
      <div class="b-sub">${esc(ct.year_gz)}年　${esc(ct.month_gz)}月　${esc(ct.day_gz)}日　${esc(ct.shichen)}時</div>
      <div class="b-sub">${esc(ct.lunar_text || "")}　旬空 ${esc((board.xunkong || []).join("、"))}</div>
      ${gtags.length ? `<div class="b-tags">${gtags.map(([t, c]) =>
        `<span class="tag ${c}">${esc(t)}</span>`).join("")}</div>` : ""}
    </div>
    <div class="hex">${renderLines(board)}</div>
    <div class="b-params">
      <div class="b-param"><div class="b-param-k">月建</div>
        <div class="b-param-v">${esc(board.month_zhi)}<small> · ${esc(board.month_wx)}</small></div></div>
      <div class="b-param"><div class="b-param-k">日辰</div>
        <div class="b-param-v">${esc(board.day_gz)}<small> · ${esc(board.day_wx)}</small></div></div>
      <div class="b-param"><div class="b-param-k">旬空</div>
        <div class="b-param-v">${esc((board.xunkong || []).join("、"))}</div></div>
      <div class="b-param"><div class="b-param-k">用神</div>
        <div class="b-param-v accent">${esc(ys)}</div></div>
      <div class="b-param"><div class="b-param-k">世／應</div>
        <div class="b-param-v">${board.world_pos} / ${board.response_pos}</div></div>
      <div class="b-param"><div class="b-param-k">動爻</div>
        <div class="b-param-v accent">${esc(board.moving_text || "無")}</div></div>
    </div>
    ${ci.length ? `<div class="b-ci"><div class="b-ci-title">卦　爻　辭</div>${ci.join("")}</div>` : ""}
    <details class="b-fold" open><summary>技術明細</summary>
      <div class="b-tech">
        <div class="b-tech-row"><span class="b-tech-k">宮位</span>
          <span class="b-tech-v">${esc(board.palace)}宮 · ${esc(board.palace_wx)}</span></div>
        <div class="b-tech-row"><span class="b-tech-k">世應</span>
          <span class="b-tech-v">世 ${board.world_pos} 爻　應 ${board.response_pos} 爻</span></div>
        <div class="b-tech-row"><span class="b-tech-k">動爻</span>
          <span class="b-tech-v">${esc(board.moving_text || "無")}</span></div>
        <div class="b-tech-row"><span class="b-tech-k">三合</span>
          <span class="b-tech-v">${board.sanhe && Object.keys(board.sanhe).length
            ? Object.entries(board.sanhe).map(([k, v]) => esc(k) + "：" + esc(v.status)).join("<br>")
            : "無"}</span></div>
        <div class="b-tech-row"><span class="b-tech-k">卦變</span>
          <span class="b-tech-v">${esc(board.gua_bian || "—")}</span></div>
      </div>
    </details>
  </div>`;
}

function renderIntake() {
  return `<section class="intake">
    <div class="intake-inner">
      <div class="intake-mark">${["☰","☱","☲","☳","☴","☵","☶","☷"]
        .map((s) => `<span>${s}</span>`).join("")}</div>
      <h2 class="intake-title">所問何事？</h2>
      <p class="intake-sub">心中默念所問，再起卦。卦由時定，月建日辰皆依此刻推算。</p>
      <form class="intake-form">
        <label class="field">
          <span class="field-label">占問</span>
          <textarea rows="3" placeholder="例：這次面試能否錄取？　例：與他這段感情是否值得走下去？"></textarea>
          <span class="field-hint">0 / 400</span>
        </label>
        <div class="intake-row">
          <label class="field field-sm">
            <span class="field-label">起卦方式</span>
            <div class="seg">
              <button type="button" class="seg-btn is-on">擲錢起卦</button>
              <button type="button" class="seg-btn">手動指定</button>
            </div>
          </label>
          <label class="field field-sm">
            <span class="field-label">用神</span>
            <select><option>自動推斷</option><option>父母</option><option>兄弟</option>
              <option>子孫</option><option>妻財</option><option>官鬼</option></select>
          </label>
          <label class="field field-sm">
            <span class="field-label">占卦時間</span>
            <input type="datetime-local" value="2026-11-22T12:30">
          </label>
        </div>
        <button class="btn-primary" type="button">
          <span class="btn-primary-inner">起　卦</span></button>
      </form>
    </div>
  </section>`;
}

function renderThread(board, answer) {
  const ct = board.cast_time;
  return `<section class="thread">
    <div class="msg msg-q">
      <div class="bubble">家人介紹的女緣，是否旺自己</div>
      <div class="stamp">${esc(ct.moment_display)}　${esc(ct.year_gz)}年 ${esc(ct.month_gz)}月 ${esc(ct.day_gz)}日</div>
    </div>
    <div class="msg msg-a">
      <div class="answer-head">
        <div class="answer-seal">斷</div>
        <div class="answer-meta"><b>解卦</b>　<span>DeepSeek · deepseek-chat</span></div>
      </div>
      <div class="answer-body">${answer}</div>
    </div>
  </section>
  <form class="composer">
    <input type="text" placeholder="針對此卦追問（例：那他什麼時候會表態？）">
    <button type="submit" class="btn-send">問</button>
  </form>`;
}

async function main() {
  // 取得真實排盤資料
  const res = await post("/api/cast", {
    question: "家人介紹的女緣，是否旺自己",
    hexagram: "地澤臨", moving: [2], yongshen: "妻財",
    when: { iso: "2026-07-16T06:30:00+00:00" },
  });
  if (!res.ok) throw new Error("排盤失敗：" + res.error);
  const board = res.board;

  // 示範用解卦內容（未呼叫付費 LLM；格式即真實輸出的樣式）
  const demoAnswer = `
<h2>一、總斷</h2>
<p>此緣本質相生，<strong>能旺你</strong>。然當下時機未至，屬「貴而暫弱」之局——人好、緣分重，
但能量尚未出來，宜守不宜急。</p>
<h2>二、用神</h2>
<p>取<strong>妻財</strong>為用神，因所問為女緣。用神妻財亥水臨五爻君位、臨應爻，正指此人。
亥水於未月處死地，受月建未土之剋、日辰卯木之泄，兩頭受壓，故旺不起來。</p>
<h2>三、世爻與自身</h2>
<p>世爻九二官鬼卯木動化庚寅，為<strong>化退神</strong>，主心氣漸退；又入月建未墓，困束施展不開；
更臨玄武，暗自動搖。</p>
<h2>四、全局分解</h2>
<p>上爻子孫酉金旺相逢日辰卯沖，為<strong>暗動</strong>而非日破——暗中生助亥水，是隱性的托底之力。
兄弟丑土兩重月破，克財阻力被削弱。</p>
<h2>五、應期</h2>
<p>亥子月財爻得令最旺，為最佳時間窗；丑月沖開未墓但你出困、財已轉弱，須防錯位。</p>
<h2>六、建議與提醒</h2>
<p>宜守不宜急。占卜斷勢象時機，非事實預測，重大決定仍須專業判斷。</p>`;

  const html = `<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>六爻 AI · 介面預覽</title>
<style>${CSS}
.preview-note{position:fixed;top:0;left:0;right:0;z-index:99;padding:8px 16px;
  font-family:var(--font-song);font-size:12px;letter-spacing:.12em;
  color:#fdf6e6;background:var(--seal);text-align:center}
.preview-note b{font-weight:600}
body{padding-top:34px}
</style>
</head>
<body>
<div class="preview-note">介面預覽（以真實排盤資料渲染，解卦文字為示範內容）· <b>http://127.0.0.1:8848/</b></div>
<div class="grain"></div>

<aside class="sidebar">
  <div class="brand">
    <div class="brand-seal">問</div>
    <div class="brand-text"><h1>六爻</h1><p>問卦・繁體</p></div>
  </div>
  <nav class="nav">
    <button class="nav-btn"><span class="nav-ico">＋</span><span>新的占問</span></button>
    <button class="nav-btn"><span class="nav-ico">⚙</span><span>設定</span></button>
  </nav>
  <div class="history-wrap">
    <h2 class="side-title">占問紀錄</h2>
    <ul class="history">
      <li><button class="history-btn is-on">家人介紹的女緣，是否旺自己
        <small>地澤臨→地雷復　剛剛</small></button></li>
    </ul>
  </div>
  <footer class="side-foot"><p>斷勢・象・時機</p><p>非事實預測</p></footer>
</aside>

<main class="stage">
  <header class="stage-head">
    <div class="stage-head-left"><span class="stage-kicker">六爻占卜</span></div>
    <div class="stage-head-right"><span class="llm-state is-warn">未設定 API 金鑰</span></div>
  </header>
  ${renderThread(board, demoAnswer)}
</main>

<aside class="board-pane">${renderBoardPane(board)}</aside>
</body>
</html>`;

  fs.writeFileSync(OUT, html, "utf8");
  console.log("已產生預覽：", OUT);
  console.log("卦盤：", board.hexagram, "→", board.changed_hexagram,
              "／", board.cast_time.month_gz, board.cast_time.day_gz);
}

main().catch((e) => {
  console.error("產生預覽失敗：", e.message);
  process.exit(1);
});
