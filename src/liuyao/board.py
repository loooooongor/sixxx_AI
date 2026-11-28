"""排盤主邏輯：把主卦+動爻+月日 裝成完整的結構化卦盤。

cast_board(...) 返回 Board 物件，含六爻的全部資訊：
陰陽、納甲、六親、六神、世應、動變、空亡、月破、日破、暗動、化進化退、入墓、旺衰。
"""

import itertools

from .data import (
    BAGUA, BAGUA_NAGAN, BAGUA_NAZHI, DIZHI_WUXING, WUXING_MU,
    WUXING_SHENG, WUXING_KE,
    JINSHEN, TUISHEN, LIUSHEN_ORDER, LIUSHEN_START, find_hexagram, HEXAGRAMS,
    CHONG, LIUHE,
)

# 三合局：三支 + 化出五行
SANHE_JU = [
    ("申", "子", "辰", "水"),
    ("亥", "卯", "未", "木"),
    ("寅", "午", "戌", "火"),
    ("巳", "酉", "丑", "金"),
]
from .wuxing import (
    liuqin, wuxing_state, shier_changsheng, is_prosperous,
    xunkong, is_void, is_chong, yongshen_role, i_sheng, i_ke,
    is_true_void, four_gods,
)


def _yao_to_bagua(yao3):
    """由三爻(自下而上 [初,中,上]，1陽0陰)反查八卦名。"""
    for name, info in BAGUA.items():
        if info["yao"] == yao3:
            return name
    raise ValueError(f"無法識別的卦象: {yao3}")


def _find_changed_hexagram(changed_lower_gua, changed_upper_gua):
    """由變卦的上下卦反查變卦全名（可能查不到組合，返回 None）。"""
    for rec in HEXAGRAMS.values():
        if rec["upper"] == changed_upper_gua and rec["lower"] == changed_lower_gua:
            return rec["name"]
    return None


def _spirit_effective(ln, board):
    """判定元神/忌神是否有力（有效）。返回 (effective, reason)。

    effective: True=有力(能生用/能克用), False=無力(見生不生/雖動不克), None=中和不定。
    依據《增刪卜易·用神元神忌神仇神章》有力五條/無用六條/忌神不克七條綜合。
    """
    # —— 明顯無力（任一命中即無力）——
    if ln.month_break:
        return (False, "月破無力")
    if ln.in_grave:
        return (False, "入墓無力")
    if ln.jin_tui == "化回頭克":
        return (False, "化回頭克無力")
    if ln.jin_tui == "化退神":
        return (False, "化退神無力")
    if ln.day_break:
        return (False, "日破無力")
    if ln.true_void:
        return (False, "真空無力")
    if ln.state in ("囚", "死") and ln.void:
        return (False, "休囚旬空無力")
    if ln.state in ("囚", "死") and not ln.is_moving and not ln.dark_move:
        return (False, "休囚不動無力")
    if ln.state in ("囚", "死") and ln.stage in ("絕", "墓", "死") and not ln.is_moving:
        return (False, "衰絕無力")

    # —— 有力（任一命中即有力）——
    if ln.is_on_month or ln.is_on_day:
        return (True, "臨日月有力")
    if ln.state in ("旺", "相"):
        return (True, "旺相有力")
    if ln.jin_tui in ("化回頭生", "化進神"):
        return (True, f"{ln.jin_tui}有力")
    if ln.is_moving or ln.dark_move:
        return (True, "發動有力")

    return (None, "中和")


def _analyze_gua_bian(board):
    """卦變生克：以主卦宮五行 vs 變卦宮五行（《增刪卜易·卦變生克墓絕章》）。

    變生/變比和為吉，變克為凶。
    """
    main_wx = board.palace_wx
    ch_name = board.changed_hexagram
    if not ch_name:
        board.gua_bian = "變卦未明"
        return
    ch_rec = find_hexagram(ch_name)
    if not ch_rec:
        board.gua_bian = "變卦未明"
        return
    ch_wx = ch_rec["palace_wx"]
    if ch_wx == main_wx:
        board.gua_bian = "變比和(吉)"
    elif i_sheng(ch_wx) == main_wx:
        board.gua_bian = "變生主(吉)"
    elif i_ke(ch_wx) == main_wx:
        board.gua_bian = "變克主(凶)"
    elif i_sheng(main_wx) == ch_wx:
        board.gua_bian = "主生變(洩)"
    elif i_ke(main_wx) == ch_wx:
        board.gua_bian = "主克變(制)"
    else:
        board.gua_bian = "無"


def _detect_fu_fan_yin(board):
    """伏吟：主卦六爻地支全等於變卦地支(卦變而地支不變)。
    反吟(簡化)：所有動爻皆化回頭沖(變爻地支衝動爻地支)。"""
    moving = board.moving_lines
    if not moving:
        return
    orig_zhi = [ln.zhi for ln in board.lines]
    changed_zhi = [ln.change_zhi if ln.is_moving else ln.zhi for ln in board.lines]
    if changed_zhi == orig_zhi:
        board.fu_yin = True
    if all(CHONG.get(ln.zhi) == ln.change_zhi for ln in moving):
        board.fan_yin = True


def _detect_sanhe(board):
    """檢測三合成局：只認位置正確或日月助成的局。

    成局條件（任一）：
    * 初爻、三爻皆為動爻（明動/暗動），且這兩爻的支為局中兩支；
    * 四爻、上爻皆為動爻（明動/暗動），且這兩爻的支為局中兩支；
    * 三支中有一支在月建或日辰，且其餘兩支都是動爻。

    其餘情況即使三支都在卦中，也只是虛合；靜爻不得拿來湊局。
    """
    line_at = {ln.position: ln for ln in board.lines}
    board_zhi = {ln.zhi for ln in board.lines}
    month_day = {board.month_zhi, board.day_zhi}
    active = lambda ln: bool(ln.is_moving or getattr(ln, "dark_move", False))
    active_zhi = {ln.zhi for ln in board.lines if active(ln)}

    result = {}
    for a, b, c, wx in SANHE_JU:
        tri = (a, b, c)
        trio = set(tri)
        in_board_zhi = [z for z in tri if z in board_zhi]
        if not in_board_zhi:
            continue
        moving_count = sum(1 for z in tri if z in active_zhi)

        pair_reasons = []
        for label, (p1, p2) in (("內卦", (1, 3)), ("外卦", (4, 6))):
            l1, l2 = line_at.get(p1), line_at.get(p2)
            if (l1 and l2 and active(l1) and active(l2)
                    and l1.zhi in trio and l2.zhi in trio
                    and l1.zhi != l2.zhi):
                pair_reasons.append(label)

        day_month_reason = False
        for dm in trio & month_day:
            others = trio - {dm}
            if all(
                any(ln.zhi == z and active(ln) for ln in board.lines)
                for z in others
            ):
                day_month_reason = True
                break

        if pair_reasons or day_month_reason:
            status = "實成之局"
            formed_by = pair_reasons + (["日月"] if day_month_reason else [])
        elif len(in_board_zhi) == 3:
            status = "虛合待用(位置或動爻不足)"
            formed_by = []
        else:
            missing = [z for z in tri if z not in board_zhi and z not in month_day]
            if missing:
                status = f"虛合(缺{''.join(missing)}，待填實)"
            else:
                status = "虛合待用(日月有支、動爻不足)"
            formed_by = []

        result[f"{a}{b}{c}{wx}局"] = {
            "status": status,
            "moving_count": moving_count,
            "branches_in_board": in_board_zhi,
            "formed_by": formed_by,
        }
    board.sanhe = result


def _fei_fu_relation(fei_wx, fu_wx):
    """飛神與伏神的五行關係。"""
    if WUXING_SHENG.get(fei_wx) == fu_wx:
        return "飛生伏", "飛神生伏神，伏神得生，較易出伏"
    if WUXING_SHENG.get(fu_wx) == fei_wx:
        return "伏生飛", "伏神生飛神，伏神洩氣，較難出伏"
    if WUXING_KE.get(fei_wx) == fu_wx:
        return "飛剋伏", "飛神剋伏神，伏神受制，較難出伏"
    if WUXING_KE.get(fu_wx) == fei_wx:
        return "伏剋飛", "伏神剋飛神，伏神有力，但出伏帶制約"
    return "比和", "飛伏比和，伏神得扶持"


def _detect_fushen(board):
    """依本宮首卦補缺六親，計算飛神、伏神、飛伏關係與出伏。

    規則：
    * 只在本卦六親不全時取伏神；
    * 伏神取自本宮首卦（八純卦）同一六親所在爻位；
    * 同六親多爻時先取最低爻位，另列 candidates 供核對；
    * 伏神出伏看飛神空破休囚、伏神日月生扶/臨值/日沖、飛生伏或比和；
      伏神空亡、月破或飛神旺相剋伏時，先論受制，不能出伏。
    """
    actual_qins = {ln.qin for ln in board.lines if ln.qin}
    if len(actual_qins) >= 5:
        board.fu_shen = []
        return
    pure_zhi = BAGUA_NAZHI.get(board.palace)
    if not pure_zhi:
        return
    pure_names = {
        "乾": "乾為天", "坎": "坎為水", "艮": "艮為山", "震": "震為雷",
        "巽": "巽為風", "離": "離為火", "坤": "坤為地", "兌": "兌為澤",
    }
    pure = []
    for pos, zhi in enumerate(pure_zhi, 1):
        wx = DIZHI_WUXING[zhi]
        pure.append({
            "pos": pos, "zhi": zhi, "wx": wx,
            "qin": liuqin(wx, board.palace_wx),
        })

    result = []
    for qin in ("父母", "兄弟", "子孫", "妻財", "官鬼"):
        if qin in actual_qins:
            continue
        candidates = [p for p in pure if p["qin"] == qin]
        if not candidates:
            continue
        src = candidates[0]
        fei = board.line(src["pos"])
        relation, relation_note = _fei_fu_relation(fei.wx, src["wx"])
        reasons = []
        blockers = []

        if fei.void:
            reasons.append("飛神空亡")
        if fei.state in ("休", "囚", "死"):
            reasons.append("飛神休囚")
        if fei.month_break or fei.day_break:
            reasons.append("飛神沖破")
        if (WUXING_SHENG.get(board.month_wx) == src["wx"]
                or WUXING_SHENG.get(board.day_wx) == src["wx"]):
            reasons.append("日月生扶伏神")
        if board.month_wx == src["wx"] or board.day_wx == src["wx"]:
            reasons.append("日月比和伏神")
        if src["zhi"] in (board.month_zhi, board.day_zhi):
            reasons.append("伏神臨日月")
        if is_chong(board.day_zhi, src["zhi"]) or is_chong(src["zhi"], board.day_zhi):
            reasons.append("伏神得日沖動")
        if relation in ("飛生伏", "比和", "伏剋飛"):
            reasons.append(relation_note)
        if relation == "伏生飛":
            blockers.append("伏神洩氣")
        if relation == "飛剋伏" and not any(r.startswith("飛神") for r in reasons):
            blockers.append("飛神旺相剋伏")
        if src["zhi"] in board.xunkong:
            blockers.append("伏神空亡")
        if is_chong(board.month_zhi, src["zhi"]) or is_chong(src["zhi"], board.month_zhi):
            blockers.append("伏神月破")

        can_chu = bool(reasons) and not blockers
        result.append({
            "pos": src["pos"],
            "pos_name": board.line(src["pos"]).name,
            "qin": qin,
            "zhi": src["zhi"],
            "wx": src["wx"],
            "state": wuxing_state(src["wx"], board.month_wx),
            "pure_gua": pure_names.get(board.palace, board.palace + "宮首卦"),
            "fei": {
                "pos": fei.position,
                "pos_name": fei.name,
                "qin": fei.qin,
                "zhi": fei.zhi,
                "wx": fei.wx,
                "state": fei.state,
                "void": bool(fei.void),
            },
            "relation": relation,
            "relation_note": relation_note,
            "can_chu": can_chu,
            "reasons": reasons,
            "blockers": blockers,
            "candidates": [p["pos"] for p in candidates],
        })
    board.fu_shen = result
    board.yongshen_fu = [
        item for item in result if board.yongshen_qin and item["qin"] == board.yongshen_qin
    ]


def _match_sanhe(zhis):
    """三支恰成一局則返回 SANHE_JU 該條 (支,支,支,五行)，否則 None。"""
    if len(set(zhis)) != 3:
        return None
    trio = set(zhis)
    for a, b, c, wx in SANHE_JU:
        if trio == {a, b, c}:
            return (a, b, c, wx)
    return None


def _detect_sanhe_local(board):
    """內卦三合局／外卦三合局：位置限定的「動爻＋變爻」成局。

    規則（《增刪卜易·三合章》之外，坊間另有內外卦成局法）：
    * 內卦三合局：初爻、三爻**皆明動**方可論（暗動本質為靜爻，不計）；
    * 外卦三合局：四爻、上爻皆明動方可論；
    * 位置不對（二、五爻，或只動其中一爻）不能成局；
    * 成局三支須取自該內／外卦兩動爻的「原支＋變支」，且動支、變支必須並見。
    """
    result = []
    for kind, positions in (("內卦三合局", (1, 3)), ("外卦三合局", (4, 6))):
        pair = [board.line(p) for p in positions]
        if not all(ln.is_moving for ln in pair):
            continue
        slots = []
        for ln in pair:
            slots.append((f"{ln.name}爻動", ln.zhi, "動"))
            slots.append((f"{ln.name}爻化", ln.change_zhi, "變"))
        seen = {}
        for combo in itertools.combinations(slots, 3):
            trio = _match_sanhe([s[1] for s in combo])
            if trio is None:
                continue
            if {s[2] for s in combo} != {"動", "變"}:
                continue          # 純動支或純變支，非「動變並見」
            key = frozenset(s[1] for s in combo)
            score = sum(1 for s in combo if s[2] == "動")
            if key not in seen or score > seen[key][0]:
                seen[key] = (score, combo, trio)
        for score, combo, trio in seen.values():
            ju = f"{trio[0]}{trio[1]}{trio[2]}{trio[3]}局"
            item = {
                "type": kind,
                "ju": ju,
                "wx": trio[3],
                "positions": list(positions),
                "members": [{"line": s[0], "zhi": s[1]} for s in combo],
                "combo": "·".join(f"{s[0]}（{s[1]}）" for s in combo),
            }
            result.append(item)
            info = board.sanhe.get(ju)
            if info is None:
                info = {"status": "實成之局", "moving_count": score,
                        "formed_by": [kind], "members": item["members"]}
                board.sanhe[ju] = info
            else:
                if not info["status"].startswith("實成"):
                    info["status"] = "實成之局"
                formed = info.get("formed_by") or []
                if isinstance(formed, str):
                    formed = [formed]
                if kind not in formed:
                    formed.append(kind)
                info["formed_by"] = formed
                info.setdefault("members", item["members"])
    board.sanhe_local = result


def _detect_liuhe_liuchong(board, ch_lower, ch_upper):
    """檢測六合卦/六沖卦（《增刪卜易·六合章/六沖章》）。

    六合卦：初四、二五、三上 三對皆地支六合；六沖卦：三對皆六沖。主卦、變卦各檢測。
    """
    pairs = [(0, 3), (1, 4), (2, 5)]  # 初四 / 二五 / 三上（0 基）

    def check(zhi6):
        he = all(LIUHE[zhi6[a]] == zhi6[b] for a, b in pairs)
        ch = all(CHONG[zhi6[a]] == zhi6[b] for a, b in pairs)
        return he, ch

    main = [l.zhi for l in board.lines]
    board.is_liuhe_gua, board.is_liuchong_gua = check(main)
    ch6 = BAGUA_NAZHI[ch_lower][:3] + BAGUA_NAZHI[ch_upper][3:]
    board.changed_is_liuhe, board.changed_is_liuchong = check(ch6)


def _detect_dark_move(board):
    """暗動／日破（《增刪卜易·日辰章》：靜爻逢日沖，旺相為暗動，休囚為日破）。

    暗動成立條件：
    1. 必須是**靜爻**——被日沖的是動爻，已是發動，不論暗動（另判動而愈動／沖散）；
    2. 被**日辰六沖**；
    3. 爻本身**旺相**（月令旺相或得月日生扶比和）→ 暗動；不旺相 → 日破。
    另一條來路：靜爻雖不旺，但**得明動之爻生助**（動爻五行生此爻），逢日沖亦作暗動。
    故日沖之爻分三路：旺相暗動 / 得動爻生助暗動 / 休囚無助日破。
    """
    movers = board.moving_lines
    for ln in board.lines:
        if ln.is_moving or not ln.day_strike:
            continue
        if ln.prosperous:
            ln.dark_move = True
            ln.dark_move_reason = "旺相逢沖"
            continue
        helpers = [m for m in movers if i_sheng(m.wx) == ln.wx]
        if helpers:
            ln.dark_move = True
            ln.dark_move_reason = "得動爻生助"
            ln.dark_move_via = [f"{m.name}爻{m.zhi}{m.wx}" for m in helpers]
        else:
            ln.day_break = True


class Line:
    """單爻資訊。"""

    def __init__(self, position):
        self.position = position            # 1..6
        self.name = {1: "初", 2: "二", 3: "三", 4: "四", 5: "五", 6: "上"}[position]
        self.yin_yang = None                # "陽"/"陰"
        self.gan = None                     # 天干
        self.zhi = None                     # 地支
        self.wx = None                      # 爻五行
        self.qin = None                     # 六親
        self.shen = None                    # 六神
        self.is_world = False
        self.is_response = False
        self.is_moving = False
        # 動爻變爻
        self.change_gan = None
        self.change_zhi = None
        self.change_wx = None
        self.change_qin = None
        # 狀態標記
        self.void = False                   # 空亡
        self.month_break = False            # 月破
        self.day_strike = False             # 被日沖
        self.dark_move = False              # 暗動
        self.dark_move_reason = ""          # 暗動緣由："旺相逢沖"/"得動爻生助"
        self.dark_move_via = []             # 得動爻生助者：動爻清單
        self.day_break = False              # 日破
        self.prosperous = False             # 旺相
        self.jin_tui = None                 # "化進神"/"化退神"/"化回頭生"/"化回頭克"/"化比和"
        self.in_grave = []                  # 入墓原因列表
        self.grave_is_void = False          # 是否入空墓
        self.stage = None                   # 十二長生階段
        self.state = None                   # 旺相休囚死
        self.role = None                    # 相對用神的四神角色(用/元/忌/仇/閒)
        # —— 擴充套件判定 ——
        self.is_on_day = False              # 臨日建(爻支==日支)
        self.is_on_month = False            # 臨月建(爻支==月支)
        self.true_void = False              # 真空(旬空且當季死地)
        self.day_strike_moving = None       # 動爻被日沖："動而愈動"/"動而沖散"
        self.effective = None               # 元神/忌神是否有力 True/False/None
        self.effective_reason = ""          # 有力/無力理由

    def label(self):
        """組合標註，用於展示。"""
        tags = []
        if self.is_world:
            tags.append("世")
        if self.is_response:
            tags.append("應")
        if self.is_moving:
            tags.append("動")
        if self.void:
            tags.append("空")
        if self.month_break:
            tags.append("月破")
        if self.dark_move:
            tags.append("暗動")
            if self.dark_move_reason == "得動爻生助":
                tags.append("動爻生助")
        if self.day_break:
            tags.append("日破")
        if self.is_on_month:
            tags.append("臨月建")
        if self.is_on_day:
            tags.append("臨日建")
        if self.true_void:
            tags.append("真空")
        if self.day_strike_moving:
            tags.append(self.day_strike_moving)
        if self.jin_tui:
            tags.append(self.jin_tui)
        for g in self.in_grave:
            tags.append(g)
        if self.grave_is_void:
            tags.append("空墓")
        return tags


class Board:
    """完整卦盤。"""

    def __init__(self):
        self.hexagram = None
        self.changed_hexagram = None
        self.palace = None
        self.palace_wx = None
        self.world_pos = None
        self.response_pos = None
        self.month_zhi = None
        self.month_wx = None
        self.day_gz = None
        self.day_gan = None
        self.day_zhi = None
        self.day_wx = None
        self.xunkong = None                 # (支,支)
        self.lines = [Line(i) for i in range(1, 7)]
        self.yongshen_qin = None
        self.yongshen_lines = []
        self.yongshen_wx = None             # 用神爻五行(四神判定基準)
        # —— 卦級分析 ——
        self.gua_bian = None                # 卦變生克(主宮vs變宮)
        self.fu_yin = False                 # 伏吟
        self.fan_yin = False                # 反吟
        self.sanhe = {}                     # 三合局檢測結果
        self.sanhe_local = []               # 內卦／外卦三合局（動變成局）
        self.fu_shen = []                   # 伏神（本宮首卦補缺六親）
        self.yongshen_fu = []               # 用神不上卦時，同六親的伏神

        self.is_liuhe_gua = False           # 主卦六合卦
        self.is_liuchong_gua = False        # 主卦六沖卦
        self.changed_is_liuhe = False       # 變卦六合卦
        self.changed_is_liuchong = False    # 變卦六沖卦
        self.changed_lower_gua = None       # 變卦下卦名
        self.changed_upper_gua = None       # 變卦上卦名

    def line(self, pos):
        return self.lines[pos - 1]

    @property
    def moving_lines(self):
        return [l for l in self.lines if l.is_moving]

    def changed_line_info(self):
        """變卦六爻完整資訊（初..上）：[{pos,yin_yang,gan,zhi,qin,shen}]。

        納甲/六親按變卦本身排（六親仍以主卦宮為我）；六神同主卦同位置（日干起，按爻位）。
        """
        lower_gan = BAGUA_NAGAN[self.changed_lower_gua][0]
        upper_gan = BAGUA_NAGAN[self.changed_upper_gua][1]
        lower_zhi = BAGUA_NAZHI[self.changed_lower_gua][:3]
        upper_zhi = BAGUA_NAZHI[self.changed_upper_gua][3:]
        info = []
        for pos in range(1, 7):
            ln = self.line(pos)
            yy = ("陰" if ln.yin_yang == "陽" else "陽") if ln.is_moving else ln.yin_yang
            if pos <= 3:
                gan, zhi = lower_gan, lower_zhi[pos - 1]
            else:
                gan, zhi = upper_gan, upper_zhi[pos - 4]
            wx = DIZHI_WUXING[zhi]
            info.append({
                "pos": pos, "yin_yang": yy,
                "gan": gan, "zhi": zhi, "wx": wx,
                "qin": liuqin(wx, self.palace_wx),
                "shen": ln.shen,
            })
        return info


def cast_board(hexagram, moving, month_zhi, day_gz, yongshen_qin=None):
    """排盤。

    Args:
        hexagram: 卦名（全名"地澤臨"或單字"臨"）。
        moving: 動爻位置，int 或 list[int]（1..6）。
        month_zhi: 月建地支，如 "未"。
        day_gz: 日干支，如 "辛卯"（完整兩天字元）。
        yongshen_qin: 可選，用神六親名（"妻財"等），用於標註各爻角色。

    Returns:
        Board 物件。
    """
    rec = find_hexagram(hexagram)
    if rec is None:
        raise ValueError(f"未找到卦: {hexagram}")

    if isinstance(moving, int):
        moving = [moving]
    moving_set = set(moving)

    board = Board()
    board.hexagram = rec["name"]
    board.palace = rec["palace"]
    board.palace_wx = rec["palace_wx"]
    board.world_pos = rec["world"]
    board.response_pos = ((board.world_pos - 1 + 3) % 6) + 1

    board.month_zhi = month_zhi
    board.month_wx = DIZHI_WUXING[month_zhi]
    board.day_gz = day_gz
    board.day_gan = day_gz[0]
    board.day_zhi = day_gz[1]
    board.day_wx = DIZHI_WUXING[board.day_zhi]
    board.xunkong = xunkong(day_gz)
    board.yongshen_qin = yongshen_qin

    upper, lower = rec["upper"], rec["lower"]
    lower_yao = BAGUA[lower]["yao"]
    upper_yao = BAGUA[upper]["yao"]
    six_yao = lower_yao + upper_yao  # 初..上

    # 變卦（動爻陰陽翻轉）
    changed_yao = [(1 - y if (i + 1) in moving_set else y) for i, y in enumerate(six_yao)]
    changed_lower_gua = _yao_to_bagua(changed_yao[0:3])
    changed_upper_gua = _yao_to_bagua(changed_yao[3:6])
    board.changed_hexagram = _find_changed_hexagram(changed_lower_gua, changed_upper_gua)
    board.changed_lower_gua = changed_lower_gua
    board.changed_upper_gua = changed_upper_gua

    # 六神起例
    start_shen = LIUSHEN_START[board.day_gan]
    start_idx = LIUSHEN_ORDER.index(start_shen)

    # 裝每爻
    lower_gan, upper_gan = BAGUA_NAGAN[lower][0], BAGUA_NAGAN[upper][1]
    lower_zhi = BAGUA_NAZHI[lower][:3]
    upper_zhi = BAGUA_NAZHI[upper][3:]

    for pos in range(1, 7):
        ln = board.line(pos)
        idx = pos - 1
        ln.yin_yang = "陽" if six_yao[idx] == 1 else "陰"
        if pos <= 3:
            ln.gan = lower_gan
            ln.zhi = lower_zhi[idx]
        else:
            ln.gan = upper_gan
            ln.zhi = upper_zhi[idx - 3]
        ln.wx = DIZHI_WUXING[ln.zhi]
        ln.qin = liuqin(ln.wx, board.palace_wx)
        ln.shen = LIUSHEN_ORDER[(start_idx + idx) % 6]
        ln.is_world = (pos == board.world_pos)
        ln.is_response = (pos == board.response_pos)
        ln.is_moving = pos in moving_set

        # 旺衰
        ln.state = wuxing_state(ln.wx, board.month_wx)
        ln.stage = shier_changsheng(ln.wx, ln.zhi)
        ln.prosperous = is_prosperous(ln.wx, ln.zhi, board.month_zhi, board.day_zhi)

        # 空亡
        ln.void = is_void(ln.zhi, day_gz)
        ln.true_void = ln.void and is_true_void(ln.wx, board.month_zhi)
        # 月破
        ln.month_break = is_chong(board.month_zhi, ln.zhi)
        # 日沖
        ln.day_strike = is_chong(board.day_zhi, ln.zhi)
        # 臨日月建
        ln.is_on_month = (ln.zhi == board.month_zhi)
        ln.is_on_day = (ln.zhi == board.day_zhi)
        # 暗動 / 日破：靜爻被日沖，須待六爻裝完（要看動爻生助），統一於 _detect_dark_move 判定
        # 動爻被日沖（《增刪卜易·日辰章》：旺動愈動，衰動沖散）
        if ln.day_strike and ln.is_moving:
            ln.day_strike_moving = "動而愈動" if ln.prosperous else "動而沖散"

    # 動爻變爻
    ch_lower_gan, ch_upper_gan = BAGUA_NAGAN[changed_lower_gua][0], BAGUA_NAGAN[changed_upper_gua][1]
    ch_lower_zhi = BAGUA_NAZHI[changed_lower_gua][:3]
    ch_upper_zhi = BAGUA_NAZHI[changed_upper_gua][3:]

    for ln in board.moving_lines:
        p = ln.position
        if p <= 3:
            ln.change_gan = ch_lower_gan
            ln.change_zhi = ch_lower_zhi[p - 1]
        else:
            ln.change_gan = ch_upper_gan
            ln.change_zhi = ch_upper_zhi[p - 4]
        ln.change_wx = DIZHI_WUXING[ln.change_zhi]
        ln.change_qin = liuqin(ln.change_wx, board.palace_wx)

        # 化進退 / 回頭生克
        if ln.wx == ln.change_wx:
            if JINSHEN.get(ln.zhi) == ln.change_zhi:
                ln.jin_tui = "化進神"
            elif TUISHEN.get(ln.zhi) == ln.change_zhi:
                ln.jin_tui = "化退神"
            else:
                ln.jin_tui = "化比和"
        else:
            if i_sheng(ln.change_wx) == ln.wx:
                ln.jin_tui = "化回頭生"
            elif i_ke(ln.change_wx) == ln.wx:
                ln.jin_tui = "化回頭克"
            else:
                ln.jin_tui = "化他"

    # 入墓
    for ln in board.lines:
        mu = WUXING_MU[ln.wx]
        reasons = []
        if board.month_zhi == mu:
            reasons.append("月墓")
        if board.day_zhi == mu:
            reasons.append("日墓")
        for other in board.lines:
            if other.is_moving and other.zhi == mu and other.position != ln.position:
                reasons.append("動爻墓")
        if ln.is_moving and ln.change_zhi == mu:
            reasons.append("化墓")
        ln.in_grave = reasons
        # 空墓：入墓 且 墓庫地支落空亡
        if reasons and mu in board.xunkong:
            ln.grave_is_void = True

    # 暗動 / 日破（靜爻逢日沖：旺相或得動爻生助 → 暗動，否則日破）
    _detect_dark_move(board)

    # 用神四神角色 + 元神/忌神有力無力（以用神爻五行為基準）
    if yongshen_qin:
        for ln in board.lines:
            if ln.qin == yongshen_qin:
                board.yongshen_lines.append(ln)
        # 用神五行基準：取最旺者，否則取第一個
        if board.yongshen_lines:
            ys_sorted = sorted(
                board.yongshen_lines,
                key=lambda l: (l.is_on_month or l.is_on_day, l.prosperous,
                               l.state in ("旺", "相")),
                reverse=True,
            )
            yongshen_wx = ys_sorted[0].wx
        else:
            yongshen_wx = None
        board.yongshen_wx = yongshen_wx
        for ln in board.lines:
            ln.role = yongshen_role(ln.wx, yongshen_wx) if yongshen_wx else None
            if ln in board.yongshen_lines:
                ln.role = "用神"
            # 元神/忌神判有力無力
            if ln.role in ("元神", "忌神"):
                eff, reason = _spirit_effective(ln, board)
                ln.effective = eff
                ln.effective_reason = reason

    # —— 飛神伏神：本宮首卦補缺六親 ——
    _detect_fushen(board)

    # —— 卦級分析：卦變生克 / 反伏 / 三合 / 六合六沖卦 ——
    _analyze_gua_bian(board)
    _detect_fu_fan_yin(board)
    _detect_sanhe(board)
    _detect_sanhe_local(board)
    _detect_liuhe_liuchong(board, changed_lower_gua, changed_upper_gua)

    return board
