# -*- coding: utf-8 -*-
"""오늘 판을 구차고지 엑셀에 그대로 적어서 기본 프린터로 뽑는다.

브라우저로 종이 모양을 흉내 내면 여백·배율이 프린터마다 어긋난다.
원본 엑셀에 **값만 채워 넣으면** 서식은 손댈 것이 없다 — 가로 방향도,
한 장 맞춤도, 색도 원본 그대로다.

    # 앱 [기록] → [엑셀용으로 복사] 한 것을 붙여넣고
    python tools/print_board.py                 # 클립보드에서 읽어 인쇄
    python tools/print_board.py 오늘.csv        # 파일에서 읽어 인쇄
    python tools/print_board.py --save          # 인쇄하지 않고 파일만 만든다

만들어진 파일은 `out/구차고지 YYYY-MM-DD.xlsx` 로 남는다.
"""
import csv
import datetime
import io
import os
import subprocess
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = os.path.join(ROOT, "reference", "구차고지-순서.xlsx")
PRINT = os.path.join(ROOT, "reference", "구차고지.xlsx")
OUT_DIR = os.path.join(ROOT, "out")


def read_clipboard():
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    finally:
        root.destroy()


def parse_board(text):
    """앱이 내보낸 CSV — 자리,차량번호,출차,비고"""
    board = {}
    for row in csv.reader(io.StringIO(text.strip())):
        if len(row) < 2:
            continue
        spot, value = row[0].strip(), row[1].strip()
        if "-" not in spot or not spot.split("-")[0].isdigit():
            continue                      # 머리글 줄
        board[spot] = value
    if not board:
        raise ValueError("자리를 하나도 못 읽었다 — [기록] → [엑셀용으로 복사] 한 것이 맞는지 확인")
    return board


def spot_cells():
    """자리번호 -> 인쇄 시트에서 값을 적을 셀. 순서 시트가 자리 위치를 안다."""
    ws = openpyxl.load_workbook(ORDER, data_only=True).worksheets[0]
    at = {}
    for rng in ws.merged_cells.ranges:
        v = ws.cell(rng.min_row, rng.min_col).value
        if v is None:
            continue
        v = str(v).strip()
        if "-" in v and v.split("-")[0].isdigit():
            at[v] = (rng.min_row, rng.min_col)
    return at


def fill(board, date):
    at = spot_cells()
    unknown = sorted(set(board) - set(at))
    if unknown:
        print(f"  (배치도에 없는 자리는 건너뛴다: {', '.join(unknown)})")

    wb = openpyxl.load_workbook(PRINT)          # 서식이 살아 있어야 하므로 data_only 를 쓰지 않는다
    ws = wb.worksheets[0]
    n = 0
    for spot, value in board.items():
        if spot not in at or not value:
            continue
        r, c = at[spot]
        ws.cell(r, c).value = value
        n += 1

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"구차고지 {date}.xlsx")
    wb.save(out)
    return out, n


def print_file(path):
    """엑셀에 맡겨 기본 프린터로 보낸다. 서식·용지 방향이 그대로 나간다."""
    try:
        import win32com.client
    except ImportError:
        os.startfile(path, "print")             # pywin32 가 없으면 셸에 맡긴다
        return "셸(기본 프린터)"
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    wb = excel.Workbooks.Open(path)
    try:
        wb.PrintOut()
    finally:
        wb.Close(SaveChanges=False)
        excel.Quit()
    return "엑셀(기본 프린터)"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_print = "--save" not in sys.argv

    if args:
        text = io.open(args[0], encoding="utf-8-sig").read()
    else:
        text = read_clipboard()

    board = parse_board(text)
    date = datetime.date.today().isoformat()
    out, n = fill(board, date)
    print(f"{out} — {n}칸 채웠다")

    if not do_print:
        return 0
    how = print_file(out)
    print(f"  {how} 로 보냈다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
