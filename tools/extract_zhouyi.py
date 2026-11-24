#!/usr/bin/env python3
"""從《易經六十四卦》整理稿提取卦辭、爻辭原文 → data/zhouyi.json。

整理稿用顏色標註：紅色 <font color="#ff0000"> 為卦辭/爻辭原文；綠色為《彖》《象》
傳及解讀，不取。爻辭按爻位(初九/九二/…/上九/初六/…/用九/用六)識別；卦辭取每卦
首個"X：…"式短句。

用法（專案根目錄；母稿已不在 repo 內，需自備該檔路徑）：
    python tools/extract_zhouyi.py <易經六十四卦.md 路徑>
"""

import json
import re
import sys
from pathlib import Path

RED = re.compile(r'<font color="#ff0000">(.*?)</font>', re.S)
YAO_KW = ["初九", "九二", "九三", "九四", "九五", "上九",
          "初六", "六二", "六三", "六四", "六五", "上六", "用九", "用六"]
YAO_RE = re.compile(r"^(" + "|".join(YAO_KW) + r")[：:]")
GUACI_HEAD = re.compile(r"^.{1,3}[：:]")


def _strip_text(s):
    return re.sub(r"</?font[^>]*>", "", s).strip()


# 個別卦辭源稿未單獨標紅，補公有領域《周易》原文（不帶卦名字首，與指令碼風格一致）
GUACI_OVERRIDES = {
    "山澤損": "有孚，元吉，無咎，可貞，利有攸往。曷之？二簋可用享。",
}


def extract(src_path):
    text = Path(src_path).read_text(encoding="utf-8")
    result = {}
    for part in re.split(r"\n(?=## 《)", text):
        gm = re.match(r"## 《(.+?)》", part.strip())
        if not gm:
            continue
        name = gm.group(1).strip()
        # 只取"人間道"段，排除"文言曰"等，避免文言內容汙染爻辭
        seg = part
        sm = re.search(r"### 人間道", part)
        if sm:
            seg = part[sm.end():]
            nxt = re.search(r"\n### ", seg)
            if nxt:
                seg = seg[:nxt.start()]
        reds = [r for r in (_strip_text(x) for x in RED.findall(seg)) if r]
        gua_ci = ""
        yao = {}
        # 卦辭：人間道段首條紅色。相容三種格式：
        #   "X：內容"（取內容）、純字首"X："（取下一段）、無字首直接內容（整條取）
        if reds and not YAO_RE.match(reds[0]):
            first = reds[0]
            cm = re.match(r"^(.{1,3})[：:](.*)$", first, re.S)
            if cm:
                gua_ci = cm.group(2).strip()
                if not gua_ci and len(reds) > 1 and not YAO_RE.match(reds[1]):
                    gua_ci = reds[1]   # 純字首"X："後跟卦辭內容
                # 若後跟爻辭，說明卦辭內容源稿未標紅 → 留空
            else:
                gua_ci = first
        # 爻辭
        for r in reds:
            ym = YAO_RE.match(r)
            if ym and ym.group(1) not in yao:
                yao[ym.group(1)] = r.split("：", 1)[1].strip() if "：" in r else r
        result[name] = {"gua_ci": gua_ci or GUACI_OVERRIDES.get(name, ""), "yao": yao}
    return result


def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法：python tools/extract_zhouyi.py <易經六十四卦.md 路徑>")
    src = sys.argv[1]
    data = extract(src)
    out = Path("data/zhouyi.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n_gua = len(data)
    n_ci = sum(1 for v in data.values() if v["gua_ci"])
    n_yao = sum(len(v["yao"]) for v in data.values())
    miss_gua = [k for k, v in data.items() if not v["gua_ci"]]
    print(f"提取 {n_gua} 卦：卦辭 {n_ci}、爻辭 {n_yao}")
    if miss_gua:
        print(f"⚠️ 卦辭缺失({len(miss_gua)})：{miss_gua[:10]}")


if __name__ == "__main__":
    main()
