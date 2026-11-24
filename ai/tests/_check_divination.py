import sys
from pathlib import Path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))          # ai/
sys.path.insert(0, str(_HERE.parent.parent / "src"))   # 排盤引擎
from datetime import datetime, timedelta, timezone

from liuyao_ai import divination as dv

TZ = timezone(timedelta(hours=8))
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")
    print(f"{'OK  ' if ok else 'FAIL'} {label}: {got!r}")


print("=== 1. 卦名 ↔ 六爻 ===")
check("乾為天六爻", dv.hexagram_lines("乾為天"), [1, 1, 1, 1, 1, 1])
check("地澤臨六爻", dv.hexagram_lines("地澤臨"), [1, 1, 0, 0, 0, 0])
check("六爻→卦名", dv.lines_to_hexagram([1, 1, 0, 0, 0, 0]), "地澤臨")
check("單字別名", dv.lines_to_hexagram(dv.hexagram_lines("臨")), "地澤臨")
check("動爻翻轉 2 爻", dv.flip_moving([1, 1, 0, 0, 0, 0], [2]), [1, 0, 0, 0, 0, 0])
check("地澤臨二爻動→地雷復", dv.lines_to_hexagram(dv.flip_moving([1, 1, 0, 0, 0, 0], [2])), "地雷復")

print("\n=== 2. 爻名 ===")
check("初爻陽", dv.yao_name(1, "陽"), "初九")
check("上爻陰", dv.yao_name(6, "陰"), "上六")
check("二爻陽", dv.yao_name(2, "陽"), "九二")
check("五爻陰", dv.yao_name(5, "陰"), "六五")
check("動爻位置", dv.yao_positions([2, 4]), "二、四")
check("無動爻", dv.yao_positions([]), "無")

print("\n=== 3. 銅錢法機率 ===")
import random
rng = random.Random(42)
counts = {}
for _ in range(12000):
    t = dv.toss_coins(rng)
    counts[t["total"]] = counts.get(t["total"], 0) + 1
for k in sorted(counts):
    print(f"      {k} {dv.TOSS_TABLE[k]['name']}: {counts[k] / 12000:.3f}")
check("老陰機率≈1/8", abs(counts[6] / 12000 - 0.125) < 0.02, True)
check("少陽機率≈3/8", abs(counts[7] / 12000 - 0.375) < 0.02, True)
check("少陰機率≈3/8", abs(counts[8] / 12000 - 0.375) < 0.02, True)
check("老陽機率≈1/8", abs(counts[9] / 12000 - 0.125) < 0.02, True)

print("\n=== 4. 完整起卦（銅錢） ===")
rng = random.Random(7)
tossed = dv.cast_by_coins(rng)
print(f"      {tossed['hexagram']} → {tossed['changed']}  動爻 {tossed['moving']}")
check("起卦有卦名", bool(tossed["hexagram"]), True)
check("六爻數", len(tossed["lines"]), 6)
if tossed["moving"]:
    check("有動爻必有變卦", bool(tossed["changed"]), True)

print("\n=== 5. 用神自動推斷 ===")
for q, want in [
    ("這次求職面試能否錄取", "官鬼"),
    ("今年財運如何", "妻財"),
    ("女友是否真心", "妻財"),
    ("考試能否考上", "官鬼"),
    ("買的房子風水如何", "父母"),
    ("家人介紹的對象是否旺我", "妻財"),
]:
    got, reason = dv.infer_yongshen(q)
    check(f"「{q}」", got, want)

print("\n=== 6. 完整占卦（repo 例一：地澤臨之復） ===")
req = dv.CastRequest(
    question="家人介紹的女緣，是否旺自己",
    hexagram="地澤臨",
    moving=[2],
    yongshen="妻財",
    when=datetime(2026, 7, 16, 14, 30, tzinfo=TZ),
)
result = dv.build_cast(req)
b = result["board"]
check("主卦", b["hexagram"], "地澤臨")
check("變卦", b["changed_hexagram"], "地雷復")
check("月建", b["month_zhi"], "未")
check("日辰", b["day_gz"], "辛卯")
check("旬空", b["xunkong"], ["午", "未"])
check("世爻位置", b["world_pos"], 2)
check("用神", b["yongshen_qin"], "妻財")
check("六爻數", len(b["lines"]), 6)
check("變卦六爻數", len(b["changed_lines"]), 6)

print("\n      六爻明細：")
for ln in b["lines"]:
    ch = f" → {ln['change_gan']}{ln['change_zhi']}({ln['change_qin']})" if ln["is_moving"] else ""
    print(f"      {ln['yao_name']:<3} {ln['shen']:<3} {ln['qin']:<3} "
          f"{ln['gan']}{ln['zhi']}{ln['wx']} {ln['state'] or '—':<2} "
          f"{'、'.join(ln['tags']) or '靜'}{ch}")

print("\n=== 7. 關鍵判定核對（對照 repo 手工結論） ===")
line2 = next(l for l in b["lines"] if l["pos"] == 2)
check("世爻二爻", line2["is_world"], True)
check("二爻動", line2["is_moving"], True)
check("二爻化退神", line2["jin_tui"], "化退神")
check("二爻入墓", "月墓" in line2["in_grave"], True)
check("二爻臨玄武", line2["shen"], "玄武")

# 子孫酉金暗動（未月旺相，卯日沖）—— repo 的關鍵結論（在上爻）
line6 = next(l for l in b["lines"] if l["pos"] == 6)
print(f"      上爻：{line6['yao_name']} {line6['qin']} {line6['gan']}{line6['zhi']}"
      f" 標註={line6['tags']}")
check("上爻為子孫酉金", (line6["qin"], line6["zhi"]), ("子孫", "酉"))
check("上爻暗動（非日破）", line6["dark_move"], True)
check("上爻非日破", line6["day_break"], False)

print("\n=== 8. Prompt 文字 ===")
text = dv.board_to_prompt_text(b)
check("含月建", "乙未" in text or "未" in text, True)
check("含暗動", "暗動" in text, True)
print("      ---- 前 18 行 ----")
for ln in text.splitlines()[:18]:
    print("      " + ln)

print("\n=== 9. 輸出規範與未成局三合 ===")
import copy
from liuyao_ai import prompt as pr
bundle = pr.build_prompt(b, req.question)
check("輸出含逐象詳解", "逐象詳解" in bundle.user, True)
check("不再使用全局分解", "全局分解" not in bundle.user, True)
check("系統要求只解讀有用象", "只解讀「有用」的象" in bundle.system, True)
check("系統要求三合只論實成", "三合只論實成之局" in bundle.system, True)
check("系統要求先說當下", "先說當下，再說未來" in bundle.system, True)
compact = pr._compact_for_prompt(b)
check("本例虛合不進 JSON", compact["sanhe"], {})
check("本例虛合不進文字", "三合：" not in text, True)
check("本例虛合不進 user", "三合：" not in bundle.user, True)

print("\n=== 10. 地支關係、旺衰與長生、標點 ===")
from liuyao.data import CHONG
check("六沖辰戌", CHONG["辰"], "戌")
check("六沖丑未", CHONG["丑"], "未")
check("丑辰不互沖", CHONG["丑"] != "辰" and CHONG["辰"] != "丑", True)
check("角色開頭", bundle.system.startswith("你是一位精研六爻十年的占卜師，以繁體中文為人斷卦。"), True)
check("無台灣用語規則", "台灣用語" not in bundle.system, True)
check("變卦納甲有五行", b["changed_lines"][0]["wx"], "水")
check("系統禁止破折號", "不要用破折號" in bundle.system, True)
check("旺衰與十二長生分開", "旺衰與十二長生分開" in bundle.system, True)
check("系統有六沖表", "子午、丑未、寅申、卯酉、辰戌、巳亥" in bundle.system, True)
check("系統明示丑辰不沖", "丑與辰不是六沖" in bundle.system, True)
check("user 有六沖表", "子午、丑未、寅申、卯酉、辰戌、巳亥" in bundle.user, True)
check("user 明示丑辰不沖", "丑與辰不是六沖" in bundle.user, True)
check("user 無破折號", "——" not in bundle.user and "—" not in bundle.user, True)
check("user 要求旺衰長生分開", "旺衰與十二長生分開寫" in bundle.user, True)
check("無兄弟奔走", "奔走" not in bundle.system, True)
check("有三合位置規則", "三合局必須符合成局位置" in bundle.system, True)

b_formed = copy.deepcopy(b)
b_formed["sanhe"] = {"亥卯未木局": {"status": "實成之局"}}
check("實成局保留在 JSON", list(pr._compact_for_prompt(b_formed)["sanhe"]), ["亥卯未木局"])
check("實成局保留在文字", "三合：亥卯未木局" in dv.board_to_prompt_text(b_formed), True)

print("\n=== 11. 三合局位置與靜爻 ===")
from types import SimpleNamespace
from liuyao.board import _detect_sanhe


def _mk(pos, zhi, moving=False):
    return SimpleNamespace(position=pos, zhi=zhi, is_moving=moving, dark_move=False)


def _sanhe_status(lines, month="亥", day="午"):
    fake = SimpleNamespace(lines=lines, month_zhi=month, day_zhi=day, sanhe={})
    _detect_sanhe(fake)
    return fake.sanhe["申子辰水局"]["status"]


# 申3動、子5動、辰1靜；沒有日月助成 → 不能成局
_case1 = [_mk(1, "辰"), _mk(2, "寅"), _mk(3, "申", True),
          _mk(4, "丑"), _mk(5, "子", True), _mk(6, "卯")]
check("靜辰不能湊申子辰局", _sanhe_status(_case1).startswith("實成"), False)

# 初、三同動 → 成局
_case2 = [_mk(1, "辰", True), _mk(2, "寅"), _mk(3, "申", True),
          _mk(4, "丑"), _mk(5, "子"), _mk(6, "卯")]
check("初三相動成局", _sanhe_status(_case2).startswith("實成"), True)

# 四、上同動 → 成局
_case3 = [_mk(1, "辰"), _mk(2, "寅"), _mk(3, "卯"),
          _mk(4, "子", True), _mk(5, "丑"), _mk(6, "申", True)]
check("四上相動成局", _sanhe_status(_case3).startswith("實成"), True)

# 子臨日，但辰靜 → 仍不能湊局
_case4 = [_mk(1, "辰"), _mk(2, "寅"), _mk(3, "申", True),
          _mk(4, "丑"), _mk(5, "子"), _mk(6, "卯")]
check("子臨日但辰靜不成局", _sanhe_status(_case4, day="子").startswith("實成"), False)

# 日月有一支，且其餘兩支皆動 → 可成局（位置不在1/3、4/6也一樣）
_case5 = [_mk(1, "巳"), _mk(2, "辰", True), _mk(3, "卯"),
          _mk(4, "申", True), _mk(5, "子"), _mk(6, "丑")]
check("日月助成且其餘兩支皆動", _sanhe_status(_case5, day="子").startswith("實成"), True)

print("\n" + "=" * 60)
if fails:
    print(f"❌ {len(fails)} 項失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 全部透過")
