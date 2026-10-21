# -*- coding: utf-8 -*-
"""A컴퓨터 받아쓰기 검사 — "열어 둔 엑셀에 그대로 적고 저장하는가".
원본은 건드리지 않는다. 복사본을 열어 두고 그 위에서 시험한다."""
import os, sys, json, shutil, datetime, subprocess, time
HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = r"D:\프로그램2\꾀꼬리\busyardapp\agent"
sys.path.insert(0, AGENT)
sys.path.append(r"D:\프로그램2\꾀꼬리\busyardapp\tools")
import agent, openpyxl

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1; print(f"  ok   {label}")
    else:
        fail += 1; print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")


# 자료 파일은 src/ 에 있다 (묶기 전에는 그쪽을 본다)
agent._data_path = lambda name: os.path.join(r"D:\프로그램2\꾀꼬리\busyardapp\src", name)

print("▶ 자리 → 칸")
cells_new, cells_old = agent.block_cells("new"), agent.block_cells("old")
eq(len(cells_new), 196, "신차고지 칸 수")
eq(cells_new[1], (38, 14), "신차고지 첫 자리는 N38")
eq(len(cells_old), 90, "구차고지 칸 수")
eq(max(r for r, _ in cells_old.values()) <= 34, True, "구차고지는 1~34행 안")

print("▶ 요청을 적을지 말지")
now = datetime.datetime(2026, 10, 2, 3, 0, tzinfo=datetime.timezone.utc)
mk = (lambda what, mins=0, i="a": {"id": i, "what": what, "date": "2026-10-01",
                                   "at": (now - datetime.timedelta(minutes=mins)).isoformat().replace("+00:00", "Z")})
eq(agent.decide(mk("excel"), None, now), "write", "엑셀 넣기 요청은 적는다")
eq(agent.decide(mk("final"), None, now), "write", "최종 인쇄 요청도 적는다")
eq(agent.decide(mk("paper"), None, now), "skip", "종이 인쇄는 사무실 PC 몫")
eq(agent.decide(mk("pull"), None, now), "skip", "가져오기도 사무실 PC 몫")
eq(agent.decide(mk("excel", i="a"), "a", now), "skip", "같은 요청을 두 번 적지 않는다")
eq(agent.decide(mk("excel", mins=11), None, now), "stale", "10분이 지난 요청은 건너뛴다")
eq(agent.decide(None, None, now), "skip", "요청이 없으면 아무것도")
eq(agent.decide(mk("save"), None, now), "write", "앱을 열 때의 '엑셀 저장' 부탁도 우리 몫")

print("▶ 앱을 열 때의 '엑셀 한 번 저장'")
# 열려 있지 않다 / 읽기 전용 / 고친 것이 없다 / 고친 것이 있다 — 네 가지
진짜찾기, 진짜열린것 = agent.find_excel, agent.running_workbook
agent.find_excel = lambda d: r"Z:\거짓\1021 운영관리.xlsx"


class 가짜wb:
    def __init__(self, read_only=False, saved=True):
        self.ReadOnly, self.Saved, self.저장횟수 = read_only, saved, 0

    def Save(self):
        self.저장횟수 += 1
        self.Saved = True


try:
    agent.running_workbook = lambda p: None
    eq(agent.save_ops()[0], False, "열려 있지 않으면 저장할 것이 없다")

    wb = 가짜wb(read_only=True, saved=False)
    agent.running_workbook = lambda p: wb
    eq(agent.save_ops()[0], False, "읽기 전용이면 저장하지 않는다")
    eq(wb.저장횟수, 0, "읽기 전용에는 손대지 않는다")

    wb = 가짜wb(saved=True)
    agent.running_workbook = lambda p: wb
    eq(agent.save_ops()[0], False, "고친 것이 없으면 그대로 둔다")
    eq(wb.저장횟수, 0, "공연히 파일 시각을 바꾸지 않는다")

    wb = 가짜wb(saved=False)
    agent.running_workbook = lambda p: wb
    된것, 말 = agent.save_ops()
    eq(된것, True, "고친 것이 있으면 저장한다")
    eq(wb.저장횟수, 1, "꼭 한 번만 저장한다")
    eq("운영관리" in 말, True, "무엇을 저장했는지 말해 준다")

    # 저장 부탁에는 창도 띄우지 않고 Z: 에 쪽지도 놓지 않는다
    띄운것, 놓은것 = [], []
    진짜알림, 진짜쪽지 = agent.notice, agent.report
    agent.notice = lambda *a, **k: 띄운것.append(a)
    agent.report = lambda *a, **k: 놓은것.append(a)
    wb = 가짜wb(saved=False)
    agent.running_workbook = lambda p: wb
    try:
        agent.handle({"id": "s1", "what": "save", "date": "2026-10-01",
                      "at": now.isoformat().replace("+00:00", "Z")})
    finally:
        agent.notice, agent.report = 진짜알림, 진짜쪽지
    eq(wb.저장횟수, 1, "부탁을 받으면 실제로 저장한다")
    eq(띄운것, [], "A 컴퓨터에 알림 창을 띄우지 않는다")
    eq(놓은것, [], "아무도 안 기다리는 일이라 쪽지도 놓지 않는다")
finally:
    agent.find_excel, agent.running_workbook = 진짜찾기, 진짜열린것

print("▶ 얼마나 자주 보는가")
eq(agent.poll_sec(datetime.datetime(2026, 10, 2, 1, 30)), 3, "새벽 1시 순찰 중에는 3초마다 (누르면 곧 받는다)")
eq(agent.poll_sec(datetime.datetime(2026, 10, 2, 22, 0)), 3, "밤 10시도 3초")
eq(agent.poll_sec(datetime.datetime(2026, 10, 2, 14, 0)), 900, "낮 2시에는 15분")
eq(agent.poll_sec(datetime.datetime(2026, 10, 2, 8, 59)), 3, "아침 9시 전까지는 3초")

print("▶ 열어 둔 엑셀에 적기")
orig = None
for d in range(0, 40):                     # 가장 가까운 날의 운영관리 파일을 찾는다
    try:
        orig = agent.find_excel(datetime.date(2026, 9, 26) + datetime.timedelta(days=d))
        break
    except FileNotFoundError:
        continue
print("   원본:", os.path.basename(orig))
copy = os.path.join(HERE, "받아쓰기-시험.xlsx")
if os.path.exists(copy):
    os.remove(copy)
shutil.copy2(orig, copy)

import pythoncom, win32com.client
pythoncom.CoInitialize()
excel = win32com.client.DispatchEx("Excel.Application")   # "A 컴퓨터가 열어 둔 엑셀" 흉내
excel.Visible = True            # 실제 A 컴퓨터처럼 보이게 열어 둔다
excel.DisplayAlerts = False
opened = excel.Workbooks.Open(copy)
print("   엑셀에 열어 둔 채로 시험합니다")

board = {"yard": "new", "date": "2026-10-01", "entries": {
    str(n): ({"plate": None, "status": "vacant", "round": 1} if n % 7 == 0 else
             {"plate": str(1500 + n), "status": "filled", "round": 1}) for n in range(1, 137)}}
board["entries"]["5"] = {"plate": None, "phone": "01012345678", "status": "car", "round": 1}

# agent 가 그 열려 있는 통합문서를 찾아 적는지 본다
t = time.time()
n, was_open = agent.write_board(board, copy, log=lambda m: None)
secs = time.time() - t
eq(was_open, True, "열려 있던 그 통합문서를 찾아서 쓴다")
print(f"   {n}대 / {secs:.0f}초")

# 저장되었는지는 디스크에서 본다
after = openpyxl.load_workbook(copy, data_only=True)["고정차고지_입력"]
got = {l: after.cell(*rc).value for l, rc in cells_new.items() if after.cell(*rc).value is not None}
eq(len(got), n, "적었다고 한 대수가 그대로 저장돼 있다")
eq(after.cell(*cells_new[1]).value, 1501, "B5-1 = 1501")
eq(after.cell(cells_new[1][0] + 1, cells_new[1][1]).value not in (None, ""), True, "이름 수식이 살아 값이 찍혔다")
eq(after.cell(*cells_new[5]).value, None, "승용차 자리는 비운다")
eq(after.cell(*cells_new[7]).value, None, "공차 자리도 비운다")
eq(after.cell(*agent.block_cells("old")[1]).value is not None, True, "구차고지 칸은 건드리지 않았다")

opened.Close(SaveChanges=False)
excel.Quit()
print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
