# -*- coding: utf-8 -*-
"""02:05 에 대장을 닫는 길이 성한가. 진짜 엑셀은 건드리지 않는다 (가짜를 끼운다).

2026-10-26: 02:05 에 차찾아가 남아 있다고 '그날 닫음' 표시를 찍어 버려, 02:07 에
차찾아가 0 이 된 뒤에도 두 번 다시 보지 않았다. 그래서 출퇴근 관리가 대장을 열지
못한 채 한참 멈춰 있었다.

    py tools\\pc\\check_close.py
"""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\agent")
sys.stdout.reconfigure(encoding="utf-8")
import agent  # noqa: E402

agent._data_path = lambda name: os.path.join(r"D:\프로그램2\꾀꼬리\busyardapp\src", name)
agent.log = lambda m: None

칸 = tempfile.mkdtemp(prefix="close-")
agent.CLOSED_FILE = os.path.join(칸, "닫음.txt")
알린것 = []
agent.notice = lambda *a, **k: 알린것.append(a[0] if a else "")

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {label}")
    else:
        fail += 1
        print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")


근무밤 = datetime.datetime(2026, 10, 26, 2, 5)
근무일들 = {"2026-10-25"}          # 새벽 2시는 전날 밤 근무다


class 가짜통합문서:
    def __init__(self):
        self.ReadOnly = False
        self.저장 = 0
        self.닫음 = 0

    def Save(self):
        self.저장 += 1

    def Close(self, **k):
        self.닫음 += 1


def 끼우기(wb, 찾을차):
    agent.find_excel = lambda d: r"Z:\거짓\1026 운영관리.xlsx"
    agent.running_workbook = lambda p: wb
    agent.cars_to_find = lambda w, log=None: list(찾을차)


진짜들 = (agent.find_excel, agent.running_workbook, agent.cars_to_find)

print("▶ 닫을 때가 되었는가")
eq(agent.due_to_close(datetime.datetime(2026, 10, 26, 2, 4), 근무일들), False, "02:04 — 아직")
eq(agent.due_to_close(근무밤, 근무일들), True, "02:05 — 지금")
eq(agent.due_to_close(datetime.datetime(2026, 10, 26, 2, 58), 근무일들), True, "02:58 — 아직 창 안")
eq(agent.due_to_close(datetime.datetime(2026, 10, 26, 3, 1), 근무일들), False, "03:01 — 창이 닫혔다")
eq(agent.due_to_close(근무밤, {"2026-01-01"}), False, "내 근무 밤이 아니면 안 닫는다")

try:
    print("▶ 차찾아가 남아 있으면 닫지 않는다 — 그러나 포기하지도 않는다")
    wb = 가짜통합문서()
    끼우기(wb, ["1301", "1354"])
    agent._told_find[0] = 0
    eq(agent.close_ops(근무밤, ask=lambda n: True), False, "닫지 않는다")
    eq(wb.닫음, 0, "정말로 안 닫았다")
    eq(len(알린것), 1, "못 찾은 차를 알린다")
    eq("1301" in 알린것[0], True, "어느 차인지 번호가 들어 있다")
    eq(agent.closed_day() or "표시 없음", "표시 없음", "★ '그날 닫음' 표시를 찍지 않는다 — 다시 봐야 하니까")
    eq(agent.due_to_close(근무밤, 근무일들), True, "그래서 다음 번에도 또 본다")

    print("▶ 3초마다 보지만 알림은 가끔만")
    알린것.clear()
    for _ in range(5):
        agent.close_ops(근무밤, ask=lambda n: True)
    eq(알린것, [], "10분 안에는 다시 알리지 않는다 (창 도배를 막는다)")

    print("▶ 차찾아가 0 이 되면 그때 닫는다")
    wb2 = 가짜통합문서()
    끼우기(wb2, [])
    eq(agent.close_ops(근무밤, ask=lambda n: True), True, "닫았다")
    eq((wb2.저장, wb2.닫음), (1, 1), "저장하고 닫는다")
    eq(agent.closed_day(), "2026-10-26", "이제는 '그날 닫음' 을 찍는다")
    eq(agent.due_to_close(근무밤, 근무일들), False, "두 번 닫지 않는다")

    print("▶ 열려 있지 않으면 할 일이 없다")
    os.remove(agent.CLOSED_FILE)
    agent.running_workbook = lambda p: None
    eq(agent.close_ops(근무밤, ask=lambda n: True), False, "닫을 것이 없다")
    eq(agent.closed_day(), "2026-10-26", "그때는 표시를 찍는다 (다시 볼 까닭이 없다)")

    print("▶ 닫지 말라고 하면 닫지 않는다")
    os.remove(agent.CLOSED_FILE)
    wb3 = 가짜통합문서()
    끼우기(wb3, [])
    eq(agent.close_ops(근무밤, ask=lambda n: False), False, "사람이 취소하면 그대로 둔다")
    eq(wb3.닫음, 0, "정말로 안 닫았다")
finally:
    agent.find_excel, agent.running_workbook, agent.cars_to_find = 진짜들

print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
