import sys
from pathlib import Path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))          # ai/
sys.path.insert(0, str(_HERE.parent.parent / "src"))   # 排盤引擎
from datetime import datetime, timedelta, timezone

from liuyao_ai import calendar as cal

TZ = timezone(timedelta(hours=8))
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")
    print(f"{'OK  ' if ok else 'FAIL'} {label}: {got!r}")


print("=== 1. 日干支（已知錨點） ===")
# 1949-10-01 為甲子日（多個黃曆來源一致：己丑年 癸酉月 甲子日）
check("1949-10-01 日干支", cal._day_gz(datetime(1949, 10, 1, 12, tzinfo=TZ)), "甲子")
# 2000-01-01 為戊午日（與多個萬年曆一致）
check("2000-01-01 日干支", cal._day_gz(datetime(2000, 1, 1, 12, tzinfo=TZ)), "戊午")
# 2024-01-01 亦為甲子日（另一錨點，驗證 60 日迴圈）
check("2024-01-01 日干支", cal._day_gz(datetime(2024, 1, 1, 12, tzinfo=TZ)), "甲子")
# 2026-08-01 = 丁未日
check("2026-08-01 日干支", cal._day_gz(datetime(2026, 8, 1, 12, tzinfo=TZ)), "丁未")
# repo 例一「未月辛卯日」實際對應 2026-07-16
check("2026-07-16 日干支", cal._day_gz(datetime(2026, 7, 16, 12, tzinfo=TZ)), "辛卯")

print("\n=== 2. 旬空 ===")
check("辛卯旬空", cal.xunkong("辛卯"), ("午", "未"))
check("甲子旬空", cal.xunkong("甲子"), ("戌", "亥"))
check("甲申旬空", cal.xunkong("甲申"), ("午", "未"))
check("癸亥旬空", cal.xunkong("癸亥"), ("子", "丑"))

print("\n=== 3. 節氣時刻（對照天文年曆） ===")
# 2026 年立春：2026-02-04 05:46（臺灣時間）左右
for name, y, want_day in [
    ("立春", 2026, 4), ("春分", 2026, 20), ("夏至", 2026, 21),
    ("秋分", 2026, 23), ("冬至", 2026, 22), ("立冬", 2026, 7),
]:
    m = cal.term_moment(y, name)
    check(f"{y} {name} 日期", m.day, want_day)
    print(f"      {name} 時刻：{m:%Y-%m-%d %H:%M:%S}")

print("\n=== 4. 年干支（立春換年） ===")
check("2026-08-01 年干支", cal.cast_time_from_date(2026, 8, 1).year_gz, "丙午")
check("2026-01-15 年干支", cal.cast_time_from_date(2026, 1, 15).year_gz, "乙巳")
check("2026-02-03 年干支", cal.cast_time_from_date(2026, 2, 3).year_gz, "乙巳")
check("2026-02-05 年干支", cal.cast_time_from_date(2026, 2, 5).year_gz, "丙午")
check("2025-12-31 年干支", cal.cast_time_from_date(2025, 12, 31).year_gz, "乙巳")
check("2024-06-01 年干支", cal.cast_time_from_date(2024, 6, 1).year_gz, "甲辰")
print("\n=== 5. 月建（節氣換月） ===")
cases = [
    (2026, 2, 5, "寅"), (2026, 3, 7, "卯"), (2026, 4, 6, "辰"),
    (2026, 5, 7, "巳"), (2026, 6, 7, "午"), (2026, 7, 8, "未"),
    (2026, 8, 8, "申"), (2026, 9, 9, "酉"), (2026, 10, 9, "戌"),
    (2026, 11, 8, "亥"), (2026, 12, 8, "子"),
]
for y, m, d, want in cases:
    got = cal.cast_time_from_date(y, m, d, 12).month_zhi
    check(f"{y}-{m:02d}-{d:02d} 月建", got, want)

# 交界前的「同一日」仍屬上一個節氣月（節氣時刻當日才交節）
check("2026-02-03 月建", cal.cast_time_from_date(2026, 2, 3, 12).month_zhi, "丑")
check("2026-07-06 月建", cal.cast_time_from_date(2026, 7, 6, 12).month_zhi, "午")
# 交節當日：交節時刻前屬舊月、後屬新月
check("2026-10-08 12:00（寒露前）", cal.cast_time_from_date(2026, 10, 8, 12).month_zhi, "酉")
check("2026-10-08 20:00（寒露後）", cal.cast_time_from_date(2026, 10, 8, 20).month_zhi, "戌")

print("\n=== 6. 月干支（五虎遁） ===")
check("2026 未月", cal.cast_time_from_date(2026, 8, 1).month_gz, "乙未")
check("2026 寅月", cal.cast_time_from_date(2026, 2, 10).month_gz, "庚寅")
check("2026 子月", cal.cast_time_from_date(2026, 12, 15).month_gz, "庚子")

print("\n=== 7. 完整排盤引數（repo 經典卦例：未月辛卯日） ===")
ct = cal.cast_time_from_date(2026, 7, 16, 14, 30)
print(f"      {ct.moment:%Y-%m-%d %H:%M}  {ct.year_gz}年 {ct.month_gz}月 {ct.day_gz}日"
      f"  旬空{ct.xunkong}  時辰{ct.shichen}  節{ct.jie}")
check("例一 年干支", ct.year_gz, "丙午")
check("例一 月建", ct.month_zhi, "未")
check("例一 月干支", ct.month_gz, "乙未")
check("例一 日干支", ct.day_gz, "辛卯")
check("例一 旬空", ct.xunkong, ("午", "未"))

print("\n=== 8. 時辰 ===")
for h, want in [(23, "子"), (0, "子"), (1, "丑"), (2, "丑"), (3, "寅"),
                (11, "午"), (12, "午"), (13, "未"), (21, "亥"), (22, "亥")]:
    got = cal.shichen(datetime(2026, 8, 1, h, 0, tzinfo=TZ))
    check(f"{h:02d}時", got, want)

print("\n=== 9. 農曆顯示 ===")
print("      2026-08-01:", ct.lunar_text)
print("      2026-11-22:", cal.cast_time_from_date(2026, 11, 22).lunar_text)

print("\n=== 10. 節氣表完整性 ===")
ts = cal.terms_in_year(2026)
check("2026 節氣數", len(ts), 24)
check("2026 節數", len(cal.jie_in_year(2026)), 12)
print("      ", " ".join(f"{t.name}{t.moment:%m-%d}" for t in ts))

print("\n" + "=" * 60)
if fails:
    print(f"❌ {len(fails)} 項失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 全部透過")
