#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  六爻 AI · 繁體版 — macOS / Linux 啟動腳本
# ═══════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

VENV_PY="../.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    if command -v python3 >/dev/null 2>&1; then
        VENV_PY="python3"
    else
        echo "找不到 Python，請先安裝 Python 3.9+"
        exit 1
    fi
fi

PORT="${LIUYAO_PORT:-8848}"
echo
echo "  正在啟動六爻 AI ..."
echo

# 兩秒後自動開瀏覽器（Linux / macOS）
( sleep 2; command -v open >/dev/null 2>&1 && open "http://127.0.0.1:${PORT}/" || \
  command -v xdg-open >/dev/null 2>&1 && xdg-open "http://127.0.0.1:${PORT}/" ) &

exec "$VENV_PY" server.py
