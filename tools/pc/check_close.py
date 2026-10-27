# -*- coding: utf-8 -*-
"""02:08 에 대장을 저장하고 닫는 길이 성한가. 진짜 엑셀은 건드리지 않는다 (가짜를 끼운다).

2026-10-26: 02:05 에 차찾아가 남아 있다고 '그날 닫음' 표시를 찍어 버려, 02:07 에
차찾아가 0 이 된 뒤에도 두 번 다시 보지 않았다 → 출퇴근 관리가 대장을 못 열었다.
2026-10-27: 그래서 **묻지도 않고, 차찾아가 남아도 닫는다** 로 바꿨다 (1분 뒤 B 가 열어야 한다).
2026-10-28: 02:09 → **02:08** (1분은 빡빡했다). 닫은 뒤 **닫힌 것을 확인**하고,
            02:12 까지 **다시 열렸는지 지켜본다**.

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
적은것 = []
agent.log = lambda m: 적은것.append(m)
agent.time = type("가짜시간", (), {"sleep": staticmethod(lambda s: None)})()

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


근무밤 = datetime.datetime(2026, 10, 26, 2, 8)
근무일들 = {"2026-10-25"}          # 새벽 2시는 전날 밤 근무다


class 가짜통합문서:
    """닫으면 '열린 목록' 에서 빠진다 — 진짜 엑셀처럼."""

    def __init__(self, 끈질김=0):
        self.ReadOnly = False
        self.저장 = 0
        self.닫음 = 0
        self.끈질김 = 끈질김          # 몇 번은 닫아도 안 닫힌 척한다

    def Save(self):
        self.저장 += 1

    def Close(self, **k):
        self.닫음 += 1

    @property
    def 열려있나(self):
        return self.닫음 <= self.끈질김


def 끼우기(wb, 찾을차):
    agent.find_excel = lambda d: r"Z:\거짓\1026 운영관리.xlsx"
    agent.running_workbook = lambda p: (wb if (wb is not None and wb.열려있나) else None)
    agent.cars_to_find = lambda w, log=None: list(찾을차)


진짜들 = (agent.find_excel, agent.running_workbook, agent.cars_to_find)

print("▶ 닫을 때가 되었는가 (02:08)")
eq(agent.CLOSE_AT, (2, 8), "닫는 시각은 02:08")
eq(agent.due_to_close(datetime.datetime(2026, 10, 26, 2, 7), 근무일들), False, "02:07 — 아직")
eq(agent.due_to_close(근무밤, 근무일들), True, "02:08 — 지금")
eq(agent.due_to_close(datetime.datetime(2026, 10, 26, 2, 58), 근무일들), True, "02:58 — 아직 창 안")
eq(agent.due_to_close(datetime.datetime(2026, 10, 26, 5, 59), 근무일들), True, "05:59 — 늦게 켜도 한 번은")
eq(agent.due_to_close(datetime.datetime(2026, 10, 26, 6, 1), 근무일들), False, "06:01 — 창이 닫혔다")
eq(agent.due_to_close(근무밤, {"2026-01-01"}), False, "내 근무 밤이 아니면 안 닫는다")

try:
    print("▶ 차찾아가 남아도 닫는다 (1분 뒤 B 가 열어야 한다)")
    wb = 가짜통합문서()
    끼우기(wb, ["1301", "1354"])
    적은것.clear()
    eq(agent.close_ops(근무밤, ask=lambda n: True), True, "닫는다")
    eq((wb.저장, wb.닫음), (1, 1), "저장하고 닫는다")
    eq(any("1301" in m for m in 적은것), True, "차찾아는 기록에 남긴다")
    eq(any("확인했습니다" in m for m in 적은것), True, "닫힌 것까지 확인한다")
    eq(알린것, [], "묻지 않는다 (확인창 없음)")
    eq(agent.closed_day(), "2026-10-26", "'그날 닫음' 을 찍는다")
    eq(agent.due_to_close(근무밤, 근무일들), False, "찍었으니 두 번 닫지 않는다")

    print("▶ 한 번에 안 닫히면 다시 닫는다")
    os.remove(agent.CLOSED_FILE)
    wb2 = 가짜통합문서(끈질김=1)        # 첫 Close 로는 안 닫힌다
    끼우기(wb2, [])
    적은것.clear()
    eq(agent.close_ops(근무밤, ask=lambda n: True), True, "결국 닫는다")
    eq(wb2.닫음, 2, "두 번 닫는다")
    eq(any("아직 열려 있습니다" in m for m in 적은것), True, "아직 열려 있다고 적는다")

    print("▶ 끝내 안 닫히면 소리 내어 적고 넘어간다")
    os.remove(agent.CLOSED_FILE)
    wb3 = 가짜통합문서(끈질김=99)
    끼우기(wb3, [])
    적은것.clear()
    eq(agent.close_ops(근무밤, ask=lambda n: True), False, "닫지 못했다고 돌려준다")
    eq(any("끝내 닫히지 않았습니다" in m for m in 적은것), True, "🚨 를 적는다")
    eq(agent.closed_day(), "2026-10-26", "그래도 표시는 찍는다 (무한히 붙들지 않는다)")

    print("▶ 닫은 뒤 02:12 까지 다시 열렸는지 지켜본다")
    wb4 = 가짜통합문서()                 # 누군가 다시 열어 두었다
    끼우기(wb4, [])
    적은것.clear()
    eq(agent.watch_closed(datetime.datetime(2026, 10, 26, 2, 10)), True, "다시 열려 있으면 또 닫는다")
    eq((wb4.저장, wb4.닫음), (1, 1), "저장하고 닫는다")
    eq(any("다시 열려 있습니다" in m for m in 적은것), True, "그렇게 적는다")

    끼우기(None, [])
    eq(agent.watch_closed(datetime.datetime(2026, 10, 26, 2, 10)), False, "닫힌 채면 조용히 있는다")

    wb5 = 가짜통합문서()
    끼우기(wb5, [])
    eq(agent.watch_closed(datetime.datetime(2026, 10, 26, 2, 13)), False, "02:13 은 창 밖 — 보지 않는다")
    eq(agent.watch_closed(datetime.datetime(2026, 10, 26, 2, 7)), False, "02:07 도 창 밖")
    eq(wb5.닫음, 0, "그러니 건드리지 않는다")

    os.remove(agent.CLOSED_FILE)
    eq(agent.watch_closed(datetime.datetime(2026, 10, 26, 2, 10)), False,
       "아직 닫지도 않은 날에는 지켜보기가 나서지 않는다 (close_ops 의 일이다)")
finally:
    agent.find_excel, agent.running_workbook, agent.cars_to_find = 진짜들

print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
