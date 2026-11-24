# 六爻占卜 · Liuyao Divination

> 面向 AI Agent 的**六爻占卜技能** + **可程式化排盤工具包**。既能把卦排準，又能用一套完整、自洽的斷卦方法去解讀它。
>
> 📖 **English: see [README.en.md](./README.en.md)**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Skill](https://img.shields.io/badge/Claude-Skill-7c3aed.svg)](./skill/liuyao-divination/SKILL.md)

---

## ✨ 這是什麼

六爻（六爻卦）是以《易經》六十四卦為基礎的傳統占卜體系。一卦排定後，給六爻配上納甲（天干地支）、六親、六神、世應，再結合占卦的**月建、日辰**，透過旺衰、空亡、破、暗動、化進化退、三合六合、墓庫等技法來判斷吉凶。

本專案提供**兩樣東西**：

1. **`SKILL.md` 智慧代理技能**：教 LLM（如 Claude Code）按訓練有素的斷卦流程讀卦——取用神、斷旺衰、辨暗動與日破、分清"貴"與"旺"等等。
2. **Python 排盤引擎 + 報告生成器**：把最容易出錯、最機械的部分（納甲、六親、空亡、暗動、化退……）交給程式確定性計算，再渲染一份古典卷宗風格的 HTML 報告。

## 🧭 為什麼做這個

手工排盤是大多數卦斷錯的根源——宮位排錯、漏判暗動、把墓庫當破……引擎負責把卦**排準**，技能負責**需要推理的判斷**。兩者配合，讓"機械部分"誠實可靠，"解讀部分"才有紮實的根基。

## 📦 專案結構

```
liuyao-divination/
├── skill/liuyao-divination/SKILL.md   # 智慧代理技能（從這裡開始）
├── references/                        # 12 冊技法參考文件
│   ├── 01-裝卦排盤.md                  #   裝卦、納甲、六親、世應、六神
│   ├── 02-用神取用.md                  #   取用神
│   ├── 03-旺衰月日.md                  #   月建日辰定旺衰
│   ├── 04-動靜暗破.md                  #   動靜、暗動、月破、日破、空亡
│   ├── 05-進退神化.md                  #   化進化退、變爻
│   ├── 06-三合六合.md                  #   三合局、六合
│   ├── 07-墓庫論.md                    #   入墓、庫墓、空墓、出墓
│   ├── 08-斷卦步驟.md                  #   完整斷卦流程
│   ├── 09-四神與有力無力.md            #   用神元神忌神仇神、有力無力
│   ├── 10-卦變反伏.md                  #   卦變生克墓絕、反吟、伏吟
│   ├── 12-應期與應驗.md                #   應期多通道交叉、應驗分層、驗卦覆盤
│   └── 13-象意解讀.md                  #   全要素象意：七層象源的同象異讀語法
├── src/
│   ├── liuyao/                        # 排盤引擎（可 import 的包）
│   └── paipan.py                      # CLI：排盤並列印
├── tools/
│   └── generate_report.py             # HTML 報告生成器
├── examples/                          # 已驗證的卦例庫（JSON）
├── tests/                             # 黃金用例測試（經典卦例）
├── data/zhouyi.json                   # 64 卦辭 + 385 爻辭（公有領域原文）
└── docs/reports/                      # 範例斷卦報告（HTML）
```

## 🚀 快速開始

### 1. 排盤（命令列）

```bash
python src/paipan.py --hexagram 地澤臨 --moving 2 --month 未 --day 卯
```

列印完整卦盤：六親、納甲、六神、世應、空亡、月破日破、暗動標記、化進化退、墓庫狀態——全部結合月建日辰判定。

### 2. 生成 HTML 報告

```bash
python tools/generate_report.py examples/01-是否旺己-地澤臨之復.json -o outputs/report.html
```

### 3. 作為 Claude Code 技能使用

```bash
# 軟連結（或複製）到你的技能目錄
ln -s "$(pwd)/skill/liuyao-divination" ~/.claude/skills/liuyao-divination
```

然後對 Claude 說："占問家人介紹的對象是否旺自己，主卦地澤臨九二動變復，辛卯日"，它就會按技能流程解讀。

### 4. 分析一個新卦（完整流程）

機械層交給程式、推理層交給 LLM，三步走：

```bash
# ① 鷹架：排盤 + 取卦辭爻辭 + 生成 JSON 骨架 + 列印推理 brief
python tools/new_case.py --hexagram 雷水解 --moving 3 --month 申 --day 甲子 \
    --question "占求職能否成" --yongshen 官鬼 -o examples/02-求職.json

# ② LLM 推理：把 brief 交給 Claude，依 SKILL.md 八步流程填充 JSON 的
#    overview 講解 / sections 分層解析 / verdict 斷語 / summary
#    （卦象推理、六爻分析、發展推演——充分發揮大模型能力）

# ③ 生成報告
python tools/generate_report.py examples/02-求職.json -o outputs/report.html
```

排盤、卦辭、關鍵判定（暗動 / 化退 / 入墓 / 三合 / 六合卦 / 元忌有力無力…）由鷹架自動算準；推理與斷卦由 LLM 發揮。詳見 `references/08-斷卦步驟.md`。

## 🧪 正確性

引擎用一個**手工精析的經典卦例**（`examples/01-是否旺己-地澤臨之復.json`，地澤臨 → 地雷復，辛卯日）來驗證。測試斷言引擎能復現每一條手工結論：妻財亥水為用神在五爻、子孫酉為**暗動**（而非日破——關鍵區別）、世爻丁卯入未墓且化退為庚寅、空亡在午未而卦中無落空之爻，等等。

```bash
python -m pytest tests/
```

## 📚 方法論

本專案採用主流綜合派（沿《增刪卜易》一脈），並**明確標出易被忽略的精細處**：

- **暗動 vs 日破**：靜爻被日辰沖，**旺相**者為暗動（激發起用），**休囚**者為日破（沖散無用）。同樣的"沖"，結論相反。
- **貴 ≠ 旺**：爻臨五爻君位是"貴"（地位尊顯），不等於"旺"（力量強旺）——旺衰仍看月日。
- **墓庫細節**：入"空墓"（墓庫落空亡）意味著困束是虛的、易脫的，不是死局。
- **進退神**：卯化寅為退神，寅化卯為進神。

詳見 [`references/`](./references) 各冊與 [`SKILL.md`](./skill/liuyao-divination/SKILL.md)。

## 🤝 貢獻

歡迎對排盤邏輯或技法文件提出修正——**準確性是本專案的全部意義**。涉及實質性的方法論變更（不同流派會有分歧），請先開 issue 討論，再慎重取捨。

## ⚠️ 理性宣告

六爻是**傳統文化與占卜術**，不是科學。本專案是一項工程與文化儲存的努力。卦象描述的是"勢、象、時機"，**不是事實預測**，絕不能替代現實中對感情、財務、健康及任何決策的理性判斷。請理性參考、負責任地使用。

## 📄 許可證

[MIT](./LICENSE) © 2026 Johnson
