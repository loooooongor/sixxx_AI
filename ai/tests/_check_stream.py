"""端到端串流測試：把 LLM 指向假伺服器，驗證 SSE 全流程。"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

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
        BASE + path, data=data, headers={"content-type": "application/json"},
        method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def sse_stream(path, payload):
    """讀 SSE，回傳 (events, raw_text)。

    注意：UTF-8 中文一個字占 3 bytes，網路分塊可能切在中間，
    故先累積 bytes、再增量解碼（等同前端 TextDecoder(stream:true)）。
    """
    import codecs

    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"}, method="POST")
    events = []
    text = ""
    decoder = codecs.getincrementaldecoder("utf-8")()
    with urllib.request.urlopen(req, timeout=120) as r:
        buf = ""
        while True:
            chunk = r.read(1024)
            if not chunk:
                break
            buf += decoder.decode(chunk)
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                event = "message"
                data_lines = []
                for line in block.split("\n"):
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data: "):
                        data_lines.append(line[6:])
                    elif line.startswith("data:"):
                        data_lines.append(line[5:])
                if not data_lines:
                    continue
                raw = "\n".join(data_lines)
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    parsed = raw
                events.append((event, parsed))
                if event == "delta":
                    text += parsed if isinstance(parsed, str) else ""
    return events, text


print("=== 1. 把 LLM 指向假伺服器 ===")
s = call("/api/settings", {
    "provider": "custom",
    "base_url": "http://127.0.0.1:8901/v1",
    "model": "mock-model",
    "api_key": "sk-mock-test-key-123456",
})
check("已設定", s["settings"]["configured"], True)
check("provider", s["settings"]["provider"], "custom")

print("\n=== 2. /api/read 串流解卦 ===")
events, text = sse_stream("/api/read", {
    "question": "家人介紹的女緣，是否旺自己",
    "hexagram": "地澤臨", "moving": [2], "yongshen": "妻財",
    "when": {"iso": "2026-07-16T06:30:00+00:00"},
})
names = [e for e, _ in events]
check("有 board 事件", "board" in names)
check("有 meta 事件", "meta" in names)
check("有 delta 事件", names.count("delta") > 5)
check("有 done 事件", "done" in names)
check("無 error 事件", "error" not in names)
check("收到全文", len(text) > 300)
check("含總斷", "總斷" in text)
check("含用神", "用神" in text)
check("含應期", "應期" in text)
check("含建議", "建議" in text)
check("保留段落換行", text.count("\n") > 8)
print(f"      事件數 {len(events)}（delta {names.count('delta')}）／全文 {len(text)} 字")
print("      首 40 字：", text[:40].replace("\n", " "))
print("      末 40 字：", text[-40:].replace("\n", " "))

print("\n=== 3. 驗證送給 LLM 的 prompt ===")
try:
    sent = json.load(open(Path(__file__).resolve().parent / "_mock_llm_last_request.json", encoding="utf-8"))
    print("      ", sent)
    check("model 正確", sent["model"], "mock-model")
    check("stream 開啟", sent["stream"], True)
    check("有 system 訊息", sent["system_chars"] > 3000)
    check("有 user 訊息", sent["user_chars"] > 800)
except OSError as e:
    check("讀到請求紀錄", f"FAIL {e}")

print("\n=== 4. board 事件內容 ===")
board_ev = next((d for e, d in events if e == "board"), None)
check("board 有卦名", board_ev and board_ev.get("hexagram"), "地澤臨")
check("board 有六爻", len(board_ev.get("lines", [])), 6)

print("\n=== 4b. /api/read 帶回卦盤：解讀必須是同一卦 ===")
cast = call("/api/cast", {"question": "串流一致性", "use_coins": True})
board_c = cast["board"]
events_c, _text_c = sse_stream("/api/read", {
    "question": "串流一致性",
    "use_coins": True,          # 舊版會因此重擲；帶了 board 就必須沿用
    "board": board_c,
})
board_ev_c = next((d for e, d in events_c if e == "board"), {}) or {}
meta_c = next((d for e, d in events_c if e == "meta"), {}) or {}
check("解讀卦名＝排盤卦名", board_ev_c.get("hexagram"), board_c["hexagram"])
check("動爻一致", board_ev_c.get("moving_positions"), board_c["moving_positions"])
check("meta 標記來源 client", meta_c.get("board_source"), "client")
check("meta 卦名一致", meta_c.get("hexagram"), board_c["hexagram"])
print(f"      起卦 {board_c['hexagram']} → 解讀 {board_ev_c.get('hexagram')}")

print("\n=== 5. /api/followup 串流追問 ===")
events2, text2 = sse_stream("/api/followup", {
    "board": board_ev,
    "question": "家人介紹的女緣，是否旺自己",
    "prior_answer": text[:300],
    "followup": "那她什麼時候會表態？",
})
names2 = [e for e, _ in events2]
check("追問有 delta", names2.count("delta") > 3)
check("追問完成", "done" in names2)
check("追問無錯誤", "error" not in names2)
check("追問有內容", len(text2) > 200)
print(f"      追問事件 {len(events2)}／{len(text2)} 字")

print("\n=== 6. 缺金鑰的行為（清空後測） ===")
call("/api/settings", {"clear_key": True})
h = call("/api/health")
check("金鑰已清空", h["llm"]["has_key"], False)
try:
    req = urllib.request.Request(
        BASE + "/api/read", data=json.dumps({
            "question": "測試", "use_coins": True}).encode(),
        headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=30)
    check("應回 428", False)
except urllib.error.HTTPError as e:
    check("HTTP 428", e.code, 428)

print("\n=== 7. LLM 認證失敗的處理 ===")
# 換回有 key，但指向會回 401 的假伺服器
call("/api/settings", {
    "provider": "custom", "base_url": "http://127.0.0.1:8902/v1",
    "model": "mock", "api_key": "sk-bad-key-0000000000",
})
events3, text3 = sse_stream("/api/read", {
    "question": "測試認證失敗", "use_coins": True})
names3 = [e for e, _ in events3]
check("有 error 事件", "error" in names3)
err = next((d for e, d in events3 if e == "error"), {})
msg = err.get("message", "") if isinstance(err, dict) else str(err)
print("      錯誤訊息：", msg[:110].replace("\n", " "))
check("訊息含 401 說明", "401" in msg)
check("訊息含 key 提示", "金鑰" in msg or "key" in msg.lower())

print("\n=== 8. 復原設定 ===")
call("/api/settings", {
    "provider": "deepseek", "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com", "clear_key": True,
})
h = call("/api/health")
check("已復原為 deepseek", h["llm"]["provider"], "deepseek")

print("\n" + "=" * 60)
if fails:
    print(f"❌ {len(fails)} 項失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 全部通過")
