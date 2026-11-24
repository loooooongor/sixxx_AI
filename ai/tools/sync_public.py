"""把 ai/web 的前端檔案同步到 Vercel 的 public/。

Vercel 會把 public/ 當成靜態網站根目錄；API 由 api/*.py 的
Python functions 提供。每次改前端後執行：

    python ai/tools/sync_public.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "ai" / "web"
DST = ROOT / "public"


def main() -> int:
    if not (SRC / "index.html").is_file():
        print(f"找不到前端：{SRC}")
        return 1
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    shutil.copy2(SRC / "index.html", DST / "index.html")
    shutil.copytree(SRC / "assets", DST / "assets")
    print(f"已同步 {SRC} → {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
