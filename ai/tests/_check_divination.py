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
bundle = pr.build_prompt(b, req.question, mode="detailed")
check("輸出含逐象詳解", "逐象詳解" in bundle.user, True)
check("不再使用全局分解", "全局分解" not in bundle.user, True)
check("系統要求只解讀有用象", "只解讀「有用」的象" in bundle.system, True)
check("系統要求三合只論實成", "三合只論實成之局" in bundle.system, True)
check("系統要求先說當下", "先說當下，再說未來" in bundle.system, True)
check("系統要求應期非必寫", "應期不是每卦必寫" in bundle.system, True)
check("系統有占問分類裁剪", "依占問裁剪段落" in bundle.system, True)
check("系統有描述型占問", "描述型" in bundle.system and "猜物" in bundle.system, True)
check("user 應期條件", "只有當時間是問題的一部分" in bundle.user, True)
check("user 建議條件", "沒有可操作的建議" in bundle.user, True)
check("user 猜物不硬套卡點", "不必勉強給成敗" in bundle.user, True)
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
check("有飛伏規則", "飛神伏神只認引擎欄位" in bundle.system, True)
check("詳細版模式", "本次輸出模式：詳細版" in bundle.system, True)
check("預設精簡", "本次輸出模式：精簡版" in pr.build_prompt(b, req.question).system, True)
check("暗動象意", "暗中、背後推動" in bundle.system and "未察覺之事悄悄發生" in bundle.system, True)
check("無浮動", "浮動" not in pr.build_prompt(b, req.question).system, True)
_concise = pr.build_prompt(b, "測試精簡模式", mode="concise")
check("精簡版模式", "本次輸出模式：精簡版" in _concise.system, True)
check("精簡版四段", "## 二、卦象與判斷" in _concise.user, True)
check("精簡版沒有用神段", "## 二、用神" not in _concise.user, True)
check("精簡版旺相", "旺相" in _concise.system and "休囚" in _concise.system, True)
check("精簡版應期可省", "只在時間是問題的一部分時才寫" in _concise.user, True)
check("精簡版建議可省", "描述型占問沒有可操作的建議" in _concise.user, True)
check("精簡版回傳 mode", _concise.mode, "concise")

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

print("\n=== 12. 飛神伏神 ===")
_fu_req = dv.CastRequest(
    question="和一家國企合作能否談成",
    hexagram="水火既濟",
    moving=[],
    yongshen="妻財",
    when=datetime(2019, 2, 21, 17, 36, 22, tzinfo=TZ),
)
_fu_board = dv.build_cast(_fu_req)["board"]
_fu = _fu_board["fu_shen"][0]
check("既濟缺妻財", _fu["qin"], "妻財")
check("妻財午火伏三爻", (_fu["pos"], _fu["zhi"]), (3, "午"))
check("伏於兄弟亥水下", (_fu["fei"]["qin"], _fu["fei"]["zhi"]), ("兄弟", "亥"))
check("飛剋伏", _fu["relation"], "飛剋伏")
check("伏神空亡不能出", _fu["can_chu"], False)
check("用神不上卦取伏神", len(_fu_board["yongshen_fu"]), 1)
check("伏神進 prompt 文字", "伏神 妻財午火" in dv.board_to_prompt_text(_fu_board), True)

_gou_req = dv.CastRequest(
    question="測試天風姤伏神",
    hexagram="天風姤",
    moving=[],
    yongshen="妻財",
    when=datetime(2019, 2, 21, 17, 36, 22, tzinfo=TZ),
)
_gou_board = dv.build_cast(_gou_req)["board"]
_gou = _gou_board["fu_shen"][0]
check("天風姤實際缺妻財", _gou["qin"], "妻財")
check("天風姤伏神在二爻", _gou["pos"], 2)
check("天風姤飛生伏", _gou["relation"], "飛生伏")
check("六親齊全不取伏神", dv.build_cast(dv.CastRequest(
    question="測試六親齊全", hexagram="乾為天", moving=[],
    when=datetime(2019, 2, 21, 17, 36, 22, tzinfo=TZ)))["board"]["fu_shen"], [])

print("\n=== 13. 銅錢／報數的六爻輸入 ===")
_lv = [7, 8, 7, 8, 9, 8]   # 少陽、少陰、少陽、少陰、老陽、少陰
_lv_cast = dv.build_cast(dv.CastRequest(
    question="六爻輸入測試", line_values=_lv,
    when=datetime(2019, 2, 21, 17, 36, 22, tzinfo=TZ)))
check("line_values 卦名", _lv_cast["board"]["hexagram"], "水火既濟")
check("line_values 動爻", _lv_cast["board"]["moving_positions"], [5])
check("line_values 變卦", _lv_cast["board"]["changed_hexagram"], "地火明夷")
check("line_values 有記錄", _lv_cast["meta"]["line_values"], _lv)
_static = dv.build_cast(dv.CastRequest(
    question="六爻全靜", line_values=[7, 7, 7, 7, 7, 7],
    when=datetime(2019, 2, 21, 17, 36, 22, tzinfo=TZ)))
check("全靜為乾", _static["board"]["hexagram"], "乾為天")
check("全靜無動爻", _static["board"]["moving_positions"], [])
check("男占感情取妻財", dv.infer_yongshen("這段感情還能走下去嗎", "男")[0], "妻財")
check("女占感情取官鬼", dv.infer_yongshen("這段感情還能走下去嗎", "女")[0], "官鬼")
_gender_board = dv.build_cast(dv.CastRequest(
    question="這段感情還能走下去嗎", hexagram="地澤臨", moving=[2], gender="女",
    when=datetime(2019, 2, 21, 17, 36, 22, tzinfo=TZ)))["board"]
check("卦盤有性別", _gender_board.get("gender"), "女")
check("性別影響用神", _gender_board.get("yongshen_qin"), "官鬼")
check("性別進 prompt", "占問者性別：女" in dv.board_to_prompt_text(_gender_board), True)
try:
    dv.build_cast(dv.CastRequest(question="壞輸入", line_values=[7, 8]))
    check("line_values 長度錯誤", False, True)
except ValueError:
    check("line_values 長度錯誤", True, True)

print("\n" + "=" * 60)
if fails:
    print(f"❌ {len(fails)} 項失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 全部透過")
