# Liuyao Divination · 六爻占卜

> An AI-agent skill + programmatic toolkit for **Liu Yao (六爻)** — traditional Chinese hexagram divination. It casts the board correctly and reasons about it with a complete, internally-consistent interpretive methodology.
>
> 📖 **中文版見 [README.md](./README.md)**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Skill](https://img.shields.io/badge/Claude-Skill-7c3aed.svg)](./skill/liuyao-divination/SKILL.md)

---

## ✨ What this is

Liu Yao (六爻 / "Six Lines") is a traditional Chinese divination system built on the 64 hexagrams of the *I Ching*. A reading assigns each of the six lines a stem-branch (納甲), a "six-relation" (六親), a spirit (六神), a world/response position (世應), and then judges fortune by analyzing strength (旺衰), void (空亡), breaks (破), dark-movement (暗動), transformations (化進/化退), combinations (三合/六合), and graveyards (墓庫) against the month and day of casting.

This project gives you **two things**:

1. **A `SKILL.md` agent skill** — teaches an LLM agent (Claude Code, etc.) the full interpretive workflow so it can read a board the way a trained practitioner does: select the Significant Line, weigh strength, distinguish dark-move from day-break, tell "noble" (貴) apart from "strong" (旺), and so on.
2. **A Python casting engine + report generator** — removes the mechanical error-prone part (納甲, 六親, 空亡, 暗動, 化退…) by computing the board deterministically, then renders an ornate classical-style HTML report.

## 🧭 Why

Manual casting is where most readings go wrong — a mis-assigned palace, a missed dark-move, a graveyard mistaken for a break. The engine computes the board; the skill handles the judgment that requires actual reasoning. Together they keep the *mechanics* honest so the *interpretation* has solid ground.

## 📦 Repository structure

```
liuyao-divination/
├── skill/liuyao-divination/SKILL.md   # The agent skill (start here)
├── references/                        # 12 methodology monographs (Chinese)
│   ├── 01-裝卦排盤.md                  #   casting & assignment
│   ├── 02-用神取用.md                  #   selecting the Significant Line
│   ├── 03-旺衰月日.md                  #   strength via month & day
│   ├── 04-動靜暗破.md                  #   move / dark-move / break / void
│   ├── 05-進退神化.md                  #   advancing & retreating transformation
│   ├── 06-三合六合.md                  #   combinations
│   ├── 07-墓庫論.md                    #   graveyard & storehouse theory
│   ├── 08-斷卦步驟.md                  #   the full interpretation workflow
│   ├── 09-四神與有力無力.md            #   four spirits & effective/ineffective
│   ├── 10-卦變反伏.md                  #   hexagram-change, fan-yin, fu-yin
│   ├── 12-應期與應驗.md                #   timing channels & layered verification
│   └── 13-象意解讀.md                  #   all-element imagery: one syntax, many readings
├── src/
│   ├── liuyao/                        # the casting engine (importable package)
│   └── paipan.py                      # CLI: cast & print a board
├── tools/
│   └── generate_report.py             # HTML report generator
├── examples/                          # validated case library (JSON)
├── tests/                             # golden-case tests (the canonical reading)
├── data/zhouyi.json                   # 64 卦辭 + 385 爻辭 (public-domain text)
└── docs/reports/                      # sample HTML reading reports
```

## 🚀 Quick start

### 1. Cast a board (CLI)

```bash
python src/paipan.py --hexagram 地澤臨 --moving 2 --month 未 --day 卯
```

Prints the full board: six relations, nayin stems, six spirits, world/response, void, month/day breaks, dark-move flags, advancing/retreating transformation, and graveyard status — all resolved against the month and day.

### 2. Generate an HTML report

```bash
python tools/generate_report.py examples/01-是否旺己-地澤臨之復.json -o outputs/report.html
```

### 3. Use as a Claude Code skill

```bash
# symlink (or copy) the skill into your skills directory
ln -s "$(pwd)/skill/liuyao-divination" ~/.claude/skills/liuyao-divination
```

Then ask Claude something like *"占問家人介紹的對象是否旺自己，主卦地澤臨九二動變復，辛卯日"* and it will follow the skill's workflow.

### 4. Analyze a new hexagram (full workflow)

Mechanics to the program, reasoning to the LLM — three steps:

```bash
# ① Scaffold: cast board + fetch hexagram/line texts + emit JSON skeleton + print a reasoning brief
python tools/new_case.py --hexagram 雷水解 --moving 3 --month 申 --day 甲子 \
    --question "占求職能否成" --yongshen 官鬼 -o examples/02-求職.json

# ② LLM reasoning: hand the brief to Claude, fill the JSON per SKILL.md's 8-step flow
#    (overview / sections / verdict / summary) — let the model do the imagery,
#    six-line analysis, and outcome推演

# ③ Generate report
python tools/generate_report.py examples/02-求職.json -o outputs/report.html
```

Casting, text lookup, and key judgments (dark-move / retreating / graveyard / combinations / effective-or-not) are computed exactly by the scaffold; interpretation is the LLM's job. See `references/08-斷卦步驟.md`.

## 🧪 Correctness

The engine is validated against a **canonical hand-analyzed case** (`examples/01-是否旺己-地澤臨之復.json`, 地澤臨 → 地雷復, 辛卯日). The test suite asserts the engine reproduces every hand-derived result: 妻財亥水 as the Significant Line on line 5, 子孫酉 as a **dark-move** (not a day-break — the key distinction), 世爻丁卯 entering the 未 graveyard and retreating to 庚寅, void at 午未 with no line actually void, and so on.

```bash
python -m pytest tests/
```

## 📚 The methodology

The interpretive rules encoded here favor the mainstream synthesis (《增刪卜易》 lineage) and explicitly flag the fine distinctions practitioners miss:

- **Dark-move vs day-break**: a still line struck by the day is a *dark-move* (暗動, awakened, useful) if **strong**, but a *day-break* (日破, shattered, useless) if **weak**. Same strike, opposite verdict.
- **Noble ≠ strong**: a line sitting on the emperor's seat (五爻君位) is *noble* (貴), not necessarily *strong* (旺) — strength still comes from month/day.
- **Graveyard nuance**: entering a **void graveyard** (空墓) means the entrapment is loose and escapable, not a dead end.
- **Advancing/retreating**: 卯→寅 is a retreating spirit (退神); 寅→卯 is advancing (進神).

See [`references/`](./references) for the full treatment and [`SKILL.md`](./skill/liuyao-divination/SKILL.md) for the workflow.

## 🤝 Contributing

Corrections to the engine's casting logic or the methodology docs are very welcome — accuracy is the whole point. Please open an issue first for substantive methodological changes (different lineages disagree, and we should pick deliberately).

## ⚠️ Disclaimer

Liu Yao is a **traditional cultural and divinatory practice**, not a science. This project is an engineering and cultural-preservation effort. Readings describe tendencies, imagery, and timing — they are **not predictions of fact** and must not replace real-world judgment in relationships, finances, health, or any decision. Use responsibly.

## 📄 License

[MIT](./LICENSE) © 2026 Johnson
