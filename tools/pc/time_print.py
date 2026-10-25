# -*- coding: utf-8 -*-
"""종이 인쇄가 어디서 시간을 먹는지 쪼개 잰다. 종이는 쓰지 않는다 (PrintOut 은 뺀다).

    py tools\\pc\\time_print.py
"""
import datetime
import os
import sys
import time

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\tools")
sys.stdout.reconfigure(encoding="utf-8")
import inbox  # noqa: E402

날 = sys.argv[1] if len(sys.argv) > 1 else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
차고지 = sys.argv[2] if len(sys.argv) > 2 else "new"

t = time.time()
판 = inbox.fetch(날, 차고지)
받기 = time.time() - t
if 판 is None:
    print("%s %s 판이 없다 — 다른 날짜로: py tools\\pc\\time_print.py 2026-10-25 new" % (날, 차고지))
    raise SystemExit(1)
print("판 받기(git pull+읽기)  %6.2f초  (%d자리)" % (받기, len(판.get("entries", {}))))

낼곳 = os.path.join(os.environ["TEMP"], "시간재기_인쇄.xlsx")
t = time.time()
칸 = inbox.fill(판, 낼곳)
채우기 = time.time() - t
print("서식 채우기            %6.2f초  (%d대)" % (채우기, 칸))

import pythoncom, win32com.client  # noqa: E402
pythoncom.CoInitialize()

t = time.time()
excel = win32com.client.DispatchEx("Excel.Application")
excel.Visible = False
띄우기 = time.time() - t
print("엑셀 새로 띄우기        %6.2f초  ← 여기가 가장 크다" % 띄우기)

t = time.time()
wb = excel.Workbooks.Open(낼곳)
열기 = time.time() - t
print("인쇄 파일 열기          %6.2f초" % 열기)

print("  (PrintOut 은 종이를 쓰므로 재지 않는다)")

t = time.time()
wb.Close(SaveChanges=False)
excel.Quit()
닫기 = time.time() - t
print("닫고 내보내기           %6.2f초" % 닫기)

print("  ---- PrintOut 빼고 합계 %6.2f초" % (받기 + 채우기 + 띄우기 + 열기 + 닫기))
try:
    os.remove(낼곳)
except OSError:
    pass
