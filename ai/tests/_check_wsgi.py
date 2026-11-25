"""檢查 Vercel / WSGI 入口：靜態檔、健康檢查、排盤與 prompt。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
ROOT = AI_DIR.parent
for p in (str(ROOT), str(AI_DIR), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from ai.wsgi import app  # noqa: E402

app.testing = True
client = app.test_client()
fails = []


def check(name: str, got, want=True) -> None:
    ok = got == want
    if not ok:
        fails.append(f"{name}: got={got!r} want={want!r}")
    print(("OK   " if ok else "FAIL ") + f"{name}: {got}")


r = client.get("/")
check("首頁 200", r.status_code, 200)
check("首頁品牌", "知幾筆記" in r.get_data(as_text=True), True)

r = client.get("/assets/app.css")
check("CSS 200", r.status_code, 200)
check("CSS 非空", len(r.data) > 1000, True)

for page in ("/pricing.html", "/billing-success.html"):
    r = client.get(page)
    check(f"{page} 200", r.status_code, 200)
    check(f"{page} 有品牌", "知幾筆記" in r.get_data(as_text=True), True)

r = client.get("/api/health")
check("health 200", r.status_code, 200)
check("health ok", r.get_json().get("ok"), True)
check("health 有 llm", "llm" in r.get_json(), True)

r = client.get("/api/providers")
check("providers 200", r.status_code, 200)
check("providers 非空", bool(r.get_json().get("providers")), True)

r = client.get("/api/settings")
check("settings 200", r.status_code, 200)
check("settings ok", r.get_json().get("ok"), True)

r = client.get("/api/glossary")
check("glossary 200", r.status_code, 200)
check("glossary 非空", bool(r.get_json().get("glossary")), True)

r = client.post("/api/cast", json={
    "question": "部署測試",
    "hexagram": "地澤臨",
    "moving": [2],
})
check("cast 200", r.status_code, 200)
board = r.get_json().get("board") or {}
check("cast 有卦", board.get("hexagram"), "地澤臨")
check("cast 有變卦", board.get("changed_hexagram"), "地雷復")

r = client.post("/api/preview", json={"board": board, "question": "部署測試"})
check("preview 200", r.status_code, 200)
system = r.get_json().get("system") or ""
check("preview 有角色", system.startswith("你是一位精研六爻十年的占卜師，以繁體中文為人斷卦。"), True)
check("preview 有規則 13", "三合局必須符合成局位置" in system, True)
check("preview 無奔走", "奔走" not in system, True)
check("preview 無破折號", "—" not in (r.get_json().get("user") or ""), True)

r = client.get("/api/nope")
check("未知 API 404", r.status_code, 404)
check("未知 API JSON", r.get_json().get("ok"), False)

# SSE：用假 LLM，確認串流格式與事件（不呼叫真實 API）
from unittest.mock import patch  # noqa: E402


class _FakeCfg:
    spec = {"label": "Fake", "env_key": "FAKE_KEY"}
    model = "fake-model"

    def configured(self):
        return True


with patch("ai.wsgi.llm.LLMConfig.load", return_value=_FakeCfg()), \
        patch("ai.wsgi.llm.stream_chat", return_value=iter(["你", "好"])):
    r = client.post("/api/read", json={"board": board, "question": "部署測試"})
    text = r.get_data(as_text=True)
    check("SSE 200", r.status_code, 200)
    check("SSE content-type", r.content_type.startswith("text/event-stream"), True)
    check("SSE 有 delta", "event: delta" in text, True)
    check("SSE 有 done", "event: done" in text, True)
    check("SSE 中文內容", "你" in text and "好" in text, True)

print()
if fails:
    print(f"❌ {len(fails)} 項失敗")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ WSGI 全部通過")
