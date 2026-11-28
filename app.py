"""Vercel 部署入口：把整個 Flask app 當成單一 Function。

Vercel 的 Flask preset 會從根目錄 `app.py` 尋找名為 `app` 的 Flask 實例。
所有 `/api/*` 路由交給 `ai/wsgi.py` 的 Flask app 處理；靜態檔由 `public/`
目錄交給 Vercel CDN。這樣 13 個舊的 `api/*.py` wrapper 可以全部移除，
Functions 數量由 13 降為 1，符合 Hobby 方案 12 個的上限。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "ai"))

from wsgi import app  # noqa: E402,F401
