"""起卦與卦盤序列化。

本模組負責「使用者輸入 → 卦名／動爻」、「六爻銅錢法起卦」，
以及把引擎排好的 ``Board`` 轉成前端好用的 JSON（含繁體術語）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from liuyao import cast_board
from liuyao.data import HEXAGRAMS, BAGUA, find_hexagram

from .calendar import CastTime, cast_time_from_date, cast_time_from_datetime

# ────────────────────────────── 八卦與爻位 ──────────────────────────────

#: 三爻（自下而上，1=陽 0=陰）→ 八卦名
YAO3_TO_GUA = {
    (1, 1, 1): "乾", (1, 1, 0): "兌", (1, 0, 1): "離", (1, 0, 0): "震",
    (0, 1, 1): "巽", (0, 1, 0): "坎", (0, 0, 1): "艮", (0, 0, 0): "坤",
}
GUA_TO_YAO3 = {v: k for k, v in YAO3_TO_GUA.items()}

#: (上卦, 下卦) → 六十四卦全名
GUA_PAIR_TO_HEX = {
    (rec["upper"], rec["lower"]): rec["name"] for rec in HEXAGRAMS.values()
}

#: 爻位名（數字 → 序）
POS_NAMES = {1: "初", 2: "二", 3: "三", 4: "四", 5: "五", 6: "上"}

#: 用神六親
LIUQIN = ["父母", "兄弟", "子孫", "妻財", "官鬼"]

#: 六親對應的「象」提示，供前端選單說明
LIUQIN_HINTS = {
    "父母": "父母、長輩、文書、房屋、車輛、學業、契約",
    "兄弟": "兄弟、朋友、同事、競爭、破財、阻礙",
    "子孫": "子女、下屬、福神、醫藥、娛樂、寵物、解憂",
    "妻財": "妻子、女友、財物、薪水、投資、所求之財",
    "官鬼": "丈夫、男友、官職、工作、疾病、憂患、盜賊",
}

#: 卦辭爻辭（公有領域原文）
GUA_PAIR_TEXT = None


def _load_zhouyi() -> dict:
    """載入 64 卦卦辭爻辭（繁體）。"""
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent.parent / "data" / "zhouyi.json"
    import json

    global GUA_PAIR_TEXT
    if GUA_PAIR_TEXT is None:
        GUA_PAIR_TEXT = json.loads(path.read_text(encoding="utf-8"))
    return GUA_PAIR_TEXT


# ────────────────────────────── 卦名 ↔ 六爻 ──────────────────────────────

def hexagram_lines(name: str) -> list[int]:
    """由卦名（全名或單字別名）取六爻，自下而上，1=陽 0=陰。"""
    rec = find_hexagram(name)
    if rec is None:
        raise ValueError(f"查無此卦：{name}")
    return list(BAGUA[rec["lower"]]["yao"]) + list(BAGUA[rec["upper"]]["yao"])


def lines_to_hexagram(lines: list[int]) -> str:
    """由六爻（自下而上）取卦名。"""
    if len(lines) != 6:
        raise ValueError("六爻必須剛好 6 爻")
    lower = YAO3_TO_GUA[tuple(lines[0:3])]
    upper = YAO3_TO_GUA[tuple(lines[3:6])]
    name = GUA_PAIR_TO_HEX.get((upper, lower))
    if name is None:
        raise ValueError(f"無法對應卦名：{upper}上{lower}下")
    return name


def flip_moving(lines: list[int], moving: list[int]) -> list[int]:
    """動爻陰陽翻轉，得變卦六爻。"""
    out = list(lines)
    for pos in moving:
        i = pos - 1
        out[i] = 1 - out[i]
    return out


def yao_name(pos: int, yin_yang: str) -> str:
    """爻名：陽爻稱九、陰爻稱六。初爻置前、上爻置前。"""
    nine_six = "九" if yin_yang == "陽" else "六"
    if pos == 1:
        return "初" + nine_six
    if pos == 6:
        return "上" + nine_six
    return nine_six + POS_NAMES[pos]


def yao_positions(moving: list[int]) -> str:
    """動爻的爻位描述，如「二、四」；無動爻回「無」。"""
    if not moving:
        return "無"
    return "、".join(POS_NAMES[p] for p in sorted(moving))


# ────────────────────────────── 銅錢法起卦 ──────────────────────────────

#: 三枚銅錢：正面（字）計 3、反面（背）計 2。
#: 一爻三枚，合計：
#:   6 = 老陰（三背）→ 動爻，陰變陽
#:   7 = 少陽（二背一字）→ 靜爻，陽
#:   8 = 少陰（一背二字）→ 靜爻，陰
#:   9 = 老陽（三字）→ 動爻，陽變陰
TOSS_TABLE = {
    6: {"name": "老陰", "yin_yang": "陰", "moving": True, "coins": [2, 2, 2]},
    7: {"name": "少陽", "yin_yang": "陽", "moving": False, "coins": [3, 2, 2]},
    8: {"name": "少陰", "yin_yang": "陰", "moving": False, "coins": [3, 3, 2]},
    9: {"name": "老陽", "yin_yang": "陽", "moving": True, "coins": [3, 3, 3]},
}


def toss_coins(rng: random.Random | None = None) -> dict:
    """擲三枚銅錢一次，回傳該爻的結果。"""
    rng = rng or random.Random()
    coins = [rng.choice([2, 3]) for _ in range(3)]
    total = sum(coins)
    info = TOSS_TABLE[total]
    return {
        "total": total,
        "name": info["name"],
        "yin_yang": info["yin_yang"],
        "moving": info["moving"],
        "coins": coins,
    }


def cast_by_coins(rng: random.Random | None = None) -> dict:
    """完整起卦：擲六次（自下而上），得卦名、動爻、變卦。"""
    rng = rng or random.Random()
    tosses: list[dict] = []
    for _ in range(6):
        tosses.append(toss_coins(rng))

    lines = [1 if t["yin_yang"] == "陽" else 0 for t in tosses]
    moving = [i + 1 for i, t in enumerate(tosses) if t["moving"]]
    name = lines_to_hexagram(lines)
    changed = lines_to_hexagram(flip_moving(lines, moving)) if moving else None
    return {
        "hexagram": name,
        "moving": moving,
        "changed": changed,
        "lines": lines,
        "tosses": tosses,
    }


# ────────────────────────────── 完整占卦 ──────────────────────────────

@dataclass
class CastRequest:
    """一次占卦請求。"""

    question: str
    hexagram: str | None = None          # 指定卦名（可選）
    moving: list[int] = field(default_factory=list)
    yongshen: str | None = None          # 用神六親（可選，未給則自動推）
    when: datetime | None = None         # 占卦時間，預設現在
    use_coins: bool = False              # True = 由程式擲錢起卦
    line_values: list[int] = field(default_factory=list)  # 6/7/8/9 六爻，自下而上
    gender: str = ""                     # 占問者性別（男/女），感情題取用神用

    def resolved_time(self) -> CastTime:
        if self.when is None:
            return cast_time_from_datetime(datetime.now().astimezone())
        return cast_time_from_datetime(self.when)


#: 由占問文字自動推用神（關鍵詞 → 六親）。取「最先命中」的規則。
YONGSHEN_RULES: list[tuple[str, str]] = [
    # 官鬼：工作、職位、考試功名、疾病、官司、憂患、丈夫/男友
    ("官鬼", "工作 求職 事業 職位 升遷 考試 功名 公職 面試 錄取 官司 訴訟 疾病 病 醫 男友 丈夫 老公 上司 主管"),
    # 妻財：財運、薪水、投資、買賣、妻子/女友、失物
    ("妻財", "財 錢 收入 薪水 投資 股票 買賣 生意 賺 賠 發財 女友 女朋友 妻子 老婆 女緣 感情 姻緣 戀愛 婚姻 對象 物件 交往 桃花 失物 找東西"),
    # 子孫：子女、下屬、寵物、醫藥、懷孕、解憂
    ("子孫", "子女 孩子 兒子 女兒 懷孕 生育 下屬 員工 學生 寵物 醫藥 治病 康復 考試運"),
    # 父母：長輩、文書、學業、房屋、車輛、契約
    ("父母", "父母 父 母 長輩 家人 房屋 房子 搬家 買房 車輛 車 學業 學位 論文 考試成績 契約 合約 檔案 證書 電話 訊息"),
    # 兄弟：朋友、同事、競爭、合夥
    ("兄弟", "兄弟 姊妹 朋友 同事 同學 合夥 合作 競爭 借錢 還錢"),
]


def infer_yongshen(question: str, gender: str = "") -> tuple[str | None, str]:
    """由占問文字與性別推用神，回傳 (六親, 理由)。"""
    q = question or ""
    g = str(gender or "").strip()
    generic = ("感情", "姻緣", "戀愛", "婚姻", "交往", "桃花", "對象")
    female_terms = ("女友", "女朋友", "妻子", "老婆", "女緣")
    male_terms = ("男友", "男朋友", "丈夫", "老公")
    if g in ("男", "male") and any(w in q for w in generic) and not any(w in q for w in male_terms):
        return "妻財", "占問者為男性，感情題以妻財為用神。"
    if g in ("女", "female") and any(w in q for w in generic) and not any(w in q for w in female_terms):
        return "官鬼", "占問者為女性，感情題以官鬼為用神。"
    for qin, words in YONGSHEN_RULES:
        hits = [w for w in words.split() if w in q]
        if hits:
            return qin, f"占問提及「{'、'.join(hits[:3])}」，依用神取用規則取{qin}。"
    return None, ""


# ────────────────────────────── 卦盤序列化 ──────────────────────────────

def _line_tags(ln) -> list[str]:
    """單爻的標註標籤（繁體、去重、保留順序）。"""
    tags: list[str] = []
    if ln.is_world:
        tags.append("世")
    if ln.is_response:
        tags.append("應")
    if ln.is_moving:
        tags.append("動")
    if ln.void:
        tags.append("空亡")
    if ln.true_void:
        tags.append("真空")
    if ln.month_break:
        tags.append("月破")
    if ln.dark_move:
        tags.append("暗動")
    if ln.day_break:
        tags.append("日破")
    if ln.is_on_month:
        tags.append("臨月建")
    if ln.is_on_day:
        tags.append("臨日建")
    if ln.day_strike_moving:
        tags.append(ln.day_strike_moving)
    if ln.jin_tui:
        tags.append(ln.jin_tui)
    for g in ln.in_grave:
        tags.append(g)
    if ln.grave_is_void:
        tags.append("空墓")
    if ln.role and ln.role not in ("閒神", "閒神"):
        tags.append(ln.role)
    # 去重但保序
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def board_to_dict(board, cast_time: CastTime) -> dict:
    """把引擎卦盤轉成前端／LLM 用的完整 JSON（繁體）。"""
    lines = []
    for pos in range(6, 0, -1):          # 上爻在上，方便前端直接渲染
        ln = board.line(pos)
        lines.append({
            "pos": pos,
            "pos_name": POS_NAMES[pos],
            "yao_name": yao_name(pos, ln.yin_yang),
            "yin_yang": ln.yin_yang,
            "gan": ln.gan,
            "zhi": ln.zhi,
            "wx": ln.wx,
            "qin": ln.qin,
            "shen": ln.shen,
            "is_world": ln.is_world,
            "is_response": ln.is_response,
            "is_moving": ln.is_moving,
            "void": ln.void,
            "month_break": ln.month_break,
            "day_break": ln.day_break,
            "dark_move": ln.dark_move,
            "true_void": ln.true_void,
            "state": ln.state,
            "stage": ln.stage,
            "jin_tui": ln.jin_tui,
            "in_grave": list(ln.in_grave),
            "grave_is_void": ln.grave_is_void,
            "role": ln.role,
            "effective": ln.effective,
            "effective_reason": ln.effective_reason,
            "change_gan": ln.change_gan,
            "change_zhi": ln.change_zhi,
            "change_qin": ln.change_qin,
            "change_wx": ln.change_wx,
            "tags": _line_tags(ln),
        })

    # 變卦六爻（完整納甲）
    changed_lines = []
    if board.changed_hexagram and board.changed_lower_gua and board.changed_upper_gua:
        for info in board.changed_line_info():
            main = board.line(info["pos"])
            changed_lines.append({
                "pos": info["pos"],
                "pos_name": POS_NAMES[info["pos"]],
                "yao_name": yao_name(info["pos"], info["yin_yang"]),
                "yin_yang": info["yin_yang"],
                "gan": info["gan"],
                "zhi": info["zhi"],
                "wx": info["wx"],
                "qin": info["qin"],
                "shen": info["shen"],
                "is_moving": main.is_moving,
                "jin_tui": main.jin_tui if main.is_moving else None,
            })

    zhouyi = _load_zhouyi()
    main_text = zhouyi.get(board.hexagram, {})
    changed_text = zhouyi.get(board.changed_hexagram, {}) if board.changed_hexagram else {}

    return {
        "question": None,                 # 由呼叫端補
        "cast_time": cast_time.to_dict(),
        "hexagram": board.hexagram,
        "changed_hexagram": board.changed_hexagram,
        "palace": board.palace,
        "palace_wx": board.palace_wx,
        "world_pos": board.world_pos,
        "response_pos": board.response_pos,
        "month_zhi": board.month_zhi,
        "month_wx": board.month_wx,
        "day_gz": board.day_gz,
        "day_wx": board.day_wx,
        "xunkong": list(board.xunkong),
        "yongshen_qin": board.yongshen_qin,
        "yongshen_lines": [
            {"pos": l.position, "yao_name": yao_name(l.position, l.yin_yang),
             "gan": l.gan, "zhi": l.zhi, "wx": l.wx}
            for l in board.yongshen_lines
        ],
        "yongshen_fu": list(board.yongshen_fu),
        "fu_shen": list(board.fu_shen),
        "moving_positions": [l.position for l in board.moving_lines],
        "moving_text": yao_positions([l.position for l in board.moving_lines]),
        "lines": lines,
        "changed_lines": changed_lines,
        # 卦級判定
        "gua_bian": board.gua_bian,
        "fu_yin": board.fu_yin,
        "fan_yin": board.fan_yin,
        "sanhe": board.sanhe,
        "sanhe_local": board.sanhe_local,
        "is_liuhe_gua": board.is_liuhe_gua,
        "is_liuchong_gua": board.is_liuchong_gua,
        "changed_is_liuhe": board.changed_is_liuhe,
        "changed_is_liuchong": board.changed_is_liuchong,
        # 卦爻辭
        "gua_ci": main_text.get("gua_ci", ""),
        "yao_ci": main_text.get("yao", {}),
        "changed_gua_ci": changed_text.get("gua_ci", ""),
    }


def build_cast(req: CastRequest) -> dict:
    """執行一次完整占卦：定時 → 起卦 → 排盤 → 序列化。

    回傳含 ``board``（卦盤 JSON）與 ``meta``（占問資訊）的字典。
    """
    ct = req.resolved_time()

    line_values = []
    if req.line_values:
        line_values = [int(v) for v in req.line_values]
        if len(line_values) != 6:
            raise ValueError("line_values 必須剛好六個數字")
        if any(v not in (6, 7, 8, 9) for v in line_values):
            raise ValueError("line_values 只能是 6、7、8、9")
        bits = [1 if v in (7, 9) else 0 for v in line_values]
        hexagram = lines_to_hexagram(bits)
        moving = [i + 1 for i, v in enumerate(line_values) if v in (6, 9)]
        tosses = []
    elif req.use_coins or (req.hexagram is None):
        tossed = cast_by_coins()
        hexagram = tossed["hexagram"]
        moving = tossed["moving"]
        tosses = tossed["tosses"]
    else:
        hexagram = req.hexagram
        moving = sorted(set(req.moving or []))
        tosses = []

    if any(p < 1 or p > 6 for p in moving):
        raise ValueError("動爻位置必須介於 1 到 6")

    yongshen = req.yongshen
    yongshen_reason = ""
    if not yongshen:
        yongshen, yongshen_reason = infer_yongshen(req.question, req.gender)

    board = cast_board(hexagram, moving, ct.month_zhi, ct.day_gz, yongshen)
    data = board_to_dict(board, ct)
    data["question"] = req.question
    data["gender"] = req.gender
    data["yongshen_reason"] = yongshen_reason

    return {
        "meta": {
            "question": req.question,
            "yongshen": yongshen or "",
            "yongshen_reason": yongshen_reason,
            "gender": req.gender,
            "use_coins": bool(tosses),
            "tosses": tosses,
            "line_values": line_values,
        },
        "board": data,
    }


def board_to_prompt_text(board: dict) -> str:
    """把卦盤 JSON 壓成給 LLM 閱讀的純文字（結構清楚、資訊完整）。"""
    ct = board["cast_time"]
    out = []
    out.append("【占卦時間】")
    out.append(f"{ct['moment_display']}（{ct['lunar_text']}）")
    out.append(f"年：{ct['year_gz']}　月：{ct['month_gz']}（月建{ct['month_zhi']}）"
               f"　日：{ct['day_gz']}（{ct['day_zhi']}）　時辰：{ct['shichen']}")
    out.append(f"旬空：{ct['xunkong'][0]}、{ct['xunkong'][1]}　所屬節氣：{ct['jie']}")
    if board.get("gender"):
        out.append(f"占問者性別：{board['gender']}")
    out.append("")
    out.append("【卦盤】")
    out.append(f"主卦：{board['hexagram']}（{board['palace']}宮·{board['palace_wx']}）"
               f"　→　變卦：{board['changed_hexagram'] or '（無動爻）'}")
    out.append(f"世爻在 {board['world_pos']} 爻，應爻在 {board['response_pos']} 爻；"
               f"動爻：{board['moving_text']}")
    out.append(f"用神：{board['yongshen_qin'] or '（未取）'}")
    if board["yongshen_lines"]:
        ys = "、".join(f"{l['yao_name']}（{l['gan']}{l['zhi']}{l['wx']}）"
                       for l in board["yongshen_lines"])
        out.append(f"用神所在：{ys}")
    out.append("")
    out.append("【六爻明細】（上爻在上）")
    out.append("爻位 | 六神 | 六親 | 納甲 | 陰陽 | 旺衰 | 長生 | 標註 | 變爻")
    for ln in board["lines"]:
        change = ""
        if ln["is_moving"] and ln["change_zhi"]:
            change = f"{ln['change_gan']}{ln['change_zhi']}（{ln['change_qin']}）"
        tags = "、".join(ln["tags"]) if ln["tags"] else "靜"
        out.append(
            f"{ln['yao_name']} | {ln['shen']} | {ln['qin']} | "
            f"{ln['gan']}{ln['zhi']}{ln['wx']} | {ln['yin_yang']} | "
            f"{ln['state'] or '無'} | {ln['stage'] or '無'} | {tags} | {change or '無'}"
        )
    out.append("")
    if board.get("fu_shen"):
        out.append("【伏神】（本宮首卦補缺六親）")
        for f in board["fu_shen"]:
            fei = f["fei"]
            tail = "可出伏" if f.get("can_chu") else "不能出伏"
            if f.get("blockers"):
                tail += "；受阻：" + "、".join(f["blockers"])
            elif f.get("reasons"):
                tail += "；依據：" + "、".join(f["reasons"][:3])
            line = (
                f"伏神 {f['qin']}{f['zhi']}{f['wx']}，"
                f"伏於{fei['pos_name']}爻{fei['qin']}{fei['zhi']}{fei['wx']}之下"
                f"（{f['relation']}；{tail}）"
            )
            if len(f.get("candidates") or []) > 1:
                line += "；同六親候選爻位 " + "、".join(str(p) for p in f["candidates"])
            out.append(line)
        if board.get("yongshen_fu"):
            out.append("用神不上卦，以同六親伏神為用神；能否出伏直接影響此事能否成。")
    out.append("")
    out.append("【卦級判定】")
    flags = []
    if board["is_liuhe_gua"]:
        flags.append("主卦六合卦")
    if board["is_liuchong_gua"]:
        flags.append("主卦六沖卦")
    if board["changed_is_liuhe"]:
        flags.append("變卦六合卦")
    if board["changed_is_liuchong"]:
        flags.append("變卦六沖卦")
    if board["fu_yin"]:
        flags.append("伏吟")
    if board["fan_yin"]:
        flags.append("反吟")
    if board["gua_bian"] and board["gua_bian"] != "變卦未明":
        flags.append(board["gua_bian"])
    if flags:
        out.append("、".join(flags))
    # 三合只把「實成之局」送進 prompt；虛合、缺支、待填實不必讓模型拿來湊數。
    formed_sanhe = {
        ju: info for ju, info in (board.get("sanhe") or {}).items()
        if str(info.get("status", "")).startswith("實成")
    }
    for ju, info in formed_sanhe.items():
        out.append(f"三合：{ju} → {info['status']}")
    for item in board.get("sanhe_local") or []:
        out.append(f"{item['type']}：{item['ju']}（{item['combo']}）")
    out.append("")
    out.append("【卦爻辭】")
    out.append(f"主卦 {board['hexagram']}：{board['gua_ci']}")
    for pos in board["moving_positions"]:
        ln = next(l for l in board["lines"] if l["pos"] == pos)
        key = ln["yao_name"]
        ci = board["yao_ci"].get(key, "")
        if ci:
            out.append(f"動爻 {key}：{ci}")
    if board["changed_hexagram"]:
        out.append(f"變卦 {board['changed_hexagram']}：{board['changed_gua_ci']}")
    return "\n".join(out)
