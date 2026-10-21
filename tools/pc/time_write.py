# -*- coding: utf-8 -*-
"""엑셀에 적는 7.9초가 어디에 쓰이는지 쪼개 잰다. 복사본에만 쓴다.

    py tools\\pc\\time_write.py
"""
import datetime
import json
import os
import shutil
import sys
import time

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\agent")
sys.path.append(r"D:\프로그램2\꾀꼬리\busyardapp\tools")
import agent  # noqa: E402
import ops_fill  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
agent._data_path = lambda name: os.path.join(r"D:\프로그램2\꾀꼬리\busyardapp\src", name)
agent.log = lambda m: None
agent.notice = lambda *a, **k: None

YARD = "new"
원본 = ops_fill.find_excel(datetime.date(2026, 10, 10))
복사본 = os.path.join(os.environ["TEMP"], "시간재기_" + os.path.basename(원본))
shutil.copy2(원본, 복사본)
print("복사본:", os.path.basename(복사본))

cells = agent.block_cells(YARD)
판 = {"yard": YARD, "date": "2026-10-09", "entries": {
    str(n): {"plate": str(1500 + (n % 90) + 1), "status": "filled"} for n in list(cells)[:121]}}

import pythoncom, win32com.client  # noqa: E402
pythoncom.CoInitialize()

t0 = time.time()
excel = win32com.client.DispatchEx("Excel.Application")
excel.Visible = False
excel.DisplayAlerts = False
wb = excel.Workbooks.Open(복사본, UpdateLinks=0)
print("  열기                 %5.2f초" % (time.time() - t0))

# 하루 한 번 치르는 '계산 방식 첫 전환' 은 미리 치러 둔다 (warm_up 이 하는 일)
t = time.time()
옛계산 = excel.Calculation
excel.Calculation = -4135
excel.Calculation = 옛계산
print("  계산방식 첫 전환      %5.2f초  (하루 한 번, warm_up 이 미리 치름)" % (time.time() - t))

want = {rc: None for rc in cells.values()}
칸수 = 0
for spot, e in 판["entries"].items():
    rc = cells.get(int(spot))
    if rc:
        want[rc] = int(e["plate"])
        칸수 += 1
묶음 = list(agent.runs(want))
print("  적을 칸 %d개, 묶음 %d번 (묶음 하나가 COM 한 번)" % (칸수, len(묶음)))

ws = wb.Worksheets(agent.SHEET)

t = time.time()
agent.wait_ready(lambda: wb.Name, "확인", 45, agent.log)
print("  받을 수 있나 확인     %5.2f초" % (time.time() - t))

t = time.time()
옛계산 = excel.Calculation
excel.Calculation = -4135
excel.EnableEvents = False
excel.ScreenUpdating = False
print("  계산·이벤트 끄기      %5.2f초" % (time.time() - t))

t = time.time()
for row, col, run in 묶음:
    ws.Range(ws.Cells(row, col), ws.Cells(row, col + len(run) - 1)).Value = (tuple(run),)
적기 = time.time() - t
print("  칸에 적기            %5.2f초  (묶음당 %.0fms)" % (적기, 적기 * 1000 / max(1, len(묶음))))

t = time.time()
excel.Calculation = 옛계산
excel.EnableEvents = True
excel.ScreenUpdating = True
print("  되돌리기(재계산 포함) %5.2f초" % (time.time() - t))

t = time.time()
wb.Save()
print("  저장                 %5.2f초" % (time.time() - t))

t = time.time()
cars = agent.cars_to_find(wb, agent.log)
print("  차찾아 읽기          %5.2f초  (%s대)" % (time.time() - t, len(cars) if cars is not None else '?'))

print("  ---- 열기 뒤 전체     %5.2f초" % (time.time() - t0))
try:
    wb.Close(SaveChanges=False)
except Exception:
    pass
agent.quit_excel(excel, ws, wb)
os.remove(복사본)
