# 知幾筆記 · AI六爻解讀

以 [`liuyao-divination`](../README.md) 排盤引擎為基礎，加上 **LLM 解卦推理**、**聊天式網頁介面** 與 **節氣曆法精算** 的六爻占卜 AI。

> **設計哲學（沿用原專案）**
> 排盤與旺衰判定這類「機械層」交給程式確定性計算，**不讓模型猜**；
> 「解讀層」才交給 LLM，並以本專案的 12 冊技法文獻為依據。
> 兩者分工，才可能既排得準、又解得有據。

---

## 一分鐘上手

```bat
:: Windows：雙擊即可
ai\start.bat
```

```bash
# macOS / Linux
bash ai/start.sh
```

瀏覽器會自動開啟 <http://127.0.0.1:8848/>。

首次使用請點左下角 **設定** 選擇供應商（DeepSeek／OpenAI／Claude／Gemini／OpenRouter／Kimi／自訂端點），
填入 API 金鑰後儲存。金鑰只寫在本機 `ai/config/llm.json`，不會上傳。

介面刻意留白：首屏只有一個起卦表單與下方輸入框；卦盤與解讀都收在對話裡。表單下方另有一段可捲動的品牌說明、六爻知識與 FAQ（給搜尋引擎與第一次到訪的人看），進入問答後會自動收起。這段的文案在 `ai/web/index.html` 的 `<section class="seo" id="about">`。
左側是**占問紀錄**，點一下就能回到舊卦，每筆右側的垃圾桶圖示可單筆刪除。
盤面只留卦名（含變卦）、四值、六親、六神、納甲與六爻卦象；世應在卦爻右側另開直行標示，動爻以顏色標示。其餘術語與細節交給解讀文字，不再擠在盤面上。
起卦方式在**對話框左側的 dropdown**；用神、占卦時間與 API 金鑰在左下角**設定**面板。
設定中的「解讀詳略」可選**詳細**或**精簡**；**預設精簡**，用「旺相」「休囚」概括旺衰，適合快速閱讀；詳細版保留六段與精確旺衰。

### 起卦方式

- **報數（預設）**：心中默念後，在六條底線上依序填入六個數字，第 1 數初爻、第 6 數上爻。
- **銅錢**：畫面顯示三枚銅錢，點一下搖一爻；連搖六次，自下而上成卦。字＝正、背＝反，三背老陽、三字老陰。

首頁的起卦表單會要求選**性別**；感情題會依性別取用神，男占女以妻財、女占男以官鬼。

銅錢對照：

| 結果 | 判定 |
|---|---|
| 一背二字 | 少陽 |
| 二背一字 | 少陰 |
| 三背 | 老陽（動） |
| 三字 | 老陰（動） |

報數對照：

| 數字 | 判定 |
|---|---|
| 1 | 陽動 |
| 2、3、5 | 陰 |
| 4、6、7 | 陽 |
| 8、0 | 陰動 |

大於 8 的數字先除以 8 取餘數；餘 0 視為 8。六個數字一律自下而上排列。

---

## 部署到 Vercel

本機仍用 `ai/server.py` 的標準庫伺服器；雲端由 `api/*.py` 的 Python functions 提供 API，前端靜態檔放在 `public/`。

1. 把 GitHub repo 連到 Vercel，Framework Preset 選 **Other**，Root Directory 保持專案根目錄。
2. 在 **Settings → Environment Variables** 設定：
   - `DEEPSEEK_API_KEY`：你的 API 金鑰（必填）
   - `LIUYAO_LLM_PROVIDER`：`deepseek`（預設）
   - `LIUYAO_LLM_MODEL`：`deepseek-chat`（預設）
   - 若要收款：`STRIPE_SECRET_KEY`、`STRIPE_PRICE_SINGLE`、`STRIPE_PRICE_MONTHLY`、`STRIPE_WEBHOOK_SECRET`，以及指向正式網域的 `PUBLIC_BASE_URL`
3. 重新部署。`public/` 會成為靜態網站，`api/` 下每個檔案自動成為 `/api/<檔名>`；依賴在 `requirements.txt`，`vercel.json` 會把知識庫與排盤引擎一起打包，並給 SSE 60 秒。

每次改前端（`ai/web`）後，執行 `python ai/tools/sync_public.py` 更新 `public/`，再提交。

雲端檔案系統唯讀，所以設定面板的「儲存」會回傳 403；金鑰與模型請用上面的環境變數。`/api/read` 是 SSE 串流，Vercel 已支援 WSGI streaming。

---

## 方案與付款（Stripe）

目前提供兩個測試方案，從 `/pricing.html` 進入：

| 方案 | 價格 | 內容 |
|---|---|---|
| 單次解讀 | HK$28 | 一次完整 AI 六爻解讀 |
| 月訂 | HK$98 / 月 | 每月 30 次解讀，Customer Portal 可取消 |

本機設定：

1. 根目錄 `.env` 填入 `STRIPE_SECRET_KEY`、`STRIPE_PRICE_SINGLE`、`STRIPE_PRICE_MONTHLY`；`.env` 已被 git 忽略。
2. 啟動 `python ai/server.py`，開 <http://127.0.0.1:8848/pricing.html>。
3. 測試卡號 `4242 4242 4242 4242`，任意未來到期日、任意 CVC。
4. 付款完成頁是 `/billing-success.html`，會用 Checkout Session 向 Stripe 確認結果。

端點：`POST /api/stripe/checkout`、`POST /api/stripe/portal`、`GET /api/stripe/session`、`POST /api/stripe/webhook`。
Webhook 需要 `STRIPE_WEBHOOK_SECRET`；本機可用 Stripe CLI：

```bash
stripe listen --forward-to localhost:8848/api/stripe/webhook
```

把 CLI 顯示的 `whsec_...` 填入 `.env`。目前沒有登入，Customer Portal 的 customer ID 存在瀏覽器 localStorage；正式上線應改成登入帳號＋Postgres，並以 webhook 的 subscription 狀態作為 entitlement 來源。SQLite 只適合本機，Vercel 的唯讀檔案系統不能寫入。

稅務：目前**沒有啟用 Stripe Tax**（先不代收稅）。若日後要對台灣／香港或海外客戶代收稅，需先設定稅務註冊、product tax code 與 price tax behavior，再開 `automatic_tax`。

---

## 這個 AI 會做什麼

起一卦，它會依《增刪卜易》一脈的**八步斷卦流程**推理，輸出成以下結構：

| 步驟 | 內容 |
|---|---|
| 一、總斷 | 先給明確方向（成／不成、吉／凶／吉中有阻），交代當下情勢，點出最關鍵的象；描述型占問不勉強給成敗，也不硬套「卡點」 |
| 二、用神 | 取哪個用神、為什麼、在問題中代表什麼、落第幾爻、旺衰與有根無根；描述型可改寫成「所測之物」 |
| 三、世爻與自身 | 先白話說問卦者當下的處境，再論世爻旺衰、空破、動變；與問題無關時可省略 |
| 四、逐象詳解 | 只挑真正影響判斷的象，逐項說明「代表什麼、卦中狀態、如何影響結論」；未成局與未出現的象不寫 |
| 五、應期 | **只有時間是問題的一部分時才寫**，多通道交叉定位時間窗；猜物、問來意這類沒有時間軸的占問不寫 |
| 六、建議與提醒 | **只有能從卦理推導出行動或心態選擇時才寫**；描述型占問不給建議，也不用空話補位 |

段落是為問題服務的，不是每卦都要填滿。成敗型（求職、感情、買賣、考試）用完整結構；
時間型把應期提前當主線；描述型（猜物、問來意、問東西在哪、問對方特徵）把五行、六神、
爻位、卦象翻成具體特徵，不寫應期也不給建議；診斷型指出性質、位置與調理方向。
某段在這個問題上沒有實質內容，就整段省略，標題也可以改得貼題。

輸出不按八步逐段排列，而是依「對結論的影響力」重新組織。三合只論**實成之局**；
虛合、缺支、沒有出現的象，不會被硬寫進來湊數。關鍵斷語用**粗體**標示（介面顯示朱色），
次要重點用*斜體*標示（金色），不必為了顏色而滿篇標記。
行文不用破折號，冒號也盡量少用。旺衰（旺相休囚死）與十二長生分開說明。
地支作用只認六沖與六合，沒有固定關係的兩支不會被硬串在一起（例如丑與辰不沖，
辰空看戌）。

### 排盤是怎麼算準的

| 要素 | 做法 |
|---|---|
| **月建** | 依**節氣**（非農曆月、非公曆月）精算。太陽視黃經用 Meeus 天文演算法求解，誤差約 1 分鐘級 |
| **日辰** | 以「1949-10-01 甲子日」為錨點推算六十甲子日，經多個獨立黃曆交叉驗證 |
| **年干支** | 依**立春**換年（六爻傳統，非正月初一） |
| **旬空** | 由日干支查旬空表 |
| **納甲、六親、六神、世應** | 原引擎計算，已驗證 |
| **飛神伏神** | 本宮首卦補缺六親、飛伏五行、出伏判斷 |
| **旺衰、月破、日破、暗動、化進退、入墓、三合六合、卦變** | 原引擎計算，已驗證 |

農曆日期亦以天文朔日（Meeus 第 49 章）推算，僅供顯示參考，不參與排盤。

### 起卦方式

- **報數**（預設）：六個數字由下而上，依表轉成少陽／少陰／老陽／老陰。
- **銅錢**：畫面三枚銅錢，點一下搖一爻，連搖六次；三背老陽、三字老陰。

首頁表單的**性別必填**；感情題男占女取妻財、女占男取官鬼。用神仍可自動推斷或指定。

---

## 專案結構

```
liuyao-divination/
├── ai/                          ← 本 AI 應用（新增）
│   ├── server.py                後端：純標準庫 HTTP 伺服器 + SSE 串流
│   ├── start.bat / start.sh     啟動腳本
│   ├── .env.example             環境變數範例
│   ├── liuyao_ai/
│   │   ├── calendar.py          節氣／干支／農曆精算（純天文演算法，無依賴）
│   │   ├── divination.py        起卦、卦盤序列化、用神推斷
│   │   ├── knowledge.py         12 冊技法文獻索引與動態擷取
│   │   ├── llm.py               多供應商 LLM 抽象層（串流）
│   │   └── prompt.py            系統提示與八步輸出規範
│   ├── web/                     前端（原生 JS，無框架、無建置步驟）
│   │   ├── index.html
│   │   └── assets/{app.css, app.js}
│   ├── config/llm.json          LLM 設定（含金鑰，已 gitignore）
│   └── _check_*.py              驗證腳本（曆法／起卦／API／串流）
├── src/liuyao/                  原排盤引擎（已繁體化）
├── references/                  12 冊技法文獻（已繁體化）
├── skill/liuyao-divination/     Agent 技能定義（已繁體化）
├── data/                        64 卦辭爻辭、術語表
└── tools/localize_zh_tw.py      繁簡轉換工具（可重複執行）
```

---

## 運作原理

```
使用者輸入占問
      │
      ▼
┌─────────────────┐
│ calendar.py     │  節氣精算 → 月建、日辰、旬空、年干支
└────────┬────────┘
         ▼
┌─────────────────┐
│ divination.py   │  擲錢／指定 → 卦名、動爻、變卦
└────────┬────────┘
         ▼
┌─────────────────┐
│ src/liuyao      │  排盤引擎：納甲、六親、六神、世應、旺衰、暗動、化進退、入墓、飛神伏神…
└────────┬────────┘   ← 這一層的結果是「唯一事實」，LLM 不得改算
         ▼
┌─────────────────┐
│ knowledge.py    │  依卦盤出現的象（暗動／月破／三合／入墓…）動態挑選相關技法冊
└────────┬────────┘
         ▼
┌─────────────────┐
│ prompt.py       │  方法論 + 相關技法 + 卦盤 → 系統提示
└────────┬────────┘
         ▼
┌─────────────────┐
│ llm.py          │  串流呼叫（SSE）→ 前端逐字顯示
└─────────────────┘
```

**知識庫動態擷取**：不是把 90KB 文獻全塞進 prompt，而是依卦盤實際出現的象
（如「上爻暗動」「二爻化退神」「兄弟月破」）挑選對應冊別，並保證「用神取用」與
「動靜暗破」兩冊永遠入選。單次 prompt 約 1.4 萬字。

**一卦只起一次**：`/api/cast` 擲錢排出卦盤後，前端把「整份卦盤」隨解讀請求送回，
`/api/read` 與 `/api/preview` 一律沿用該卦盤、不再擲錢；後端並檢查
卦名 ↔ 六爻 ↔ 動爻標記三者一致，殘缺或矛盾的卦盤直接回 400。
這確保「畫面上顯示的卦」與「LLM 解讀的卦」永遠是同一個卦
（曾因 `/api/read` 重擲銅錢而出現兩卦不一致的 bug，現由 `_check_board_lock.py` 鎖住）。

---

## 驗證結果

所有驗證腳本都可重跑：

```bash
# 排盤引擎原有測試
python -m pytest tests/ -q                     # 29 passed

# 一鍵跑完 AI 層全部驗證（需先啟動 server.py）
python ai/tests/run_all.py

# 或分項執行
python ai/tests/_check_calendar.py             # 曆法精算（55+ 項）
python ai/tests/_check_divination.py           # 起卦與卦盤
python ai/tests/_check_api.py                  # API 端到端（需伺服器）
python ai/tests/_check_board_lock.py           # 一卦只起一次（需伺服器）
python ai/tests/_check_stream.py               # SSE 串流（需伺服器 + 假 LLM）
node ai/tests/_check_render.js                 # 前端渲染
```

已驗證的關鍵結論（與 repo 手工斷卦對照）：

- 地澤臨之復、未月辛卯日：上爻子孫酉金**暗動**（旺相逢沖）而非日破 ✓
- 二爻官鬼卯木**化退神**、入**月墓**且為**空墓**、臨玄武 ✓
- 兄弟丑土兩重**月破**、世在二爻應在五爻 ✓
- 用神妻財亥水臨應爻，旬空午未而卦中無落空之爻 ✓

曆法對照：`2026-08-01 = 丙午年 乙未月 丁未日`、`2026-07-16 = 乙未月 辛卯日（旬空午未）`、
`2024-02-10 = 正月初一`、`2025-01-29 = 乙巳年正月初一`，均與公開黃曆一致。

---

## 設定

### 支援的供應商

| 供應商 | 協定 | 預設模型 |
|---|---|---|
| DeepSeek | OpenAI 相容 | `deepseek-chat` |
| OpenAI | OpenAI | `gpt-4o` |
| Claude (Anthropic) | Anthropic Messages | `claude-sonnet-4-5` |
| Google Gemini | Gemini streamGenerateContent | `gemini-2.5-pro` |
| OpenRouter | OpenAI 相容 | `deepseek/deepseek-chat-v3.1` |
| Moonshot (Kimi) | OpenAI 相容 | `moonshot-v1-32k` |
| 自訂 | OpenAI 相容 | 任意 |

### 環境變數

除了介面設定，也可用環境變數（見 `ai/.env.example`）：

```bash
DEEPSEEK_API_KEY=sk-...
LIUYAO_LLM_PROVIDER=deepseek
LIUYAO_LLM_MODEL=deepseek-chat
LIUYAO_PORT=8848
```

優先序：`ai/config/llm.json` → 環境變數 → 內建預設。

---

## 為什麼不用 FastAPI

開發環境缺少可編譯的 `pydantic-core`（需 C 編譯器），而本專案要求**零編譯依賴、開箱即跑**，
故後端以 Python 標準庫 `http.server` 實作，SSE 串流以原生寫入達成。
本機後端唯一的第三方依賴是 `httpx`（用於呼叫 LLM API），且可沿用系統既有安裝。
雲端部署另由 `ai/wsgi.py` 的 Flask WSGI app 接手，依賴列在根目錄 `requirements.txt`。

---

## 常見問題

**Q：起卦後一直停在「解讀中…」**
A：通常是 API key 未設定或餘額不足。看左下角設定旁的狀態標籤，或開瀏覽器開發者工具看 `/api/read` 回應。

**Q：月建跟手機上的萬年曆不一樣**
A：本專案月建依**節氣**（立春起寅月），萬年曆有時顯示農曆月或八字月，定義不同。
若日期正好落在交節當日，差異屬正常——交節時刻前後屬不同月建。

**Q：可以改埠號嗎**
A：可以。`set LIUYAO_PORT=9000` 後再啟動，或改 `ai/start.bat`。

**Q：金鑰會不會外洩**
A：金鑰只存本機 `ai/config/llm.json`（已列入 `.gitignore`），僅在呼叫你選定的供應商時送出。
不會寫入日誌，也不會回傳給前端。

---

## 理性提醒

六爻為傳統文化與占卜術，非科學。它斷的是「勢、象、時機」，不是事實預測。
涉及健康、法律、重大財務與婚姻決定時，請尋求專業意見，不要只依賴占卜結果。

---

## 授權

沿用原專案 [MIT License](../LICENSE)。
