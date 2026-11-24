"""一鍵跑完六爻 AI 的全部驗證。

用法（需先啟動伺服器：python server.py）::

    python tests/run_all.py

可分項執行::

    python tests/run_all.py calendar divination     # 只跑這兩項

項目：
    calendar    曆法精算（55+ 項，不需伺服器）
    divination  起卦與卦盤（不需伺服器）
    render      前端渲染（Node，不需伺服器）
    lock        一卦只起一次（需伺服器）
    api         API 端到端（需伺服器）
    stream      SSE 串流（需伺服器 + 自動起假 LLM）
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
ROOT = AI_DIR.parent

#: 驗證項目：(名稱, 指令, 需要的伺服器, 說明)
ITEMS = {
    "calendar": ([sys.executable, str(HERE / "_check_calendar.py")], False,
                 "曆法精算"),
    "divination": ([sys.executable, str(HERE / "_check_divination.py")], False,
                   "起卦與卦盤"),
    "render": (["node", str(HERE / "_check_render.js")], False, "前端渲染"),
    "lock": ([sys.executable, str(HERE / "_check_board_lock.py")], True,
             "一卦只起一次"),
    "api": ([sys.executable, str(HERE / "_check_api.py")], True, "API 端到端"),
    "wsgi": ([sys.executable, str(HERE / "_check_wsgi.py")], False, "Vercel WSGI"),
    "stream": ([sys.executable, str(HERE / "_check_stream.py")], True, "SSE 串流"),
}


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def env() -> dict:
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    paths = [str(ROOT / "src"), str(AI_DIR)]
    e["PYTHONPATH"] = os.pathsep.join(paths + ([e["PYTHONPATH"]] if e.get("PYTHONPATH") else []))
    return e


def run(name: str) -> tuple[bool, str]:
    cmd, needs_server, label = ITEMS[name]
    if needs_server and not port_open(8848):
        return False, f"{label}：伺服器未啟動（請先 python server.py）"
    t0 = time.time()
    cp = subprocess.run(cmd, cwd=str(HERE), env=env(), text=True,
                        encoding="utf-8", errors="replace",
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = cp.stdout or ""
    tail = "\n".join(
        ln for ln in out.strip().splitlines()
        if ln.startswith(("FAIL", "❌", "  -", "✅")) or "Traceback" in ln
    )[-1200:]
    ok = cp.returncode == 0 and "✅" in out
    dur = time.time() - t0
    return ok, f"{label}（{dur:.1f}s）{'\n' + tail if not ok else ''}"


def main() -> int:
    wanted = [a for a in sys.argv[1:] if a in ITEMS] or list(ITEMS)
    unknown = [a for a in sys.argv[1:] if a not in ITEMS]
    if unknown:
        print(f"未知項目：{'、'.join(unknown)}")
        print(f"可用：{'、'.join(ITEMS)}")
        return 2

    mocks = []
    if "stream" in wanted and port_open(8848):
        # 正常回應的假 LLM（8901）與認證失敗的假 LLM（8902）
        for port, mode in ((8901, "ok"), (8902, "auth_fail")):
            if port_open(port):
                continue
            mocks.append(subprocess.Popen(
                [sys.executable, str(HERE / "_mock_llm.py"), str(port), mode],
                cwd=str(HERE), env=env(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            for _ in range(40):
                if port_open(port):
                    break
                time.sleep(0.1)

    results = []
    try:
        print("=" * 62)
        print("  六爻 AI · 驗證總測")
        print("=" * 62)
        for name in wanted:
            ok, msg = run(name)
            results.append((name, ok, msg))
            print(f"{'✅' if ok else '❌'} {msg}")
    finally:
        for m in mocks:
            m.terminate()
            try:
                m.wait(timeout=5)
            except subprocess.TimeoutExpired:
                m.kill()

    failed = [r for r in results if not r[1]]
    print("=" * 62)
    if failed:
        print(f"❌ {len(failed)}/{len(results)} 項失敗")
        return 1
    print(f"✅ 全部 {len(results)} 項通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
