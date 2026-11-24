"""進階判定測試：四神、有力無力、真空、臨日建、卦變反伏、三合虛合。

對應 P0+P1 升級項，驗證引擎新增的判定邏輯。
"""

import pytest

from liuyao import cast_board
from liuyao.wuxing import four_gods, is_true_void, season_of, wuxing_state


# ----------------------------------------------------------------
# 旺相休囚死（《增刪卜易》：當令者旺，令所生者相，生令者休，克令者囚，令所克者死）
# ----------------------------------------------------------------
@pytest.mark.parametrize("ling,expect", [
    # 木令(春)：木旺、火相(木生火)、水休(水生木)、金囚、土死
    ("木", {"木": "旺", "火": "相", "水": "休", "金": "囚", "土": "死"}),
    # 火令(夏)：火旺、土相、木休、水囚、金死
    ("火", {"火": "旺", "土": "相", "木": "休", "水": "囚", "金": "死"}),
    # 金令(秋)：金旺、水相、土休、火囚、木死
    ("金", {"金": "旺", "水": "相", "土": "休", "火": "囚", "木": "死"}),
    # 水令(冬)：水旺、木相、金休、土囚、火死
    ("水", {"水": "旺", "木": "相", "金": "休", "土": "囚", "火": "死"}),
    # 土令(四季月)：土旺、金相(土生金)、火休(火生土)、木囚、水死 —— 與 references/03 表格一致
    ("土", {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"}),
])
def test_wuxing_state_full_table(ling, expect):
    """⭐ 相/休迴歸：五行五態全表（舊版把'令生者相/生令者休'寫反）。"""
    for yao_wx, state in expect.items():
        assert wuxing_state(yao_wx, ling) == state


def test_wuxing_state_case01_you_xiang():
    """⭐ 案例01迴歸：未月(土令)子孫酉金應為'相'(土生金)，父母巳火應為'休'(火生土)。

    舊版輸出金'休'/火'相'與 references/03 表格、案例斷言(五行金相)相反。
    且酉金仍須旺相→逢卯日沖為暗動(非日破)。
    """
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    assert b.line(6).state == "相"      # 酉金，未月土生金
    assert b.line(1).state == "休"      # 巳火，生未月土而洩
    assert b.line(5).state == "死"      # 亥水，土克水（與案例一致，非本次迴歸範圍，一併鎖住）
    assert b.line(6).dark_move is True  # 暗動判定不迴歸


# ----------------------------------------------------------------
# 四神
# ----------------------------------------------------------------
def test_four_gods_water():
    """用神=水 → 元金、忌土、仇火。"""
    assert four_gods("水") == {"用": "水", "元": "金", "忌": "土", "仇": "火"}


def test_four_gods_metal():
    """用神=金 → 元土、忌火、仇木（《增刪卜易》原例）。"""
    assert four_gods("金") == {"用": "金", "元": "土", "忌": "火", "仇": "木"}


def test_chou_shen_parent_fire():
    """⭐ 父母巳火(火) 對用神妻財水 → 仇神(克金元、生土忌)。

    舊版按六親判為'閒神'，改為五行基準後正確判為仇神。
    """
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    l1 = b.line(1)
    assert l1.qin == "父母"
    assert l1.zhi == "巳"
    assert l1.wx == "火"
    assert l1.role == "仇神"


# ----------------------------------------------------------------
# 元神忌神有力無力
# ----------------------------------------------------------------
def test_yuanshen_effective_you():
    """子孫酉金=元神，未月旺相、逢日沖暗動 → 有力(能生用)。"""
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    l6 = b.line(6)
    assert l6.role == "元神"
    assert l6.effective is True
    assert "有力" in l6.effective_reason


def test_jishen_ineffective_chou():
    """⭐ 兄弟丑土=忌神，但月破 → 無力(雖忌神卻克不到用，'雖動不克')。"""
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    l3 = b.line(3)
    assert l3.role == "忌神"
    assert l3.effective is False
    assert "月破" in l3.effective_reason


# ----------------------------------------------------------------
# 臨日建 / 真空
# ----------------------------------------------------------------
def test_world_on_day():
    """世爻卯木臨日建(卯日)。"""
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    assert b.line(2).is_on_day is True


def test_true_void_season():
    """真空季節：春土/夏金/秋木/冬火；四季月無真空。"""
    assert is_true_void("土", "寅") is True   # 春土
    assert is_true_void("金", "巳") is True   # 夏金
    assert is_true_void("木", "申") is True   # 秋木
    assert is_true_void("火", "亥") is True   # 冬火
    assert season_of("未") == "季"
    assert is_true_void("金", "未") is False  # 季月無真空


# ----------------------------------------------------------------
# 卦變生克 / 反伏
# ----------------------------------------------------------------
def test_gua_bian_bihe():
    """臨變復，同坤宮土 → 變比和(吉)。"""
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    assert "比和" in b.gua_bian


def test_fu_fan_yin_false():
    """臨變復，卯化寅，非伏非反。"""
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    assert b.fu_yin is False
    assert b.fan_yin is False


# ----------------------------------------------------------------
# 三合（虛合待用 + 暗動算動）
# ----------------------------------------------------------------
def test_sanhe_xu_he_que_wei():
    """亥卯未木局：卦中缺未(在月)，虛合待填實；動爻僅卯1。"""
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    s = b.sanhe["亥卯未木局"]
    assert "虛合" in s["status"] and "缺未" in s["status"]
    assert s["moving_count"] == 1


def test_sanhe_dark_move_counts_as_moving():
    """⭐ 巳酉丑金局：酉暗動計入動爻數(=1)；三支雖齊但動不足→虛合待用。"""
    b = cast_board("地澤臨", 2, "未", "辛卯", "妻財")
    s = b.sanhe["巳酉丑金局"]
    assert s["moving_count"] == 1          # 酉暗動算入
    assert "支齊動不足" in s["status"]


# ----------------------------------------------------------------
# 內卦／外卦三合局（位置限定的動爻＋變爻成局）
# ----------------------------------------------------------------
def test_sanhe_inner_by_moving_and_changed():
    """⭐ 天風姤 初、三同動：初丑動、初化巳、三酉動 → 巳酉丑金局（內卦三合局）。

    卦中本缺巳（原為虛合待填實），巳由初爻化出 → 升級為實成之局。
    """
    b = cast_board("天風姤", [1, 3], "子", "甲子")
    assert (b.line(1).zhi, b.line(1).change_zhi) == ("丑", "巳")
    assert (b.line(3).zhi, b.line(3).change_zhi) == ("酉", "丑")
    assert len(b.sanhe_local) == 1
    item = b.sanhe_local[0]
    assert item["type"] == "內卦三合局"
    assert item["ju"] == "巳酉丑金局"
    assert item["positions"] == [1, 3]
    assert b.sanhe["巳酉丑金局"]["status"] == "實成之局"
    assert "內卦三合局" in b.sanhe["巳酉丑金局"]["formed_by"]


def test_sanhe_outer_by_moving_and_changed():
    """⭐ 澤水困 四、上同動：四亥動、上未動、上化卯 → 亥卯未木局（外卦三合局）。"""
    b = cast_board("澤水困", [4, 6], "子", "甲子")
    assert (b.line(4).zhi, b.line(4).change_zhi) == ("亥", "未")
    assert (b.line(6).zhi, b.line(6).change_zhi) == ("未", "卯")
    assert len(b.sanhe_local) == 1
    item = b.sanhe_local[0]
    assert item["type"] == "外卦三合局"
    assert item["ju"] == "亥卯未木局"
    assert item["positions"] == [4, 6]
    assert b.sanhe["亥卯未木局"]["status"] == "實成之局"
    assert "外卦三合局" in b.sanhe["亥卯未木局"]["formed_by"]


def test_sanhe_wrong_positions_not_formed():
    """⭐ 位置不對不成局：地澤臨 二、五同動（巳酉丑三支皆在卦中）→ 無內/外卦局。"""
    b = cast_board("地澤臨", [2, 5], "未", "辛卯")
    assert b.sanhe_local == []
    assert "支齊動不足" in b.sanhe["巳酉丑金局"]["status"]


# ----------------------------------------------------------------
# 暗動：靜爻＋日沖＋（旺相 或 得動爻生助）；旺衰不看十二長生
# ----------------------------------------------------------------
def test_dark_move_by_moving_line_support():
    """⭐ 乾為天 五爻申金動：初爻子水休囚（卯月）逢午日沖，本應日破；
    得申金動而生之 → 暗動（被動爻生助）。"""
    b = cast_board("乾為天", 5, "卯", "甲午")
    l1 = b.line(1)
    assert l1.zhi == "子"
    assert l1.day_strike is True
    assert l1.prosperous is False         # 卯月水休；自坐帝旺已不參旺衰
    assert l1.dark_move is True
    assert l1.day_break is False
    assert l1.dark_move_reason == "得動爻生助"
    assert "動爻生助" in l1.label()


def test_day_break_without_support():
    """⭐ 同盤無動爻：初爻子水休囚逢日沖、無動爻生助 → 日破。"""
    b = cast_board("乾為天", [], "卯", "甲午")
    l1 = b.line(1)
    assert l1.prosperous is False
    assert l1.dark_move is False
    assert l1.day_break is True


def test_moving_line_struck_is_not_dark_move():
    """⭐ 動爻被日沖不判暗動：乾為天 初爻動、午日沖子 → 動而沖散。"""
    b = cast_board("乾為天", 1, "卯", "甲午")
    l1 = b.line(1)
    assert l1.is_moving is True
    assert l1.day_strike is True
    assert l1.dark_move is False
    assert l1.day_break is False
    assert l1.day_strike_moving == "動而沖散"
