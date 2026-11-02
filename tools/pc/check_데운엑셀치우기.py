# -*- coding: utf-8 -*-
"""sctc-copy 가 강제로 꺼지면 인쇄용으로 숨겨 띄운 엑셀이 남는다 — 다음에 켤 때 치우는가 (2026-11-03).

그날 밤 sctc-copy 를 여러 번 강제로 껐다 켰더니 숨은 엑셀이 열몇 개 쌓여 B PC 가 느려졌다.
진짜 엑셀은 띄우지도 끄지도 않는다 (가짜 프로세스).

    py tools\\pc\\check_데운엑셀치우기.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.stdout.reconfigure(encoding="utf-8")
import print_board  # noqa: E402

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1
        print("  ok   %s" % label)
    else:
        fail += 1
        print("  FAIL %s\n       기대 %r\n       실제 %r" % (label, want, got))


class 가짜프로세스:
    목록 = {}

    def __init__(self, pid):
        if pid not in self.목록:
            raise LookupError("없는 프로세스")
        self.pid = pid
        self._이름, self._때 = self.목록[pid]

    def name(self):
        return self._이름

    def create_time(self):
        return self._때

    def kill(self):
        죽인것.append(self.pid)


죽인것 = []
print_board._프로세스 = 가짜프로세스
print_board.데운엑셀_기록 = os.path.join(tempfile.mkdtemp(prefix="데운엑셀-"), "데운엑셀.txt")

print("▶ 지난번에 숨겨 띄운 엑셀이 남아 있으면 치운다")
가짜프로세스.목록 = {101: ("EXCEL.EXE", 1000.0), 102: ("EXCEL.EXE", 2000.0), 103: ("notepad.exe", 3000.0)}
print_board._데운것적기(101, 1000.0)
print_board._데운것적기(102, 1999.0)      # 그 번호를 이제 다른 엑셀이 쓴다 (시작 시각이 다르다)
print_board._데운것적기(103, 3000.0)      # 엑셀이 아니다
print_board._데운것적기(104, 4000.0)      # 이미 없다
eq(print_board.지난엑셀치우기(), 1, "치운 수")
eq(죽인것, [101], "★ 우리가 띄운 그 엑셀만 끝낸다 (번호·시작 시각이 같은 것)")
eq(os.path.exists(print_board.데운엑셀_기록), False, "치운 뒤엔 적어 둔 것을 지운다")

죽인것.clear()
eq(print_board.지난엑셀치우기(), 0, "적어 둔 것이 없으면 아무것도")
eq(죽인것, [], "사람이 연 엑셀은 건드리지 않는다")

print("\n통과 %d / 실패 %d" % (ok, fail))
sys.exit(1 if fail else 0)
