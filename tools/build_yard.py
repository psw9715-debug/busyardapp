# -*- coding: utf-8 -*-
"""차고지 프린트.xlsx -> src/yard-data.js

신차고지-순서 시트의 병합 셀을 읽어 배치도 그리드 데이터를 생성한다.
- 자리 한 칸 = 엑셀 세로 3행 병합 블록
- 그리드 행 = (엑셀행 - 3) / 3 + 1   (1..20)
- 그리드 열 = 엑셀 열 번호            (1..15, A..O)
"""
import json
import openpyxl
from openpyxl.utils import get_column_letter as col_letter

XLSX = "reference/차고지 프린트.xlsx"
OUT = "src/yard-data.js"

ORDER_SHEET = "신차고지-순서"   # 순회 번호가 적힌 시트
PRINT_SHEET = "신차고지"        # 주차장 바닥 고정번호가 적힌 시트


def grid_row(excel_row):
    return (excel_row - 3) // 3 + 1


def join_label(text):
    """원본에서 줄바꿈된 라벨을 한 줄로 합친다.

    "수\\n소\\n차\\n고\\n지" 는 세로로 쓴 한 단어이므로 그냥 붙이고,
    "B2\\nB4" 는 별개의 두 표지라 구분자를 넣는다.
    """
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) <= 1:
        return text.replace("\n", "")
    sep = "/" if all(ln.strip().isalnum() and ln.isascii() for ln in lines) else ""
    return sep.join(ln.strip() for ln in lines)


def main():
    wb = openpyxl.load_workbook(XLSX)
    ws = wb[ORDER_SHEET]
    wp = wb[PRINT_SHEET]

    # 인쇄 시트의 고정번호 라벨 (L열 3~23행, M열 24~62행)
    painted = {}
    for r in range(3, 63, 3):
        for c in (12, 13):
            v = wp.cell(r, c).value
            if v is not None:
                painted[col_letter(c) + str(r)] = v

    cells = []
    for rng in ws.merged_cells.ranges:
        if rng.min_row < 3:
            continue  # 1~2행은 제목
        value = ws.cell(rng.min_row, rng.min_col).value
        cell = {
            "col": rng.min_col,
            "colspan": rng.max_col - rng.min_col + 1,
            "row": grid_row(rng.min_row),
            "rowspan": (rng.max_row - rng.min_row + 1) // 3,
            "xl": col_letter(rng.min_col) + str(rng.min_row),
        }

        if isinstance(value, int):
            cell["kind"] = "spot"
            cell["spot"] = value
        elif value is not None:
            cell["kind"] = "label"
            cell["text"] = join_label(str(value))
        elif cell["col"] == 12 and cell["row"] >= 8:
            # L열 하단 13칸: 바닥에 적힌 고정번호일 뿐 순회 대상 아님
            cell["kind"] = "skip"
            cell["text"] = str(painted.get(col_letter(13) + str((cell["row"] - 1) * 3 + 3), ""))
        else:
            cell["kind"] = "void"
        cells.append(cell)

    cells.sort(key=lambda c: (c["row"], c["col"]))
    spots = sorted(c["spot"] for c in cells if c["kind"] == "spot")

    assert spots == list(range(1, 110)), f"순회 번호가 1~109 연속이 아님: {spots[:5]}...{spots[-5:]}"

    data = {
        "id": "new",
        "name": "6차고지 (신차고지)",
        "cols": 15,
        "rows": 20,
        "wideCol": 1,        # A열은 원본에서 폭이 2배 이상
        "totalSpots": len(spots),
        "cells": cells,
    }

    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// 자동 생성 파일 — 직접 수정하지 말 것. `python tools/build_yard.py` 로 재생성.\n")
        f.write("export const YARD = " + body + ";\n")

    kinds = {}
    for c in cells:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(f"{OUT} 생성 완료 — {kinds}")


if __name__ == "__main__":
    main()
