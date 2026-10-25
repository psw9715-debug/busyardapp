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


# ---- 인쇄용 엑셀을 데워 둔다 ----------------------------------------------
#
# 엑셀을 쓸 때마다 새로 띄우면 한 번에 6초가 든다 (띄우기 2.9초 + 여는 데 1.5초 + …).
# 한 번 데워 두고 다시 쓰면 **0.8초**다. 하룻밤에 여러 번 뽑으므로 그만큼 고스란히 번다.
#   잰 값 (2026-10-26) — 새로 띄우기 6.35 / 5.82 / 6.06초, 데운 뒤 1.42 / 0.79 / 0.78초
#
# 보이지 않는 엑셀이 남는 것은 이 프로젝트에서 전에 탈이 난 적이 있다. 그래서
#   · 통합문서는 뽑자마자 닫는다 (파일을 쥐고 있지 않는다)
#   · 한동안 안 쓰면 스스로 내보낸다
#   · 프로그램이 끝날 때도 내보낸다
import atexit
import threading

# COM 개체는 **만든 스레드에서만** 쓸 수 있다. 인쇄는 우편함 감시 스레드에서도,
# 밤 스케줄러 스레드에서도 부르므로, 데운 엑셀은 스레드마다 따로 둔다.
# (하나를 같이 쓰면 다른 스레드에서 RPC_E_WRONG_THREAD 로 터진다.)
_내엑셀 = threading.local()
_모아둔것 = []                  # 끝날 때 내보내려고 모아 둔다
_모음자물쇠 = threading.Lock()


def _엑셀내보내기(앱):
    try:
        앱.Quit()
    except Exception:
        pass


def _데운엑셀():
    """이 스레드의 인쇄용 엑셀. 데워 두고 다시 쓴다. 죽어 있으면 새로 띄운다."""
    import win32com.client
    앱 = getattr(_내엑셀, "앱", None)
    if 앱 is not None:
        try:
            앱.Visible = False          # 살아 있는지 두드려 본다
            return 앱
        except Exception:
            _내엑셀.앱 = None
    # DispatchEx — 열어 둔 엑셀에 붙지 않는다. 붙으면 Quit 할 때 남의 문서까지 닫힌다.
    앱 = win32com.client.DispatchEx("Excel.Application")
    앱.Visible = False
    try:
        앱.DisplayAlerts = False
    except Exception:
        pass
    _내엑셀.앱 = 앱
    with _모음자물쇠:
        _모아둔것.append(앱)
    return 앱


def warm_print_excel():
    """조용한 틈에 미리 데워 둔다. 부른 그 스레드의 것을 데운다. 데웠으면 True.

    첫 인쇄가 느린 것은 엑셀을 띄우는 3초 때문이다. 사람이 기다리지 않는 틈에
    미리 치러 두면 누르는 순간에는 0.8초면 끝난다.
    """
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    try:
        _데운엑셀()
        return True
    except Exception:
        return False


@atexit.register
def _다내보내기():
    with _모음자물쇠:
        남은것, _모아둔것[:] = list(_모아둔것), []
    for 앱 in 남은것:
        _엑셀내보내기(앱)


def print_file(path):
    """엑셀에 맡겨 기본 프린터로 보낸다. 서식·용지 방향이 그대로 나간다."""
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        os.startfile(path, "print")             # pywin32 가 없으면 셸에 맡긴다
        return "셸(기본 프린터)"
    excel = _데운엑셀()
    wb = excel.Workbooks.Open(path)
    try:
        wb.PrintOut()
    finally:
        wb.Close(SaveChanges=False)             # 통합문서만 닫는다 — 엑셀은 데운 채로 둔다
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
