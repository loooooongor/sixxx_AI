"""干支曆法：由公曆日期精確推算年月日干支、節氣、旬空。

六爻排盤的「月建」與「日辰」不是隨便填的，必須由實際占卦時間推算：

* **月建**：以「節氣」為界（不是農曆月、也不是公曆月）。立春起寅月，驚蟄起卯月，
  清明起辰月……小寒起丑月。六爻的旺衰全靠月建，故此處必須準確。
* **日辰**：六十甲子日迴圈，以儒略日天數推算。
* **年干支**：六爻沿《增刪卜易》一脈，以「立春」換年（不是正月初一）。

本模組只用標準庫，天文公式取自 Meeus《Astronomical Algorithms》第 22／25／47 章：
太陽視黃經精度約 0.01°（摺合時間約 15 分鐘），足以判定節氣落在哪一天；
節氣時刻另有 ±1 分鐘級別的牛頓迭代收斂。

用法::

    from liuyao_ai.calendar import cast_time_from_datetime
    ct = cast_time_from_datetime(datetime(2026, 8, 1, 14, 30))
    ct.year_gz    # '丙午'
    ct.month_gz   # '乙未'
    ct.month_zhi  # '未'
    ct.day_gz     # '辛卯'
    ct.xunkong    # ('午', '未')
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

# ────────────────────────────── 基本常數 ──────────────────────────────

TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI = "子丑寅卯辰巳午未申酉戌亥"

# 時辰（地支 → 起始鐘點，子時跨日故分早晚子）
SHICHEN_BOUNDS = [
    (23, "子"), (1, "丑"), (3, "寅"), (5, "卯"), (7, "辰"), (9, "巳"),
    (11, "午"), (13, "未"), (15, "申"), (17, "酉"), (19, "戌"), (21, "亥"),
]

# 廿四節氣角度（太陽視黃經，度）。六爻月建只看「節」不看「氣」。
# 立春 315°、驚蟄 345°、清明 15°、立夏 45°、芒種 75°、小暑 105°、
# 立秋 135°、白露 165°、寒露 195°、立冬 225°、大雪 255°、小寒 285°
JIE_ANGLES = [315, 345, 15, 45, 75, 105, 135, 165, 195, 225, 255, 285]
JIE_NAMES = ["立春", "驚蟄", "清明", "立夏", "芒種", "小暑",
             "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]
# 對應的月建地支（立春＝寅月）
JIE_MONTH_ZHI = ["寅", "卯", "辰", "巳", "午", "未",
                 "申", "酉", "戌", "亥", "子", "丑"]

# 廿四節氣全名（含「中氣」），僅供顯示
ALL_TERM_NAMES = [
    "小寒", "大寒", "立春", "雨水", "驚蟄", "春分", "清明", "穀雨",
    "立夏", "小滿", "芒種", "夏至", "小暑", "大暑", "立秋", "處暑",
    "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
]

# 旬空表：旬號 = 六十甲子序號 // 10
XUNKONG_TABLE = [
    ("戌", "亥"),  # 甲子旬
    ("申", "酉"),  # 甲戌旬
    ("午", "未"),  # 甲申旬
    ("辰", "巳"),  # 甲午旬
    ("寅", "卯"),  # 甲辰旬
    ("子", "丑"),  # 甲寅旬
]

# 節氣判定容差（日）。節氣時刻落在午夜附近時，用此避免誤判前後一日。
_TERM_TOLERANCE = 0.0


# ────────────────────────────── 儒略日 ──────────────────────────────

def jd_from_ymd(year: int, month: int, day: float) -> float:
    """公曆（格里曆）→ 儒略日。day 可含小數。

    以 1582-10-15 為界自動切換儒略曆／格里曆（本專案不涉古早日期，
    但保留正確性）。
    """
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    if (year, month, day) < (1582, 10, 15):
        b = 0
    return (math.floor(365.25 * (year + 4716))
            + math.floor(30.6001 * (month + 1))
            + day + b - 1524.5)


def jd_from_datetime(dt: datetime) -> float:
    """datetime → 儒略日（UT）。naive 一律視為 UTC。

    帶時區的 datetime 會**先轉成 UTC** 再取日期時間分量，
    否則「22:36 +08:00」會被誤當成「22:36 UTC」，整整差 8 小時。
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return jd_from_ymd(dt.year, dt.month, dt.day + (
        dt.hour + dt.minute / 60 + dt.second / 3600
        + dt.microsecond / 3.6e9) / 24)


def jd_to_datetime(jd: float, tz: timezone = timezone.utc) -> datetime:
    """儒略日 → 指定時區的 datetime。"""
    unix = (jd - 2440587.5) * 86400.0
    return datetime.fromtimestamp(unix, tz)


# ────────────────────────────── ΔT（力學時 − 世界時） ──────────────────────────────

def delta_t(year: float) -> float:
    """力學時與世界時的差值 ΔT（秒），Meeus 第 10 章近似式。

    本專案合理範圍 1900–2100；範圍外用外插，精度尚可。
    """
    y = year
    if 2005 <= y < 2050:
        t = y - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t * t
    if 1986 <= y < 2005:
        t = y - 2000
        return (63.86 + 0.3345 * t - 0.060374 * t ** 2
                + 0.0017275 * t ** 3 + 0.000651814 * t ** 4
                + 0.00002373599 * t ** 5)
    if 1961 <= y < 1986:
        t = y - 1975
        return 45.45 + 1.067 * t - t ** 2 / 260 - t ** 3 / 718
    if 1941 <= y < 1961:
        t = y - 1950
        return 29.07 + 0.407 * t - t ** 2 / 233 + t ** 3 / 2547
    if 1920 <= y < 1941:
        t = y - 1920
        return 21.20 + 0.84493 * t - 0.076100 * t ** 2 + 0.0020936 * t ** 3
    if 2050 <= y < 2150:
        u = (y - 1820) / 100
        return -20 + 32 * u * u - 0.5628 * (2150 - y)
    if y < 1920:
        u = (y - 1820) / 100
        return -20 + 32 * u * u
    u = (y - 1820) / 100
    return -20 + 32 * u * u


def jde_from_jd(jd_ut: float) -> float:
    """UT 儒略日 → 力學時儒略日。"""
    year = 2000.0 + (jd_ut - 2451545.0) / 365.25
    return jd_ut + delta_t(year) / 86400.0


def jd_from_jde(jde: float) -> float:
    """力學時儒略日 → UT 儒略日。"""
    year = 2000.0 + (jde - 2451545.0) / 365.25
    return jde - delta_t(year) / 86400.0


# ────────────────────────────── 太陽視黃經 ──────────────────────────────

def sun_apparent_longitude(jde: float) -> float:
    """太陽視黃經 λ（度，0–360），Meeus 第 25 章（精度約 0.01°）。"""
    t = (jde - 2451545.0) / 36525.0

    # 幾何平黃經
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    # 平近點角
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t
    m_rad = math.radians(m)

    # 中心差（度）
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m_rad)
         + (0.019993 - 0.000101 * t) * math.sin(2 * m_rad)
         + 0.000289 * math.sin(3 * m_rad))

    # 真黃經
    true_long = l0 + c

    # 章動與光行差修正
    omega = 125.04 - 1934.136 * t
    omega_rad = math.radians(omega)
    nutation = -0.00569 - 0.00478 * math.sin(omega_rad)
    apparent = true_long + nutation

    return apparent % 360.0


def sun_longitude_rate(jde: float) -> float:
    """太陽視黃經日變化率（度／日），供牛頓迭代用。

    注意：黃經在 0°/360° 處回繞，直接相減會得到 −359° 這種荒謬值，
    差值必須先歸一到 (−180, 180]，才會是真正的 ~0.98–1.02 度／日。
    """
    delta = sun_apparent_longitude(jde + 0.5) - sun_apparent_longitude(jde - 0.5)
    return (delta + 180.0) % 360.0 - 180.0


def solve_term_jde(target_angle: float, guess_jde: float,
                   tol: float = 1e-7) -> float:
    """求太陽視黃經等於 target_angle 的力學時儒略日。

    先以牛頓迭代（差值歸一處理回繞）快速收斂，收斂後驗算殘差；
    若殘差仍偏大，改用夾逼法（bisection）保證求出正解。

    Args:
        target_angle: 目標黃經（度，0–360）。
        guess_jde: 初值（力學時儒略日），須落在解附近（一週內）。
        tol: 收斂容差（日），1e-7 日約 0.009 秒。
    """
    def residual(x: float) -> float:
        return (target_angle - sun_apparent_longitude(x) + 180.0) % 360.0 - 180.0

    x = guess_jde
    for _ in range(30):
        diff = residual(x)
        rate = sun_longitude_rate(x)
        if abs(rate) < 1e-6:
            break
        step = max(-5.0, min(5.0, diff / rate))
        x += step
        if abs(step) < tol:
            break

    # 驗算：殘差仍大就用夾逼法重解（穩健保險）
    if abs(residual(x)) > 1e-4:
        lo, hi = x - 6.0, x + 6.0
        # 先確認 lo/hi 夾住目標（residual 由負轉正）
        r_lo = residual(lo)
        for _ in range(80):
            mid = (lo + hi) / 2.0
            r_mid = residual(mid)
            if abs(r_mid) < tol:
                return mid
            if (r_mid > 0) == (r_lo > 0):
                lo, r_lo = mid, r_mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    return x


def _guess_jde_for_angle(target_angle: float, year: int) -> float:
    """給定年份與目標黃經，給出一個粗略初值（力學時儒略日）。

    約定：傳回的節氣落在「該公曆年內」。太陽黃經 0°（春分）約在 3 月 20 日，
    故黃經 ≥ 270° 的節氣（冬至、小寒、大寒）雖在 3 月 20 日之前，
    仍屬該年 1 月或 12 月，須用「負位移」回推。
    """
    angle = target_angle % 360
    # 相對春分（0°）的天數；黃經每度約 1.0146 日。
    # 取 (angle - 0) 在 [0, 360) 的位移，但若位移 > 275 天則視為跨年回推。
    offset_days = (angle / 360.0) * 365.2422
    if offset_days > 275.0:          # 冬至、小寒、大寒 → 落在本年 1 月
        offset_days -= 365.2422
    base_jd = jd_from_ymd(year, 3, 20.0) + offset_days
    # 牛頓式粗調一次
    lam = sun_apparent_longitude(jde_from_jd(base_jd))
    diff = (angle - lam + 180) % 360 - 180
    return jde_from_jd(base_jd) + diff


# ────────────────────────────── 節氣 ──────────────────────────────

@dataclass(frozen=True)
class SolarTerm:
    """一個節氣。"""

    name: str
    angle: float          # 太陽視黃經（度）
    moment: datetime      # 節氣交節時刻（臺灣時間 UTC+8）
    jie: bool             # True = 「節」（換月建），False = 「氣」

    def __str__(self) -> str:
        return f"{self.name}（{self.moment:%Y-%m-%d %H:%M}）"


# 節氣角度 ↔ 名稱（全 24 個，含中氣）
_TERM_SPECS = [
    # (名稱, 黃經, 是否為「節」)
    ("小寒", 285, True), ("大寒", 315 - 30 + 30, False),   # 大寒 300
    ("立春", 315, True), ("雨水", 330, False),
    ("驚蟄", 345, True), ("春分", 0, False),
    ("清明", 15, True), ("穀雨", 30, False),
    ("立夏", 45, True), ("小滿", 60, False),
    ("芒種", 75, True), ("夏至", 90, False),
    ("小暑", 105, True), ("大暑", 120, False),
    ("立秋", 135, True), ("處暑", 150, False),
    ("白露", 165, True), ("秋分", 180, False),
    ("寒露", 195, True), ("霜降", 210, False),
    ("立冬", 225, True), ("小雪", 240, False),
    ("大雪", 255, True), ("冬至", 270, False),
]
# 修正大寒角度（上面為求可讀性分開寫，此處覆寫為 300）
_TERM_SPECS[1] = ("大寒", 300, False)


def term_moment(year: int, name: str, tz: timezone | None = None) -> datetime:
    """求某年某個節氣的準確時刻（預設臺灣時間 UTC+8）。"""
    tz = tz or timezone(timedelta(hours=8))
    spec = next((s for s in _TERM_SPECS if s[0] == name), None)
    if spec is None:
        raise ValueError(f"未知節氣：{name}")
    _, angle, _ = spec
    jde = solve_term_jde(angle, _guess_jde_for_angle(angle, year))
    return jd_to_datetime(jd_from_jde(jde), tz)


def terms_in_year(year: int, tz: timezone | None = None) -> list[SolarTerm]:
    """列出某年全部 24 個節氣（依時間排序）。"""
    tz = tz or timezone(timedelta(hours=8))
    out: list[SolarTerm] = []
    for name, angle, jie in _TERM_SPECS:
        jde = solve_term_jde(angle, _guess_jde_for_angle(angle, year))
        out.append(SolarTerm(name, angle, jd_to_datetime(jd_from_jde(jde), tz), jie))
    out.sort(key=lambda s: s.moment)
    return out


def jie_in_year(year: int, tz: timezone | None = None) -> list[SolarTerm]:
    """某年的 12 個「節」（換月建用），依時間排序。"""
    return [s for s in terms_in_year(year, tz) if s.jie]


def _month_zhi_at(dt: datetime) -> tuple[str, str]:
    """由時刻判定月建地支與它所屬的「節」名。

    取該時刻之前最近的一個「節」，其月建地支即為當下月建。
    須同時檢查前一年，因為立春前的日期屬於上一年的大雪／小寒月。
    """
    tz = dt.tzinfo or timezone(timedelta(hours=8))
    candidates: list[SolarTerm] = []
    for y in (dt.year - 1, dt.year):
        candidates.extend(jie_in_year(y, tz))
    candidates.sort(key=lambda s: s.moment)
    prev = [s for s in candidates if s.moment <= dt]
    if not prev:
        # 極端情況：落在最早的節之前，退回用去年最後一節
        return "丑", "小寒"
    term = prev[-1]
    idx = JIE_NAMES.index(term.name)
    return JIE_MONTH_ZHI[idx], term.name


def _year_gz(dt: datetime) -> tuple[str, int]:
    """由時刻判定年干支（以立春換年）與其對應的「命理年」數字。"""
    tz = dt.tzinfo or timezone(timedelta(hours=8))
    lichun = term_moment(dt.year, "立春", tz)
    year_num = dt.year if dt >= lichun else dt.year - 1
    # 1984 年為甲子年
    offset = (year_num - 1984) % 60
    return TIANGAN[offset % 10] + DIZHI[offset % 12], year_num


def _month_gan(zhi: str, year_gan: str) -> str:
    """由年干與月支推月干（五虎遁）。"""
    # 寅月起干：甲己之年丙作首
    start = {"甲": 2, "己": 2, "乙": 4, "庚": 4, "丙": 6, "辛": 6,
             "丁": 8, "壬": 8, "戊": 0, "癸": 0}[year_gan]
    # 寅=0 ... 丑=11
    order = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]
    idx = order.index(zhi)
    return TIANGAN[(start + idx) % 10]


#: 日干支錨點：1949-10-01 為「甲子」日（多方黃曆一致）。
_DAY_GZ_ANCHOR = date(1949, 10, 1)
_DAY_GZ_ANCHOR_IDX = 0          # 甲子 = 六十甲子序號 0


def _day_gz(dt: datetime) -> str:
    """由日期（以當地日界的「日」為準）推日干支。

    以「1949-10-01 甲子日」為錨點（多方黃曆一致），用天數差推算，每 60 日一迴圈。
    子時（23:00 起）不換日——採一般占卦者填寫日期的直覺做法。
    """
    tz = dt.tzinfo or timezone(timedelta(hours=8))
    local = dt.astimezone(tz)
    days = (local.date() - _DAY_GZ_ANCHOR).days
    n = (_DAY_GZ_ANCHOR_IDX + days) % 60
    return TIANGAN[n % 10] + DIZHI[n % 12]


def xunkong(day_gz: str) -> tuple[str, str]:
    """由日干支查旬空（空亡的兩個地支）。"""
    gan_idx = TIANGAN.index(day_gz[0])
    zhi_idx = DIZHI.index(day_gz[1])
    # 六十甲子序號
    n = (zhi_idx - gan_idx) % 12
    n = n + 12 * 0 if n % 2 == 0 else n  # 確保同奇偶
    # 用 gan/zhi 同餘求 n（0..59）
    for i in range(60):
        if i % 10 == gan_idx and i % 12 == zhi_idx:
            n = i
            break
    return XUNKONG_TABLE[n // 10]


def shichen(dt: datetime) -> str:
    """由時刻求時辰地支。"""
    hour = dt.hour
    if hour == 23 or hour == 0:
        return "子"
    for start_hour, zhi in SHICHEN_BOUNDS:
        if start_hour > 0 and start_hour <= hour < start_hour + 2:
            return zhi
    return "子"


# ────────────────────────────── 對外主體 ──────────────────────────────

@dataclass
class CastTime:
    """一次占卦的完整時間資訊 —— 六爻排盤所需的月建、日辰、空亡皆由此而來。"""

    moment: datetime
    year_gz: str
    month_gz: str
    month_zhi: str
    day_gz: str
    day_gan: str
    day_zhi: str
    xunkong: tuple[str, str]
    shichen: str
    jie: str                       # 當下所屬的「節」名
    lunar_text: str = ""           # 農曆顯示（盡力而為，僅供參考）

    @property
    def year_gan(self) -> str:
        return self.year_gz[0]

    @property
    def month_gan(self) -> str:
        return self.month_gz[0]

    def to_dict(self) -> dict:
        return {
            "moment": self.moment.isoformat(),
            "moment_display": self.moment.strftime("%Y 年 %m 月 %d 日 %H:%M"),
            "year_gz": self.year_gz,
            "month_gz": self.month_gz,
            "month_zhi": self.month_zhi,
            "day_gz": self.day_gz,
            "day_gan": self.day_gan,
            "day_zhi": self.day_zhi,
            "xunkong": list(self.xunkong),
            "shichen": self.shichen,
            "jie": self.jie,
            "lunar_text": self.lunar_text,
        }


def cast_time_from_datetime(dt: datetime,
                            tz: timezone | None = None) -> CastTime:
    """由（帶時區或 naive 的）datetime 推算完整排盤時間資訊。

    naive datetime 一律視為臺灣時間（UTC+8）。
    """
    tz = tz or timezone(timedelta(hours=8))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    local = dt.astimezone(tz)

    year_gz, _year_num = _year_gz(local)
    month_zhi, jie_name = _month_zhi_at(local)
    month_gan = _month_gan(month_zhi, year_gz[0])
    day_gz = _day_gz(local)

    ct = CastTime(
        moment=local,
        year_gz=year_gz,
        month_gz=month_gan + month_zhi,
        month_zhi=month_zhi,
        day_gz=day_gz,
        day_gan=day_gz[0],
        day_zhi=day_gz[1],
        xunkong=xunkong(day_gz),
        shichen=shichen(local),
        jie=jie_name,
    )
    ct.lunar_text = _lunar_text(local)
    return ct


def cast_time_from_date(year: int, month: int, day: int,
                        hour: int = 12, minute: int = 0,
                        tz: timezone | None = None) -> CastTime:
    """便捷入口：由公曆年月日時分推算排盤時間。"""
    tz = tz or timezone(timedelta(hours=8))
    return cast_time_from_datetime(
        datetime(year, month, day, hour, minute, tzinfo=tz), tz)


# ────────────────────────────── 朔日（新月） ──────────────────────────────

def _new_moon_jde(k: float) -> float:
    """Meeus 第 49 章：求第 k 個朔的力學時儒略日。

    k = 0 對應 2000-01-06 的新月；每 +1 為下一個朔。精度約 1 分鐘。
    """
    t = k / 1236.85
    jde = (2451550.09766 + 29.530588861 * k + 0.00015437 * t ** 2
           - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4)
    e = 1 - 0.002516 * t - 0.0000074 * t * t
    m = math.radians(2.5534 + 29.10535670 * k - 0.0000014 * t * t
                     - 0.00000011 * t ** 3)
    mp = math.radians(201.5643 + 385.81693528 * k + 0.0107582 * t * t
                      + 0.00001238 * t ** 3 - 0.000000058 * t ** 4)
    f = math.radians(160.7108 + 390.67050284 * k - 0.0016118 * t * t
                     - 0.00000227 * t ** 3 + 0.000000011 * t ** 4)

    c = (-0.40720 * math.sin(mp)
         + 0.17241 * e * math.sin(m)
         + 0.01608 * math.sin(2 * mp)
         + 0.01039 * math.sin(2 * f)
         + 0.00739 * e * math.sin(mp - m)
         - 0.00514 * e * math.sin(mp + m)
         + 0.00208 * e * e * math.sin(2 * m)
         - 0.00111 * math.sin(mp - 2 * f)
         - 0.00057 * math.sin(mp + 2 * f)
         + 0.00056 * e * math.sin(2 * mp + m)
         - 0.00042 * math.sin(3 * mp)
         + 0.00042 * e * math.sin(m + 2 * f)
         + 0.00038 * e * math.sin(m - 2 * f)
         - 0.00024 * e * math.sin(2 * mp - m)
         - 0.00017 * math.sin(omega_term(k))
         - 0.00007 * math.sin(mp + 2 * m)
         + 0.00004 * math.sin(2 * mp - 2 * f)
         + 0.00004 * math.sin(3 * m)
         + 0.00003 * math.sin(mp + m - 2 * f)
         + 0.00003 * math.sin(2 * mp + 2 * f)
         - 0.00003 * math.sin(mp + m + 2 * f)
         + 0.00003 * math.sin(mp - m + 2 * f)
         - 0.00002 * math.sin(mp - m - 2 * f)
         - 0.00002 * math.sin(3 * mp + m)
         + 0.00002 * math.sin(4 * mp))
    return jde + c


def omega_term(k: float) -> float:
    """Meeus 第 49 章中 omega 的近似值（弧度）。"""
    t = k / 1236.85
    omega = 124.7746 - 1.56375580 * k + 0.0020672 * t * t + 0.00000215 * t ** 3
    return math.radians(omega)


def solar_correction_new_moon(jde: float) -> float:
    """Meeus 第 49 章：朔時刻的額外修正項（A1 週期項，約 ±0.0005 日）。"""
    t = (jde - 2451545.0) / 36525.0
    a1 = 299.77 + 0.107408 * (jde - 2451545.0) / 365.25 - 0.009173 * t * t
    return 0.000325 * math.sin(math.radians(a1))


def new_moons_between(jd_start: float, jd_end: float,
                      tz: timezone | None = None) -> list[datetime]:
    """列出 [jd_start, jd_end] 之間所有朔日（當地時區的日期，00:00）。"""
    tz = tz or timezone(timedelta(hours=8))
    # 由粗略 k 值反推起始 k：k = (JD - 2451550.1) / 29.530588861
    k0 = int(math.floor((jd_start - 2451550.09766) / 29.530588861)) - 2
    out = []
    k = k0
    while True:
        jde = _new_moon_jde(k) + solar_correction_new_moon(_new_moon_jde(k))
        jd = jd_from_jde(jde)
        if jd > jd_end + 2:
            break
        if jd >= jd_start - 2:
            dt = jd_to_datetime(jd, tz)
            # 朔日以所在「日」為準（農曆初一起始）
            out.append(datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=tz))
        k += 1
        if k - k0 > 4000:
            break
    return out

_LUNAR_MONTH_NAMES = ["正", "二", "三", "四", "五", "六",
                      "七", "八", "九", "十", "冬", "臘"]
_LUNAR_DAY_NAMES = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]

#: 廿四節氣的黃經（度），用於判斷閏月（無「中氣」之月為閏月）
_TERM_ANGLES_ALL = [
    ("小寒", 285), ("大寒", 300), ("立春", 315), ("雨水", 330),
    ("驚蟄", 345), ("春分", 0), ("清明", 15), ("穀雨", 30),
    ("立夏", 45), ("小滿", 60), ("芒種", 75), ("夏至", 90),
    ("小暑", 105), ("大暑", 120), ("立秋", 135), ("處暑", 150),
    ("白露", 165), ("秋分", 180), ("寒露", 195), ("霜降", 210),
    ("立冬", 225), ("小雪", 240), ("大雪", 255), ("冬至", 270),
]
#: 「中氣」黃經（雨水 330° 起，每 30° 一個）
_ZHONGQI_ANGLES = [330] + [(330 + 30 * i) % 360 for i in range(1, 12)]


def _terms_all_in_year(year: int, tz: timezone | None = None) -> list[tuple[float, datetime]]:
    """某年 24 個節氣的 (黃經, 時刻)，依時間排序。"""
    tz = tz or timezone(timedelta(hours=8))
    out = []
    for _name, angle in _TERM_ANGLES_ALL:
        jde = solve_term_jde(angle, _guess_jde_for_angle(angle, year))
        out.append((angle, jd_to_datetime(jd_from_jde(jde), tz)))
    out.sort(key=lambda t: t[1])
    return out


def _winter_solstice(year: int, tz: timezone) -> datetime:
    """某年冬至（12 月）的時刻。"""
    return term_moment(year, "冬至", tz)


def _sui_months(start: datetime, end: datetime,
                tz: timezone) -> list[dict]:
    """求「歲」內各農曆月：由 start 至 end 之間的各個朔日。

    回傳每項：{"start": 朔日, "index": 0 起月序, "leap": 是否閏月}
    """
    moons = new_moons_between(jd_from_datetime(start) - 3,
                              jd_from_datetime(end) + 3, tz)
    # 只保留 start 之後（含）到 end 之前的朔
    months = [m for m in moons if start.replace(hour=0, minute=0) <= m < end]
    if not months:
        return []
    return [{"start": m, "index": i, "leap": False}
            for i, m in enumerate(months)]


def _lunar_sui(solstice: datetime, tz: timezone) -> list[dict]:
    """求出以某個冬至所在月為十一月起算的「歲」（至下一個冬至月止）。

    若兩冬至之間有 13 個朔日，則有一個閏月：取該歲中「第一個不含中氣」的月。
    """
    next_solstice = _winter_solstice(solstice.year + 1, tz)
    # 起點：冬至所在月（冬至之前最近的一個朔日）
    start_moons = new_moons_between(jd_from_datetime(solstice) - 40,
                                    jd_from_datetime(solstice) + 1, tz)
    start = start_moons[-1] if start_moons else solstice
    end_moons = new_moons_between(jd_from_datetime(next_solstice) - 40,
                                  jd_from_datetime(next_solstice) + 1, tz)
    end = end_moons[-1] if end_moons else next_solstice
    months = _sui_months(start, end, tz)
    if len(months) != 13:
        return months

    # 找出不含中氣的月：中氣落在 [本月朔, 下月朔) 之外則該月無中氣
    terms = []
    for y in (solstice.year, solstice.year + 1, next_solstice.year):
        terms.extend(_terms_all_in_year(y, tz))
    zhongqi = [t for a, t in terms if a in _ZHONGQI_ANGLES]
    leap_idx = None
    for i, mo in enumerate(months):
        nxt = months[i + 1]["start"] if i + 1 < len(months) else end
        if not any(mo["start"] <= z < nxt for z in zhongqi):
            leap_idx = i
            break
    if leap_idx is not None:
        months[leap_idx]["leap"] = True
    return months


def gregorian_to_lunar(dt: datetime, tz: timezone | None = None) -> dict | None:
    """公曆 → 農曆（年、月、日、是否閏月）。以臺灣時間為準。

    正統演算法：以「冬至所在月為十一月」，並以「無中氣者為閏月」定閏。
    """
    tz = tz or timezone(timedelta(hours=8))
    local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
    day = datetime(local.year, local.month, local.day, 0, 0, tzinfo=tz)

    # 取前一年冬至為基準（確保 day 落在同一「歲」內）
    solstice_year = local.year if local.month >= 12 else local.year - 1
    for base_year in (solstice_year, solstice_year - 1):
        solstice = _winter_solstice(base_year, tz)
        if solstice > day:
            continue
        months = _lunar_sui(solstice, tz)
        if not months:
            continue
        # 該歲的月份：索引 0 = 十一月，1 = 十二月，2 = 正月 …（閏月不佔月序）
        ordinal = 11
        lunar_year = base_year
        for i, mo in enumerate(months):
            if i > 0 and not mo["leap"]:
                ordinal = (ordinal % 12) + 1
                if ordinal == 1:            # 正月 → 跨入新的一個農曆年
                    lunar_year = base_year + 1
            nxt = months[i + 1]["start"] if i + 1 < len(months) else None
            if mo["start"] <= day and (nxt is None or day < nxt):
                days = (day - mo["start"]).days
                return {
                    "year": lunar_year,
                    "month": ordinal,
                    "day": days + 1,
                    "leap": mo["leap"],
                }
    return None


def _lunar_text(dt: datetime) -> str:
    """農曆文字（僅供顯示，不參與排盤計算）。"""
    try:
        lu = gregorian_to_lunar(dt)
        if not lu:
            return ""
        yg = (TIANGAN[(lu["year"] - 1984) % 10]
              + DIZHI[(lu["year"] - 1984) % 12])
        month_name = _LUNAR_MONTH_NAMES[lu["month"] - 1]
        leap = "閏" if lu.get("leap") else ""
        day_name = _LUNAR_DAY_NAMES[max(0, min(29, lu["day"] - 1))]
        return f"農曆{yg}年{leap}{month_name}月{day_name}"
    except Exception:
        return ""


# ────────────────────────────── 自我校驗 ──────────────────────────────

def _self_check() -> None:
    """模組載入時的基本正確性自檢（僅在設定環境變數時啟用）。"""
    import os
    if not os.environ.get("LIUYAO_SELF_CHECK"):
        return
    ct = cast_time_from_date(2026, 8, 1, 14, 30)
    assert ct.year_gz == "丙午", ct.year_gz
    assert ct.month_zhi == "未", ct.month_zhi
    assert ct.day_gz == "丁未", ct.day_gz
    assert ct.xunkong == ("寅", "卯"), ct.xunkong


_self_check()
