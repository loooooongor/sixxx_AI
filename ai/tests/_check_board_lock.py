"""回歸測試：一卦只能起一次 —— 畫面排出的卦盤必須就是 LLM 解讀的那一份。

背景（bug）：`/api/cast`（擲錢）排好卦之後，前端若把同一份請求內容
（含 `use_coins: true`、不帶卦盤）再送到 `/api/read`，後端會再擲一次銅錢，
於是「畫面上顯示的卦」與「解讀所用的卦」變成兩個不同的卦。

本腳本鎖住三個不變量：
  1. 請求帶回 `board` 時，回傳的卦盤必須與帶回的完全一致、且不得再變動；
  2. 同一份 `board` 重複請求 N 次，卦盤必須逐位元組相同（證明沒有重擲）；
  3. 只有未帶 `board` 時，才允許後端自行排盤（`board_source == "server"`）。
另檢查殘缺／自相矛盾的卦盤一律回 400，不會被拿去解讀。

需要伺服器：``python server.py``
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8848"
fails = []


def check(label, got, want=True):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")
    print(f"{'OK  ' if ok else 'FAIL'} {label}: {got!r}")


def call(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, headers={"content-type": "application/json"},
        method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def expect_400(label, payload):
    try:
        call("/api/preview", payload)
    except urllib.error.HTTPError as e:
        check(f"{label} → 400", e.code, 400)
    else:
        check(f"{label} → 400", False)


def clone(board):
    return json.loads(json.dumps(board))


QUESTION = "這次合作能否談成"

print("=== 1. 擲錢起卦（唯一的隨機來源） ===")
cast = call("/api/cast", {"question": QUESTION, "use_coins": True})
check("ok", cast["ok"])
board = cast["board"]
hexagram = board["hexagram"]
check("有擲錢紀錄", len(cast["meta"]["tosses"]), 6)
print(f"      本次起卦：{hexagram}"
      f"{'→' + board['changed_hexagram'] if board['changed_hexagram'] else ''}"
      f"　動爻 {board['moving_positions']}")

print("\n=== 2. 帶回同一份卦盤解讀：必須永遠是同一卦 ===")
first = None
for i in range(5):
    pv = call("/api/preview", {
        "question": QUESTION,
        "use_coins": True,          # 故意保留：舊版會因此重擲，新版必須忽略
        "board": board,
    })
    tag = f"第 {i + 1} 次"
    check(f"{tag} 卦名", pv["board"]["hexagram"], hexagram)
    check(f"{tag} 變卦", pv["board"]["changed_hexagram"], board["changed_hexagram"])
    check(f"{tag} 動爻", pv["board"]["moving_positions"], board["moving_positions"])
    check(f"{tag} 時間", pv["board"]["cast_time"]["moment"], board["cast_time"]["moment"])
    check(f"{tag} 來源為 client", pv.get("board_source"), "client")
    check(f"{tag} prompt 含此卦名", hexagram in pv["user"])
    snapshot = json.dumps(pv["board"], sort_keys=True, ensure_ascii=False)
    if first is None:
        first = snapshot
    else:
        check(f"{tag} 卦盤與第一次完全相同", snapshot == first)

print("\n=== 3. 未帶 board：才由後端排盤 ===")
pv2 = call("/api/preview", {"question": "手動指定", "hexagram": "地澤臨", "moving": [2]})
check("來源為 server", pv2.get("board_source"), "server")
check("主卦", pv2["board"]["hexagram"], "地澤臨")
check("變卦", pv2["board"]["changed_hexagram"], "地雷復")

print("\n=== 4. 殘缺／矛盾卦盤一律拒絕 ===")
bad = clone(board)
bad["hexagram"] = "乾為天" if hexagram != "乾為天" else "坤為地"
expect_400("卦名與六爻不符", {"question": QUESTION, "board": bad})

bad2 = clone(board)
bad2["lines"] = bad2["lines"][:5]
expect_400("只有五爻", {"question": QUESTION, "board": bad2})

bad3 = clone(board)
bad3["moving_positions"] = [] if board["moving_positions"] else [1]
expect_400("動爻與六爻標記不符", {"question": QUESTION, "board": bad3})

bad4 = clone(board)
bad4["cast_time"] = {"moment": bad4["cast_time"].get("moment")}
expect_400("占卦時間缺欄位", {"question": QUESTION, "board": bad4})

expect_400("board 不是物件", {"question": QUESTION, "board": "地澤臨"})
expect_400("占問空白", {"question": "   ", "board": board})

print("\n=== 5. /api/read 也走同一套驗證（壞卦盤不得送去解讀） ===")
try:
    req = urllib.request.Request(
        BASE + "/api/read",
        data=json.dumps({"question": QUESTION, "board": bad}).encode(),
        headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=30)
    check("壞卦盤被擋下", False)
except urllib.error.HTTPError as e:
    check("HTTP 400（在呼叫 LLM 之前就擋下）", e.code, 400)
    print("      訊息：", json.loads(e.read().decode()).get("error", "")[:60])

print("\n" + "=" * 60)
if fails:
    print(f"❌ {len(fails)} 項失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 一卦只起一次：全部通過")
