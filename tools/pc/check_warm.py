# -*- coding: utf-8 -*-
"""미리 데워 두면 누를 때 빨라지는가 — 두 차고지 모두. 복사본에만 쓴다."""
import datetime
import os
import shutil
import sys
import time

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\agent")
sys.path.append(r"D:\프로그램2\꾀꼬리\busyardapp\tools")
import agent  # noqa: E402
import ops_fill  # noqa: E402
import pythoncom  # noqa: E402
import win32com.client  # noqa: E402

agent._data_path = lambda name: os.path.join(r"D:\프로그램2\꾀꼬리\busyardapp\src", name)
agent.log = lambda m: None
agent.notice = lambda *a, **k: type("N", (), {"close": lambda self: None})()

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {label}")
    else:
        fail += 1
        print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")


orig = ops_fill.find_excel(datetime.date(2026, 10, 10))
copy = os.path.join(r"Z:\교통사업처_버스운영센터\상황실\받아쓰기", "데우기.xlsx")
agent.find_excel = lambda date: copy
agent.ops_date = lambda now: datetime.date(2026, 10, 10)

pythoncom.CoInitialize()
times = {}
for yard, count in (("new", 136), ("old", 90)):
    name = "6차고지" if yard == "new" else "1차고지"
    print(f"\n── {name} ──")
    if os.path.exists(copy):
        os.remove(copy)
    shutil.copy2(orig, copy)
    agent._warmed.clear()

    app = win32com.client.DispatchEx("Excel.Application")
    app.Visible = True
    app.DisplayAlerts = False
    wb = app.Workbooks.Open(copy)
    for _ in range(80):
        if app.CalculationState == 0:
            break
        time.sleep(0.25)

    t = time.time()
    warmed = agent.warm_up(log=lambda m: None)
    warm_secs = time.time() - t
    eq(warmed, True, "열려 있으면 미리 데운다")
    print(f"   미리 데우기 {warm_secs:.1f}초 (사람이 기다리지 않는 시간이다)")
    eq(agent.warm_up(log=lambda m: None), False, "하루에 한 번만 데운다")

    board = {"yard": yard, "date": "2026-10-09", "entries": {
        str(i): {"plate": str(1500 + i), "status": "filled", "round": 1} for i in range(1, count + 1)}}
    t = time.time()
    n, was_open = agent.write_board(board, copy, log=lambda m: None)
    secs = time.time() - t
    times[name] = secs
    eq(was_open, True, "열어 둔 그 엑셀에 적는다")
    print(f"   넣기 {secs:.1f}초 ({n}대)")
    eq(secs < 5, True, f"데워 둔 뒤에는 5초 안에 끝난다 (잰 값 {secs:.1f}초)")

    cells = agent.block_cells(yard)
    rc = cells[1]
    eq(wb.Worksheets(agent.SHEET).Cells(rc[0], rc[1]).Value, 1501.0, "첫 자리에 1501")
    eq(bool(app.EnableEvents), True, "이벤트를 도로 켜 둔다")

    wb.Close(SaveChanges=False)
    agent.quit_excel(app, wb)

os.remove(copy)
print(f"\n   6차고지 {times.get('6차고지', 0):.1f}초 · 1차고지 {times.get('1차고지', 0):.1f}초")
print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
