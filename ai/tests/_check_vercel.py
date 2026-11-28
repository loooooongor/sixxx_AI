"""檢查 Vercel 的單一 Flask Function 與 public/ 靜態檔。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
ROOT = AI_DIR.parent
for p in (str(ROOT), str(AI_DIR), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from werkzeug.test import Client  # noqa: E402

from ai.wsgi import app as flask_app  # noqa: E402

fails = []


def check(name: str, got, want=True) -> None:
    ok = got == want
    if not ok:
        fails.append(f"{name}: got={got!r} want={want!r}")
    print(("OK   " if ok else "FAIL ") + f"{name}: {got}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


for rel in ("index.html", "pricing.html", "billing-success.html",
            "robots.txt",
            "assets/app.css", "assets/app.js",
            "assets/coin-front.png", "assets/coin-back.png",
            "assets/coin-front.webp", "assets/coin-back.webp"):
    src = AI_DIR / "web" / rel
    dst = ROOT / "public" / rel
    check(f"public/{rel} 存在", dst.is_file(), True)
    if dst.is_file():
        check(f"public/{rel} 與 ai/web 同步", digest(dst), digest(src))

index_html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
check("public 首頁有品牌", "知幾筆記" in index_html, True)

print("\n=== SEO 基本條件 ===")
title = re.search(r"<title>(.*?)</title>", index_html)
check("title 有卦師訓練定位", bool(title and "執業卦師訓練" in title.group(1)), True)
desc = re.search(r'name="description" content="(.*?)"', index_html)
check("有 meta description", bool(desc), True)
if desc:
    check("description 長度 60–120", 60 <= len(desc.group(1)) <= 120, True)
check("唯一 h1", len(re.findall(r"<h1[\s>]", index_html)), 1)
check("內容區 h1 有主關鍵字", "執業卦師訓練的 AI 六爻解讀" in index_html, True)
check("FAQ 為靜態 HTML", index_html.count("<details"), 8)
faq_ld = [b for b in re.findall(
    r'<script type="application/ld\+json">(.*?)</script>', index_html, re.S)
    if '"FAQPage"' in b]
check("有 FAQPage JSON-LD", len(faq_ld), 1)
if faq_ld:
    data = json.loads(faq_ld[0])
    check("FAQPage 有 8 條", len(data.get("mainEntity", [])), 8)
check("robots 禁止爬 /api", "Disallow: /api/" in
      (ROOT / "public" / "robots.txt").read_text(encoding="utf-8"), True)

check("app.py 存在", (ROOT / "app.py").is_file(), True)
check("api/ 舊 wrapper 已移除", not (ROOT / "api").exists(), True)

vercel_cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
check("framework 設為 flask", vercel_cfg.get("framework"), "flask")
check("不再用 api functions 設定", "functions" in vercel_cfg, False)
check("已移除 stripe rewrites", vercel_cfg.get("rewrites", []), [])

check("Flask app 可載入", callable(flask_app), True)

r = Client(flask_app).get("/api/health")
check("api.health 200", r.status_code, 200)
check("api.health JSON", json.loads(r.get_data(as_text=True)).get("ok"), True)

payload = json.dumps({"question": "部署測試", "hexagram": "地澤臨", "moving": [2]})
r = Client(flask_app).post("/api/cast", data=payload, content_type="application/json")
data = json.loads(r.get_data(as_text=True))
check("api.cast 200", r.status_code, 200)
check("api.cast 有卦", (data.get("board") or {}).get("hexagram"), "地澤臨")

for path in ("/api/providers", "/api/glossary", "/api/settings"):
    r = Client(flask_app).get(path)
    check(f"{path} 200", r.status_code, 200)

r = Client(flask_app).get("/")
check("首頁 200", r.status_code, 200)
check("首頁有品牌", "知幾" in r.get_data(as_text=True), True)

print()
if fails:
    print(f"❌ {len(fails)} 項失敗")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ Vercel 入口全部通過")
