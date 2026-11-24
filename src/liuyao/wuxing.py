"""五行工具：生克關係、六親推演、旺衰判定、十二長生、旬空、暗動/日破判定。"""

from .data import (
    DIZHI, DIZHI_WUXING, WUXING_SHENG, WUXING_KE, WUXING_MU,
    SHIER_CHANGSHENG_START, SHIER_NAMES, SHIER_WEAK,
    TIANGAN, XUNKONG_BY_XUN, CHONG,
)


# ----------------------------------------------------------------
# 基本關係
# ----------------------------------------------------------------
def sheng_me(wx):
    """生我者的五行（誰生 wx）。"""
    for k, v in WUXING_SHENG.items():
        if v == wx:
            return k
    return None


def ke_me(wx):
    """克我者的五行（誰克 wx）。"""
    for k, v in WUXING_KE.items():
        if v == wx:
            return k
    return None


def i_sheng(wx):
    """我生者。"""
    return WUXING_SHENG[wx]


def i_ke(wx):
    """我克者。"""
    return WUXING_KE[wx]


# ----------------------------------------------------------------
# 六親
# ----------------------------------------------------------------
def liuqin(yao_wx, palace_wx):
    """根據爻五行與本宮五行，返回六親。

    以本宮五行為'我'：
        生我者 = 父母；我生者 = 子孫；克我者 = 官鬼；我克者 = 妻財；同我 = 兄弟。
    """
    if yao_wx == palace_wx:
        return "兄弟"
    if sheng_me(palace_wx) == yao_wx:   # yao 生 palace → 生我者 = 父母
        return "父母"
    if i_sheng(palace_wx) == yao_wx:    # palace 生 yao → 我生者 = 子孫
        return "子孫"
    if ke_me(palace_wx) == yao_wx:      # yao 克 palace → 克我者 = 官鬼
        return "官鬼"
    if i_ke(palace_wx) == yao_wx:       # palace 克 yao → 我克者 = 妻財
        return "妻財"
    return "兄弟"


def four_gods(yongshen_wx):
    """以用神五行為基準，返回四神的五行。

    用=本身；元=生用者(sheng_me)；忌=克用者(ke_me)；仇=克元者(=生忌者)。
    例：用=金 → 元=土, 忌=火, 仇=木(克土生火)。
    """
    yuan = sheng_me(yongshen_wx)
    ji = ke_me(yongshen_wx)
    chou = ke_me(yuan)  # 克元神者；亦 = sheng_me(ji) 生忌神者
    return {"用": yongshen_wx, "元": yuan, "忌": ji, "仇": chou}


def yongshen_role(yao_wx, yongshen_wx):
    """該爻(按五行)相對用神爻(按五行)的四神角色：用/元/忌/仇/閒。

    注意：以【用神爻的五行】為基準（非六親），這才符合"元生用、忌克用、仇克元生忌"的定義。
    """
    if yao_wx == yongshen_wx:
        return "用神"
    g = four_gods(yongshen_wx)
    if yao_wx == g["元"]:
        return "元神"
    if yao_wx == g["忌"]:
        return "忌神"
    if yao_wx == g["仇"]:
        return "仇神"
    return "閒神"


# ----------------------------------------------------------------
# 真空（旬空 + 當令死地）
# ----------------------------------------------------------------
# 真空：春土、夏金、秋木、冬火（《增刪卜易·旬空章》）
_TRUE_VOID = {
    "春": "土", "夏": "金", "秋": "木", "冬": "火",
}


def season_of(month_zhi):
    """月支 → 季節。四季月(辰戌丑未)返回 '季'（土當令，無真空）。"""
    if month_zhi in ("寅", "卯"):
        return "春"
    if month_zhi in ("巳", "午"):
        return "夏"
    if month_zhi in ("申", "酉"):
        return "秋"
    if month_zhi in ("亥", "子"):
        return "冬"
    return "季"  # 辰戌丑未


def is_true_void(yao_wx, month_zhi):
    """爻是否為'真空'：落旬空且其五行恰為當季真空之五行。須配合 is_void 使用。"""
    season = season_of(month_zhi)
    return _TRUE_VOID.get(season) == yao_wx


# ----------------------------------------------------------------
# 旺相休囚死（按月令當令五行）
# ----------------------------------------------------------------
def wuxing_state(yao_wx, ling_wx):
    """爻五行在當令五行(月令)下的狀態：旺/相/休/囚/死。

    當令者旺，令所生者相(次旺)，生令者休(洩氣)，克令者囚，令所克者死。
    例：未月土令 → 土旺、金相(土生金)、火休(火生土)、木囚、水死。
    """
    if yao_wx == ling_wx:
        return "旺"
    if i_sheng(ling_wx) == yao_wx:    # 令生者 = 相（當令所生，次旺）
        return "相"
    if sheng_me(ling_wx) == yao_wx:   # 生令者 = 休（生當令而洩氣）
        return "休"
    if ke_me(ling_wx) == yao_wx:      # 克令者 = 囚
        return "囚"
    if i_ke(ling_wx) == yao_wx:       # 令克者 = 死
        return "死"
    return "休"


# ----------------------------------------------------------------
# 十二長生
# ----------------------------------------------------------------
def shier_changsheng(yao_wx, dz):
    """爻五行(以地支 dz 代表位置)在十二長生中的階段名。返回階段名或 None。"""
    start = SHIER_CHANGSHENG_START.get(yao_wx)
    if start is None:
        return None
    start_idx = DIZHI.index(start)
    dz_idx = DIZHI.index(dz)
    # 地支順行：(dz_idx - start_idx) % 12 為步數
    step = (dz_idx - start_idx) % 12
    return SHIER_NAMES[step]


# ----------------------------------------------------------------
# 爻的旺衰判定（用於暗動/日破、用神有力無力）
# ----------------------------------------------------------------
def is_prosperous(yao_wx, yao_dz, month_dz, day_dz):
    """判斷爻是否旺相。

    只看月令旺相休囚死與月日生扶比和：旺相、得月日生、得月日比和 → 旺相。
    十二長生**不參旺衰判定**（yao_dz 僅為呼叫端相容而保留，未使用）。
    """
    month_wx = DIZHI_WUXING[month_dz]
    day_wx = DIZHI_WUXING[day_dz]

    # 1. 月令旺相
    st = wuxing_state(yao_wx, month_wx)
    if st in ("旺", "相"):
        return True
    # 2. 月生日、日生日（生扶）
    if i_sheng(month_wx) == yao_wx or i_sheng(day_wx) == yao_wx:
        return True
    # 3. 月比和、日比和
    if month_wx == yao_wx or day_wx == yao_wx:
        return True
    return False


# ----------------------------------------------------------------
# 旬空
# ----------------------------------------------------------------
def ganzhi_index(gan, zhi):
    """六十甲子序號 0..59。"""
    gi = TIANGAN.index(gan)
    zi = DIZHI.index(zhi)
    n = gi
    while n % 12 != zi:
        n += 10
    return n  # 必在 0..59


def xunkong(day_gz):
    """由日干支(如 '辛卯')查旬空，返回兩個空亡地支的元組。"""
    g, z = day_gz[0], day_gz[1]
    n = ganzhi_index(g, z)
    return XUNKONG_BY_XUN[n // 10]


def is_void(yao_dz, day_gz):
    """爻地支是否落空亡。"""
    return yao_dz in xunkong(day_gz)


# ----------------------------------------------------------------
# 沖
# ----------------------------------------------------------------
def is_chong(a, b):
    return CHONG.get(a) == b
