# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Engine（三合局補全：內卦／外卦三合局）**: 限**初+三爻**或**四+上爻皆明動**，取兩動爻的「原支＋變支」共四支，任三支成局且**動支、變支並見**，方論內／外卦三合局；二、五爻動不成局，靜爻（含暗動）不能頂替明動。缺支由變爻補出者，原「虛合待填實」升為**實成之局**（新增 `Board.sanhe_local`）。
- **Engine（暗動）**: 暗動收斂為三條件——**靜爻／日辰六沖／旺相**；並新增「靜爻不旺但**得明動之爻生助**，逢日沖亦作暗動」一途（`Line.dark_move_reason`、`dark_move_via`）。動爻被日沖只論「動而愈動／沖散」，不再誤判暗動。
- **Reference docs**: `references/12-應期與應驗.md` — 應期多通道交叉定位與置信度分級、化出之支三重身份（"退而得合"辨析）、應驗分層核對、驗卦覆盤循環（事前斷語/事後補釋證據分級）。`references/13-象意解讀.md` — **全要素象意體系**：七層象源（五行五性、關係、狀態、爻位、天時、卦象、六神）一套語法「**象核 × 域 × 角色**」同象異讀；象核×域速查表、旺相休囚死的處境象、十二長生的生命週期象、間爻=中間人象、月建日辰天時象、多象同向與層間互校、同盤異占遷移示範。均以驗證卦例（地澤臨之復）匿名貫穿。
- **Skill**: `SKILL.md` 新增關鍵辨析 #11（象意三要素·同象異讀）、#12（應期多通道交叉與應驗分層）及速查條目；辨析 #7 補"破而待填／入局從化"兩訣；Deep References 同步。
- **References（三合進階技法，源自驗證卦例辯證）**：`06-三合六合` 新增「局之進階」節——**破而待填 vs 虛一待用**兩虛之辨（局中支月破≠局缺支）、**拱而不出**（待用期間所拱之字不作生克）、成局另兩路徑（靜爻臨值力同發動、月日與動爻會局）、**入局從化**（收編效應："從局不從性"，原支沖剋隨化而收）、**失令局生**（備用管道接棒）；`12` 應期通道表新增「破待填→局成」；`13` 三合行補「從局不從性」。
- **Report generator**: 報告佈局從「占時快照」升級為「斷→驗→續生命週期檔案」——新增可選節 **肆·應驗紀實**（事實時間線 + 逐象對應表 + 證據分級徽章：事前斷語·已驗/事後對帳/回溯吻合）與 **伍·應期追蹤**（時間窗/卦理預期/狀態徽章：待驗/警示），編號動態順延；舊案例 JSON 無新欄位則不渲染（完全向後相容）。
- README（中/英）結構樹同步更新。

### Changed
- **Deploy（Hobby Function 上限）**: 移除 `api/` 的 13 個 wrapper，改由根目錄 `app.py` 匯出 `ai/wsgi.py` 的 Flask app；Vercel Flask preset 只建立 **1 個 Function**，符合 Hobby 12 個上限。`vercel.json` 的 `functions` 改指向 `app.py`，並刪除 Stripe 的 5 條 rewrites（Flask 已直接提供 `/api/stripe/*` 路由）。`_check_vercel.py` 改測 Flask app、`/api/health`、`/api/cast`、`/api/providers`、`/api/glossary`、`/api/settings` 與首頁。
- **Homepage / 品牌定位**: 首頁改以「執業卦師訓練的 AI 六爻解讀」為主軸，加入完整品牌說明、專業六爻解卦八步流程、可問範圍、六爻知識與 8 條 FAQ；文字明確區分「卦師參與建立知識庫、案例、規則與校驗」與「模型微調」，不夸大訓練方式。
- **SEO**: 首頁 Title 改為「六爻占卜｜執業卦師訓練的 AI 六爻解卦｜知幾」，重寫 description；新增 FAQPage 與 WebApplication JSON-LD、Open Graph／Twitter Card、`robots.txt`、`<noscript>` 摘要；補 `專業六爻占卜`、`專業六爻解卦`、`卦師六爻解卦`、`卦師 AI 占卜`、`卦師訓練的 AI 六爻`、`AI 六爻專業分析`、`真人卦師`、`傳統六爻理論` 等關鍵語。
- **首頁互動**: 品牌區的 h1 改為視覺相同的 div，讓頁面唯一 h1 落在內容區；起卦畫面新增「知幾是甚麼？」跳轉連結；進入問答後自動收起內容區，返回新占問時再顯示。
- **Web / 體積**: 銅錢圖由 240px PNG（106/110 KB）縮為 168px 並增設 WebP（8.3/8.0 KB），CSS 以 `image-set()` 優先載入 WebP、PNG 作後備；`sync_public.py` 同步 `*.txt`／`*.xml`。
- **Deploy**: `vercel.json` 指定 `hkg1` 區域（香港使用者與 DeepSeek API 延遲較低）、`/assets/*` 交由 CDN 快取（瀏覽器仍每次 revalidate）、`/api/*` 加 `X-Robots-Tag: noindex`；`.vercelignore` 補 `.npm-cache/`、`.agents/`、`.dsh-bundles/`、`docs/reports/`。
- **Cleanup**: 刪除 `ai/.tmp/` 內約 467 MB 的截圖測試用瀏覽器 profile（`cp-*`，已 gitignore）；工作區由 536 MB 降至約 69 MB。
- **Prompt（依占問裁剪段落）**: 不再強制填滿「總斷→用神→世爻→逐象→應期→建議」。新增占問分類（成敗／時間／描述／診斷）：**應期只在時間是問題的一部分時才寫**，猜物、問來意、問東西在哪這類描述型占問不排時間表；**建議只在能從卦理推導出行動或心態選擇時才給**，描述型占問不硬給，也不掛空泛提醒。總斷第二句的「具體卡點」改為有對立、競爭或阻礙時才寫；描述型改寫「所測的是什麼、憑哪個象」。標題可依問題改寫，無實質內容的段落整段省略。
- **Knowledge（SKILL.md）**: 新增「Output Shape — 依占問裁剪段落」對照表；第 8 步註明應期非必寫；用神速查補「猜物／問來意以應爻為主體」；常見錯誤新增「每卦都硬排應期、硬給建議」。`references/02` 補描述型占問取象說明，`references/08` 輸出規範同步。
- **Knowledge（context 去重）**: `_extract_skill_core()` 第一段改為在 `## Critical Distinctions` 前截斷，修掉「關鍵辨析」在知識庫上下文中重複出現一次的問題，單次 prompt 少約五千字。

### Fixed
- **Engine（旺衰）**: `is_prosperous()` 移除「十二長生進氣（長生／冠帶／臨官／帝旺）」一條——旺衰只看月令旺相休囚死與月日生扶比和。副作用：靜爻逢日沖不再因「自坐帝旺」誤判旺相，**日破得以真正出現**（例：子水卯月午日無動爻生助 → 日破；五爻申金明動生之 → 暗動）。
- **Docs**: `references/04-動靜暗破.md` 暗動三條件、日破定義、判定流程、速查表；`references/06-三合六合.md` 新增內／外卦三合局節；`references/03-旺衰月日.md` §三註明十二長生不參旺衰；`SKILL.md` 第 2／4／6 步、辨析 #1／#7、常見錯誤表同步。
- **Tests**: 新增 6 項（內卦三合局、外卦三合局、位置不合不成局、得動爻生助暗動、無助日破、動爻被沖不判暗動），共 35 項。
- **Engine**: `wuxing_state()` 相/休 判定反轉 — 舊版"生令者相、令生者休"，與《增刪卜易》及本專案 `references/03` 表格、案例斷言相反；現為 **當令所生者相、生令者休**（例：未月土令，金相、火休）。案例 01 中子孫酉金旺衰由"休"正為"相"，元神有力理由由"發動有力"精化為"旺相有力"；暗動等其餘判定不受影響（`is_prosperous` 多通道兜底）。
- **Docs**: `references/03-旺衰月日.md`、`SKILL.md` 旺相休囚死速查文字表述同步修正，與表格一致。
- **Tests**: 新增五行五態全表引數化測試 + 案例 01 迴歸斷言（未月酉金=相、巳火=休、暗動不變），共 29 項。

### Removed
- **六十四卦長文獻**：移除 `docs/易經六十四卦.md`（402 KB 完整源稿）與 `references/11-六十四卦判辭.md` —— 該冊在知識庫權重最低（1.0），每次只取前 4 冊，原本就從未進入 prompt；連帶移除只被母稿引用的 `docs/images/guaxiang/` 64 張卦象圖（39.1 MB）與 `docs/images/` 下的收款 QR code。`data/zhouyi.json`（64 卦辭 + 385 爻辭）保留，排盤、卦盤輸出與 prompt 皆不受影響。
- **Tools**：移除 `tools/extract_panji.py`（唯一產物即上述判辭檔）。
- **References 索引**：`references/` 由 13 冊降為 12 冊（保留 12、13 原編號，11 留空），`knowledge.py`、健康檢查與 README（中/英）、`ai/README.md`、`SKILL.md` 同步更新。
- **README**：移除「支援這個專案 / Support This Project」段落與支付寶、微信收款 QR code。

## [0.1.0] - 2026-07-16

### Added
- **Skill**: `skill/liuyao-divination/SKILL.md` — Claude Code / agent skill for Liu Yao (六爻) divination analysis, distilling a complete interpretive methodology.
- **Reference docs** (`references/`): 8 monographs covering 裝卦排盤 (casting & assigning), 用神取用 (selecting the Significant Line), 旺衰月日 (strength via month/day), 動靜暗破 (moving/dark-move/broken/void), 進退神化 (advancing/retreating transformation), 三合六合 (combinations), 墓庫論 (graveyard/storehouse theory), 斷卦步驟 (full interpretation workflow).
- **Python engine** (`src/liuyao/`): programmatic board-casting — 64 hexagrams, eight palaces & six relations (六親), nayin-stem assignment (納甲), six spirits (六神), void/empty (空亡), month/day break (月破/日破), dark-move (暗動), advancing/retreating spirit (化進/化退), twelve-stage graveyard (十二長生墓庫), world/response (世應).
- **CLI**: `src/paipan.py` — cast and print a board from hexagram + moving line + month + day.
- **Report generator**: `tools/generate_report.py` — render an ornate classical-style HTML report from a structured case JSON.
- **Examples**: `examples/01-是否旺己-地澤臨之復.json` — the canonical case (地澤臨 → 地雷復, 辛卯日) used to validate the engine end-to-end.
- Bilingual README (English + 簡體中文), MIT license.

[Unreleased]: https://github.com/Johnson/liuyao-divination/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Johnson/liuyao-divination/releases/tag/v0.1.0
