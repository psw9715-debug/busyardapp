# -*- coding: utf-8 -*-
"""최종 인쇄: 1차고지는 가로, 빠른 길, 그리고 두 번 뽑지 않는가.
종이로는 보내지 않는다 — PrintOut 자리를 가로채 무엇을 어떻게 뽑으려 했는지 본다."""
import datetime
import os
import shutil
import sys
import time

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\agent")
sys.path.append(r"D:\프로그램2\꾀꼬리\busyardapp\tools")
import agent  # noqa: E402
import ops_fill  # noqa: E402

agent._data_path = lambda name: os.path.join(r"D:\프로그램2\꾀꼬리\busyardapp\src", name)
agent.log = lambda m: None
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
zdir = os.path.join(r"Z:\교통사업처_버스운영센터\상황실", "받아쓰기")
copy = os.path.join(zdir, "인쇄시험.xlsx")
if os.path.exists(copy):
    os.remove(copy)
shutil.copy2(orig, copy)

import pythoncom
import win32com.client
pythoncom.CoInitialize()
holder = win32com.client.DispatchEx("Excel.Application")     # A 가 열어 둔 척
holder.Visible = True
holder.DisplayAlerts = False
held = holder.Workbooks.Open(copy)
time.sleep(1)

ws = held.Worksheets(ops_fill.SHEET)
before = {k: getattr(ws.PageSetup, k) for k in agent.PAGE_KEYS}

print("▶ 1차고지는 가로로 (열어 둔 그 문서에서 바로)")
printed = {}
real_print = type(ws).PrintOut if hasattr(type(ws), "PrintOut") else None


class Spy:
    """PrintOut 만 가로채고 나머지는 그대로 넘긴다 (종이를 쓰지 않는다)"""
    def __init__(self, ws):
        self._ws = ws

    def __getattr__(self, name):
        if name == "PrintOut":
            def fake(*a, **k):
                ps = self._ws.PageSetup
                printed.update(area=ps.PrintArea, orient=ps.Orientation, paper=ps.PaperSize,
                               wide=ps.FitToPagesWide, tall=ps.FitToPagesTall, at=time.time())
            return fake
        return getattr(self._ws, name)


class WbSpy:
    def __init__(self, wb):
        self._wb = wb

    def Worksheets(self, name):
        return Spy(self._wb.Worksheets(name))

    def __getattr__(self, name):
        return getattr(self._wb, name)


t = time.time()
agent.print_block(WbSpy(held), "old")
old_secs = time.time() - t
eq(printed.get("orient"), 2, "1차고지는 가로(2)로 뽑는다")
eq(printed.get("area", "").replace("$", ""), "A1:O34", "인쇄 영역은 A1:O34")
eq(printed.get("paper"), 9, "A4 용지")
eq((printed.get("wide"), printed.get("tall")), (1, 1), "한 장에 맞춘다")
print(f"   {old_secs:.1f}초 (엑셀을 새로 띄우고 여는 14초가 빠졌다)")
eq(old_secs < 15, True, f"열어 둔 문서에서 바로 뽑는다 (잰 값 {old_secs:.1f}초 — 엑셀을 새로 띄우고 여는 14초가 빠진다)")

print("▶ 6차고지는 세로로")
printed.clear()
agent.print_block(WbSpy(held), "new")
eq(printed.get("orient"), 1, "6차고지는 세로(1)")
eq(printed.get("area", "").replace("$", ""), "A36:O97", "인쇄 영역은 A36:O97")

print("▶ 같은 차고지를 다시 뽑으면 설정을 또 건드리지 않는다")
t = time.time()
again = agent.page_setup(held.Application, ws, "new", log=None)
twice = time.time() - t
eq(again, 0, "고칠 것이 없다")
eq(twice < 1, True, f"그래서 거저다 ({twice:.2f}초)")

print("▶ 차고지를 바꾸면 그때만 고친다")
changed = agent.page_setup(held.Application, ws, "old", log=None)
eq(changed > 0, True, "가로/영역이 달라 고친다")
eq(str(ws.PageSetup.PrintArea).replace("$", ""), "A1:O34", "1차고지 영역으로")
eq(ws.PageSetup.Orientation, 2, "가로로")

print("▶ A 가 뽑았으면 사무실 PC 는 또 뽑지 않는다")
calls = []
ops_fill.print_ops = lambda path, yard="new": calls.append((path, yard))
msg = ops_fill.run_final(board_date="2026-10-09", log=lambda m: None, yard="old",
                         recorded="A 컴퓨터가 열어 둔 엑셀에 76대 적음 · 인쇄까지 함", printed=True)
eq(calls, [], "두 번 뽑지 않는다")
eq("인쇄까지" in msg, True, "폰에는 A 가 뽑았다고 알린다")

print("▶ A 가 적었지만 못 뽑았으면 사무실 PC 가 뽑는다")
calls.clear()
ops_fill.run_final(board_date="2026-10-09", log=lambda m: None, yard="old",
                   recorded="A 컴퓨터가 엑셀에 76대 적음", printed=False)
eq(len(calls), 1, "사무실 PC 가 한 번 뽑는다")
eq(calls[0][1], "old", "1차고지로 뽑는다 (가로)")

print("▶ 아무도 안 적었으면 적고 나서, 적은 그 파일을 뽑는다")
calls.clear()
ops_fill.find_excel = lambda date: copy
import inbox
board = {"yard": "old", "date": "2026-10-09", "entries": {
    str(n): {"plate": str(3000 + n), "status": "filled", "round": 1} for n in range(1, 91)}}
inbox.fetch = lambda date, yard="new": board
held.Close(SaveChanges=False)          # 아무도 열어 두지 않은 상태로
agent.quit_excel(holder)
ops_fill.run_final(board_date="2026-10-09", log=lambda m: None, yard="old")
eq(len(calls), 1, "한 번 뽑는다")
eq(os.path.normcase(calls[0][0]), os.path.normcase(copy), "복사본이 아니라 적은 그 원본을 뽑는다")

os.remove(copy)
print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
