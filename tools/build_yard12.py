# -*- coding: utf-8 -*-
"""구차고지 엑셀 -> src/guide/yard12-data.js

두 파일을 합쳐 하나로 만든다.
- `구차고지-순서.xlsx` : 자리번호가 적힌 시트. 배정 순서와 자리 수는 여기가 정한다.
- `구차고지.xlsx`      : 실제로 손으로 적는 인쇄용 시트. 색·테두리·라벨을 여기서 가져온다.

자리 한 칸 = 엑셀 세로 3행 블록이다.
  그리드 행 = (엑셀행 - 1) / 3 + 1   (1..12)
  그리드 열 = 엑셀 열 번호            (1..15, A..O)
"""
import json
import openpyxl
from openpyxl.utils import get_column_letter as col_letter

from xlsx_color import load_theme, cell_bg, border_weights

XLSX = "reference/구차고지-순서.xlsx"
PRINT_XLSX = "reference/구차고지.xlsx"
OUT = "src/guide/yard12-data.js"

# 엑셀 블록 시작행 -> (차고지, 줄)
BLOCKS = {
    9:  ("2", "lane3"),
    12: ("2", "lane2"),
    15: ("2", "lane1"),
    23: ("1", "rear"),
    29: ("1", "even"),
    32: ("1", "odd"),
}
RESERVED = {"1015": "1-41", "1016": "1-42"}


def read_rows(ws):
    """블록마다 엑셀에 적힌 좌->우 순서로 자리번호를 모은다."""
    top = {(r.min_row, r.min_col) for r in ws.merged_cells.ranges}
    rows = {}
    for row, (yard, line) in BLOCKS.items():
        spots = []
        for col in range(1, ws.max_column + 1):
            if (row, col) not in top:
                continue
            v = ws.cell(row, col).value
            if v is None:
                continue
            v = str(v).strip()
            if v.startswith(yard + "-"):
                spots.append(v)
        rows[line] = spots
    return rows


def num(spot):
    return int(spot.split("-")[1])


def grid_row(excel_row):
    return (excel_row - 1) // 3 + 1


def print_cells(ws, wp):
    """인쇄용 격자. 종이와 같은 모양이 되도록 병합·색·테두리를 그대로 옮긴다."""
    theme = load_theme(PRINT_XLSX)
    cells, taken = [], set()

    for rng in sorted(ws.merged_cells.ranges, key=lambda r: (r.min_row, r.min_col)):
        value = ws.cell(rng.min_row, rng.min_col).value
        c = {
            "col": rng.min_col,
            "colspan": rng.max_col - rng.min_col + 1,
            "row": grid_row(rng.min_row),
            "rowspan": max(1, (rng.max_row - rng.min_row + 1) // 3),
            "xl": col_letter(rng.min_col) + str(rng.min_row),
        }
        bg = cell_bg(wp.cell(rng.min_row, rng.min_col), theme)
        if bg:
            c["bg"] = bg
        c["b"] = border_weights(wp, rng.min_row, rng.min_col, rng.max_row, rng.max_col)

        text = None if value is None else str(value).strip()
        if text and "-" in text and text.split("-")[0].isdigit():
            c["kind"], c["spot"] = "spot", text
        elif text:
            c["kind"], c["text"] = "label", text
        else:
            # 순서 시트가 비어 있어도 인쇄 시트에 라벨이 있을 수 있다 (예비·민노 등)
            pv = wp.cell(rng.min_row, rng.min_col).value
            if pv is not None and str(pv).strip():
                c["kind"], c["text"] = "label", str(pv).strip()
            else:
                c["kind"] = "void"
        cells.append(c)
        for dr in range(c["rowspan"]):
            for dc in range(c["colspan"]):
                taken.add((c["row"] + dr, c["col"] + dc))

    # 병합에 안 든 나머지 — 색만 칠해진 구역 표시가 여기 있다
    for excel_row in range(1, 35, 3):
        row = grid_row(excel_row)
        for col in range(1, 16):
            if (row, col) in taken:
                continue
            v = wp.cell(excel_row, col).value
            bg = cell_bg(wp.cell(excel_row, col), theme)
            b = border_weights(wp, excel_row, col, excel_row + 2, col)
            if v is None and not bg and not any(b):
                continue
            c = {"col": col, "colspan": 1, "row": row, "rowspan": 1,
                 "xl": col_letter(col) + str(excel_row), "b": b,
                 "kind": "label" if v is not None else "plain"}
            if v is not None:
                c["text"] = str(v).strip()
            if bg:
                c["bg"] = bg
            cells.append(c)

    cells.sort(key=lambda c: (c["row"], c["col"]))
    return cells


def main():
    ws = openpyxl.load_workbook(XLSX, data_only=True).worksheets[0]
    r = read_rows(ws)

    # 1차고지 — 출차는 번호 오름차순으로 채운다 (1-1 앞줄, 1-2 뒷줄, 1-3 앞줄 …)
    seq = sorted(r["odd"] + r["even"], key=num)
    rear = sorted(r["rear"], key=num)

    assert [num(s) for s in seq] == list(range(1, len(seq) + 1)), "1차고지 순번행이 1부터 연속이 아니다"
    assert [num(s) for s in rear] == list(range(len(seq) + 1, len(seq) + 1 + len(rear))), \
        "1차고지 맨 뒷열이 순번행 뒤로 연속이 아니다"
    for spot in RESERVED.values():
        assert spot in rear, f"전용칸 {spot} 이 맨 뒷열에 없다"

    # 2차고지 — 엑셀은 오른쪽이 2-1 이므로 뒤집어 채우는 순서로 만든다.
    #            예비칸(2-27·2-28)은 줄 끝에 붙어 있어 번호로 갈린다.
    lanes, spare = {}, {}
    for i, line in enumerate(("lane1", "lane2", "lane3"), start=1):
        spots = sorted(r[line], key=num)
        head = [s for s in spots if num(s) <= 26]
        tail = [s for s in spots if num(s) > 26]
        assert len(tail) <= 1, f"{line} 에 예비칸이 둘 이상"
        lanes[i] = head
        if tail:
            spare[i] = tail[0]

    total = len(seq) + len(rear) + sum(len(v) for v in lanes.values()) + len(spare)

    wp = openpyxl.load_workbook(PRINT_XLSX).worksheets[0]
    cells = print_cells(ws, wp)
    printed = {c["spot"] for c in cells if c["kind"] == "spot"}
    ours = set(seq) | set(rear) | {s for v in lanes.values() for s in v} | set(spare.values())
    missing = ours - printed
    assert not missing, f"인쇄 격자에 빠진 자리: {sorted(missing)}"

    data = {
        "yard1": {"seq": seq, "rear": rear, "reserved": RESERVED},
        "yard2": {"lanes": lanes, "spare": spare},
        "print": {"cols": 15, "rows": 12, "wideCol": 1, "cells": cells},
    }

    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// 자동 생성 파일 — 직접 수정하지 말 것. `python tools/build_yard12.py` 로 재생성.\n")
        f.write("export const YARD12 = " + body + ";\n")

    kinds = {}
    for c in cells:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(f"{OUT} 생성 완료 — 1차고지 순번 {len(seq)} + 뒷열 {len(rear)}, "
          f"2차고지 {[len(lanes[i]) for i in (1,2,3)]} + 예비 {sorted(spare.values())}, 합계 {total}칸")
    print(f"  인쇄 격자 {len(cells)}칸 — {kinds}")


if __name__ == "__main__":
    main()
