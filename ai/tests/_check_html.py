"""檢查 HTML 標籤配對（供預覽頁與前端頁面用）。"""

import re
import sys
from pathlib import Path

TAGS = ["div", "section", "aside", "main", "form", "button", "ul", "li",
        "details", "summary", "table", "tr", "td", "th", "p", "h2", "h3",
        "span", "select", "option", "textarea", "nav", "header", "footer",
        "label", "b", "small", "style", "script"]
VOID = ["input", "br", "hr", "img", "meta", "link"]


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "preview.html")
    h = path.read_text(encoding="utf-8")
    bad = 0
    print(f"{'tag':<12}{'open':>6}{'close':>7}")
    for t in TAGS:
        o = len(re.findall(r"<" + t + r"(?=[\s>])", h))
        c = len(re.findall(r"</" + t + r">", h))
        mark = ""
        if o != c:
            mark = "   <-- 不平衡"
            bad += 1
        print(f"{t:<12}{o:>6}{c:>7}{mark}")
    print()
    for t in VOID:
        print(f"{t}(void)：{len(re.findall(chr(60) + t + r'(?=[\s>/])', h))}")
    print()
    if bad:
        print(f"❌ {bad} 個標籤不平衡")
        return 1
    print("✅ 全部標籤平衡")
    return 0


if __name__ == "__main__":
    sys.exit(main())
