"""檢查 Vercel 的 api/*.py functions 與 public/ 靜態檔。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
ROOT = AI_DIR.parent
for p in (str(ROOT), str(AI_DIR), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from werkzeug.test import Client  # noqa: E402

import api.cast as api_cast  # noqa: E402
import api.health as api_health  # noqa: E402

fails = []


def check(name: str, got, want=True) -> None:
    ok = got == want
    if not ok:
        fails.append(f"{name}: got={got!r} want={want!r}")
    print(("OK   " if ok else "FAIL ") + f"{name}: {got}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


for rel in ("index.html", "pricing.html", "billing-success.html",
            "assets/app.css", "assets/app.js"):
    src = AI_DIR / "web" / rel
    dst = ROOT / "public" / rel
    check(f"public/{rel} 存在", dst.is_file(), True)
    if dst.is_file():
        check(f"public/{rel} 與 ai/web 同步", digest(dst), digest(src))

check("public 首頁有品牌", "知幾筆記" in (ROOT / "public" / "index.html").read_text(encoding="utf-8"), True)

check("api.cast 有 WSGI app", callable(api_cast.app), True)
check("api.health 有 WSGI app", callable(api_health.app), True)

r = Client(api_health.app).get("/")
check("api.health 200", r.status_code, 200)
check("api.health JSON", json.loads(r.get_data(as_text=True)).get("ok"), True)

payload = json.dumps({"question": "部署測試", "hexagram": "地澤臨", "moving": [2]})
r = Client(api_cast.app).post("/", data=payload, content_type="application/json")
data = json.loads(r.get_data(as_text=True))
check("api.cast 200", r.status_code, 200)
check("api.cast 有卦", (data.get("board") or {}).get("hexagram"), "地澤臨")

print()
if fails:
    print(f"❌ {len(fails)} 項失敗")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ Vercel 入口全部通過")
