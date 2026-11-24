"""端到端 API 測試：排盤、prompt 組裝、設定、SSE 串流（以假 LLM 驗證）。"""

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8848"
fails = []


def check(label, got, want=True):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")
    print(f"{'OK  ' if ok else 'FAIL'} {label}: {got!r}")


def call(path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"content-type": "application/json"},
        method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


print("=== 1. health ===")
h = call("/api/health")
check("ok", h["ok"])
check("知識庫小節 > 100", h["sections_indexed"] > 100)
check("12 冊", h["docs_indexed"], 12)
check("初始未設定金鑰", h["llm"]["configured"], False)

print("\n=== 2. providers ===")
p = call("/api/providers")
check("供應商數 >= 6", len(p["providers"]) >= 6)
print("      ", "、".join(x["label"] for x in p["providers"]))

print("\n=== 3. 排盤（repo 例一） ===")
res = call("/api/cast", {
    "question": "家人介紹的女緣，是否旺自己",
    "hexagram": "地澤臨",
    "moving": [2],
    "yongshen": "妻財",
    "when": {"iso": "2026-07-16T06:30:00+00:00"},
})
check("ok", res["ok"])
b = res["board"]
check("主卦", b["hexagram"], "地澤臨")
check("變卦", b["changed_hexagram"], "地雷復")
check("月建", b["month_zhi"], "未")
check("日辰", b["day_gz"], "辛卯")
check("旬空", b["xunkong"], ["午", "未"])
check("用神", b["yongshen_qin"], "妻財")
check("六爻", len(b["lines"]), 6)
check("上爻暗動", next(l for l in b["lines"] if l["pos"] == 6)["dark_move"], True)
check("二爻化退", next(l for l in b["lines"] if l["pos"] == 2)["jin_tui"], "化退神")

print("\n=== 4. 銅錢起卦（無指定卦） ===")
res2 = call("/api/cast", {"question": "測試擲錢起卦", "use_coins": True,
                          "when": {"iso": "2026-11-22T04:00:00+00:00"}})
check("ok", res2["ok"])
check("有卦名", bool(res2["board"]["hexagram"]))
check("有擲錢紀錄", len(res2["meta"]["tosses"]), 6)
check("擲錢總和合法", all(t["total"] in (6, 7, 8, 9) for t in res2["meta"]["tosses"]))
print(f"      {res2['meta']['tosses'][0]}")

print("\n=== 5. 用神自動推斷 ===")
res3 = call("/api/cast", {"question": "這次求職面試能否錄取", "use_coins": True,
                          "when": {"iso": "2026-11-22T04:00:00+00:00"}})
check("自動取官鬼", res3["board"]["yongshen_qin"], "官鬼")
print("      理由：", res3["board"]["yongshen_reason"])

print("\n=== 6. prompt 組裝 ===")
pv = call("/api/preview", {
    "question": "家人介紹的女緣，是否旺自己",
    "hexagram": "地澤臨", "moving": [2], "yongshen": "妻財",
    "when": {"iso": "2026-07-16T06:30:00+00:00"},
})
check("ok", pv["ok"])
check("system 有內容", len(pv["system"]) > 3000)
check("user 有內容", len(pv["user"]) > 800)
check("含八步流程", "取用神" in pv["system"])
check("含暗動辨析", "暗動" in pv["system"])
check("含卦盤文字", "地澤臨" in pv["user"])
check("含 JSON", '"hexagram"' in pv["user"])
print(f"      system {pv['system_chars']} 字 / user {pv['user_chars']} 字"
      f" / 合計約 {pv['system_chars'] + pv['user_chars']} 字")

print("\n=== 7. 知識庫動態擷取（依卦象選冊） ===")
sys.path.insert(0, ".")
from liuyao_ai.knowledge import get_kb
kb = get_kb()
docs = kb.sections_for_board(b, "家人介紹的女緣是否旺自己")
print("      本例選冊：", docs)
check("有選到技法冊", len(docs) >= 3)
ctx = kb.build_context(b, "家人介紹的女緣是否旺自己")
check("上下文含方法論", "斷卦方法論" in ctx)
check("上下文含技法參考", "技法參考" in ctx)
print(f"      上下文字數：{len(ctx)}")

# 不同卦象應選不同冊
b2 = dict(b)
b2["lines"] = [dict(l, tags=[], role=None) for l in b["lines"]]
b2["sanhe"] = {"亥卯未木局": {"status": "虛合(缺亥，待填實)"}}
b2["is_liuhe_gua"] = True
docs2 = kb.sections_for_board(b2, "test")
print("      三合/六合卦選冊：", docs2)
check("三合卦含 06 冊", any(d.startswith("06") for d in docs2))

print("\n=== 8. 設定讀寫 ===")
s0 = call("/api/settings")
check("初始 provider", s0["settings"]["provider"], "deepseek")
s1 = call("/api/settings", {"provider": "openai", "model": "gpt-4o-mini"})
check("切換 provider", s1["settings"]["provider"], "openai")
check("切換 model", s1["settings"]["model"], "gpt-4o-mini")
check("base_url 跟著換", "openai" in s1["settings"]["base_url"])
# 切回
call("/api/settings", {"provider": "deepseek", "model": "deepseek-chat"})

print("\n=== 9. 未設定金鑰時的行為 ===")
try:
    req = urllib.request.Request(
        BASE + "/api/read", data=json.dumps({
            "question": "測試", "hexagram": "地澤臨", "moving": [2],
        }).encode(), headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
        check("回 428 提示設定", out.get("need_settings"), True)
        print("      訊息：", out.get("error", "")[:70])
except urllib.error.HTTPError as e:
    body = json.loads(e.read().decode())
    check("HTTP 428", e.code, 428)
    check("need_settings", body.get("need_settings"), True)

print("\n=== 10. 靜態檔 ===")
for path, ctype in [("/", "text/html"), ("/assets/app.css", "text/css"),
                    ("/assets/app.js", "javascript")]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            body = r.read()
            check(f"{path} 可讀", len(body) > 100)
            check(f"{path} 型別", ctype in r.headers.get("content-type", ""))
    except Exception as e:
        check(f"{path} 可讀", f"FAIL {e}")

print("\n=== 11. 錯誤處理 ===")
try:
    urllib.request.urlopen(BASE + "/api/nope", timeout=10)
    check("404", False)
except urllib.error.HTTPError as e:
    check("404 狀態", e.code, 404)

try:
    call("/api/cast", {"question": ""})
    check("空問題被拒", False)
except urllib.error.HTTPError as e:
    check("空問題 400", e.code, 400)

try:
    call("/api/cast", {"question": "測試", "hexagram": "不存在的卦", "moving": []})
    check("怪卦名被拒", False)
except urllib.error.HTTPError as e:
    check("怪卦名 400", e.code, 400)

print("\n=== 12. glossary ===")
g = call("/api/glossary")
check("術語數 > 30", len(g["glossary"]) > 30)
print("      樣本：", "、".join(list(g["glossary"])[:8]))

print("\n" + "=" * 60)
if fails:
    print(f"❌ {len(fails)} 項失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 全部通過")
