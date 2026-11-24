#!/usr/bin/env python3
"""新卦鷹架：自動排盤 + 取卦辭爻辭 + 生成卦例JSON骨架 + 列印推理brief。

分工：
  - 機械層（排盤、卦辭爻辭、JSON結構、關鍵判定摘要）→ 由本指令碼自動完成。
  - 推理層（卦象/動爻講解、分層解析、斷語、應期、發展推演）→ 交給 LLM。
    本指令碼會列印一份「排盤摘要 + 推理 prompt」作為 LLM 的輸入；
    LLM 據此推理、填好 JSON 的 overview.gua_explanation / sections / verdict / summary，
    再用 generate_report.py 生成報告。

示例：
  python tools/new_case.py --hexagram 雷水解 --moving 3 --month 申 --day 甲子 \\
      --question "占求職能否成" --yongshen 官鬼 --title 求職 -o examples/02-求職.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from liuyao import cast_board, format_board
from liuyao.format import yao_name

ROOT = Path(__file__).resolve().parent.parent
ZHOUYI = json.loads(ROOT.joinpath("data", "zhouyi.json").read_text(encoding="utf-8"))

DISCLAIMER = ("六爻為傳統文化與占卜術，非科學。斷的是「勢、象、時機」，非事實預測。"
              "重大決策須以現實理性判斷為準，占卜結果僅作參考。")


def build_overview(board):
    """從 zhouyi.json 自動取主卦/變卦卦辭、動爻爻辭；講解欄位留空待 LLM。"""
    def gua_ci(gname, prefix):
        ci = ZHOUYI.get(gname, {}).get("gua_ci", "")
        return {"label": f"{prefix} · {gname}", "text": ci, "note": ""} if ci else None

    items = [gua_ci(board.hexagram, "主卦")]
    if board.changed_hexagram:
        items.append(gua_ci(board.changed_hexagram, "變卦"))
    gua_ci_list = [x for x in items if x]

    yao_ci_list = []
    main_yao = ZHOUYI.get(board.hexagram, {}).get("yao", {})
    for ln in board.moving_lines:
        pos_name = yao_name(ln.position, ln.yin_yang)
        text = main_yao.get(pos_name, "")
        if text:
            yao_ci_list.append({
                "label": f"動爻 · {board.hexagram} {pos_name}",
                "text": f"{pos_name}：{text}",
                "note": "",
            })
    return {"gua_ci": gua_ci_list, "yao_ci": yao_ci_list,
            "gua_explanation": "", "moving_explanation": ""}


def brief(board, output):
    """列印排盤 + 關鍵判定 + 推理 prompt（LLM 據此發揮）。"""
    L = [format_board(board), "", "===== 關鍵判定（引擎已算，供推理參考）====="]
    if board.yongshen_wx:
        L.append(f"用神：{board.yongshen_qin}（五行 {board.yongshen_wx}）")
        for ln in board.lines:
            if ln.role and ln.role != "閒神":
                extra = ""
                if ln.role in ("元神", "忌神"):
                    eff = "有力" if ln.effective else ("無力" if ln.effective is False else "中和")
                    extra = f" → {eff}（{ln.effective_reason}）"
                L.append(f"  {yao_name(ln.position, ln.yin_yang)} {ln.qin} {ln.gan}{ln.zhi}：{ln.role}{extra}")
    for ln in board.moving_lines:
        L.append(f"動爻 {yao_name(ln.position, ln.yin_yang)} {ln.gan}{ln.zhi} → "
                 f"{ln.change_gan}{ln.change_zhi}（{ln.jin_tui}）")
    for ln in board.lines:
        if ln.dark_move:
            L.append(f"暗動 {yao_name(ln.position, ln.yin_yang)} {ln.gan}{ln.zhi}（{ln.role}）")
    flags = []
    if board.is_liuhe_gua: flags.append("主卦·六合卦")
    if board.is_liuchong_gua: flags.append("主卦·六沖卦")
    if board.changed_is_liuhe: flags.append("變卦·六合卦")
    if board.changed_is_liuchong: flags.append("變卦·六沖卦")
    if board.fu_yin: flags.append("伏吟")
    if board.fan_yin: flags.append("反吟")
    if board.gua_bian and board.gua_bian != "變卦未明": flags.append(board.gua_bian)
    if flags: L.append("卦級：" + "，".join(flags))
    for k, v in board.sanhe.items():
        L.append(f"三合 {k}：{v['status']}（動爻 {v['moving_count']}）")

    L += ["", "===== 推理 prompt（交 LLM 發揮）=====",
          "請依 SKILL.md 八步流程（取用神→旺衰→世爻→動靜暗破→化變合墓→綜合定性→應期），"
          "結合上面排盤，推理並填寫卦例 JSON：",
          "  overview.gua_explanation  卦象講解（主→變寓意）",
          "  overview.moving_explanation  動爻講解（為何是樞紐/病灶）",
          "  sections  分層解析卡片（用神/世爻/元神暗動/三合/六神/空亡/卦意/應期…）",
          "  verdict  完整斷語（含發展推演與應期辯證）",
          "  summary  一句話總結",
          "關鍵辨析：暗動≠日破、貴≠旺、虛合待用、空墓出墓、元忌有力無力、沖墓雙向。",
          f"填好後生成報告：python tools/generate_report.py {output} -o outputs/report.html"]
    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(description="新卦鷹架：排盤+卦辭+JSON骨架+推理brief")
    p.add_argument("--hexagram", required=True, help="主卦名（如 雷水解 / 解）")
    p.add_argument("--moving", required=True, help="動爻，如 3 或 2,4")
    p.add_argument("--month", required=True, help="月建（地支如 申，或干支如 庚申）")
    p.add_argument("--day", required=True, help="日干支（兩天字元，如 甲子）")
    p.add_argument("--question", required=True, help="所占之事")
    p.add_argument("--yongshen", required=True, help="用神六親（如 官鬼/妻財）")
    p.add_argument("--year", default="", help="年干支（如 丙午）")
    p.add_argument("--title", default=None, help="卦例標題（預設取問事）")
    p.add_argument("--background", default="", help="背景說明")
    p.add_argument("-o", "--output", default=None, help="輸出 JSON 路徑")
    args = p.parse_args()

    moving = [int(x.strip()) for x in str(args.moving).split(",") if x.strip()]
    month_zhi = args.month[-1]  # 末字為月支
    board = cast_board(args.hexagram, moving, month_zhi, args.day, args.yongshen)

    output = args.output or str(ROOT / "examples" / "new-case.json")
    output_path = Path(output)
    moving_desc = "".join(yao_name(m, board.line(m).yin_yang) for m in moving)

    case = {
        "id": output_path.stem,
        "title": args.title or args.question[:10],
        "subtitle": f"{board.hexagram} · {moving_desc}動 · 變{board.changed_hexagram}",
        "meta": {
            "year": args.year, "month": args.month, "day": args.day,
            "xunkong": "、".join(board.xunkong),
            "question": args.question, "background": args.background,
        },
        "board": {
            "hexagram": args.hexagram, "moving": moving,
            "month_zhi": month_zhi, "day_gz": args.day, "yongshen": args.yongshen,
        },
        "overview": build_overview(board),
        "sections": [
            {"title": "（待 LLM 填寫）分層解析", "subtitle": "", "paragraphs": [""]},
        ],
        "verdict": ["（待 LLM 填寫）完整斷語"],
        "summary": "（待 LLM 填寫）一句話總結",
        "disclaimer": DISCLAIMER,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已生成卦例骨架：{output_path}\n")
    print(brief(board, output))


if __name__ == "__main__":
    main()
