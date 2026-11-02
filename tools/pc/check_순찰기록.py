# -*- coding: utf-8 -*-
"""순찰 로그 — 폰이 보낸 때 · B 가 받은 때 · A 가 받고 끝낸 때 · 인쇄한 때를 B 에 적는가 (2026-11-03).

진짜 inbox 가지와 진짜 자료 폴더는 건드리지 않는다 (임시 폴더에 적는다).

    py tools\\pc\\check_순찰기록.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.stdout.reconfigure(encoding="utf-8")
import inbox  # noqa: E402

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1
        print("  ok   %s" % label)
    else:
        fail += 1
        print("  FAIL %s\n       기대 %r\n       실제 %r" % (label, want, got))


inbox.순찰기록_DIR = tempfile.mkdtemp(prefix="순찰기록-")
읽기 = lambda: open(os.path.join(inbox.순찰기록_DIR, "2026-11-02.log"), encoding="utf-8").read()  # noqa: E731

print("▶ 시각")
eq(inbox.때글("2026-11-02T15:32:46.171Z"), "00:32:46", "UTC → 한국 시각")
eq(inbox.때글(None), "?", "없으면 ?")

print("\n▶ 첫 입력 시각 (폰이 엑셀 보내기 때 함께 보낸 것)")
순찰 = {"new": {"1": "2026-11-02T15:10:00Z", "2": "2026-11-02T16:40:00Z"}, "old": {"1": "2026-11-02T13:05:00Z"}}
eq(inbox.첫입력줄들(순찰), ["🚶 구 1차 첫 입력 22:05:00", "🚶 신 1차 첫 입력 00:10:00", "🚶 신 2차 첫 입력 01:40:00"],
   "★ 구에서 신으로, 1차에서 2차로")
eq(inbox.첫입력줄들(None), [], "없으면 빈 것")

print("\n▶ 적기")
inbox.순찰로그("2026-11-02", "📱 폰 엑셀 넣기(신) 보냄 00:32:46")
for 줄 in inbox.첫입력줄들(순찰):
    inbox.순찰로그("2026-11-02", 줄, 한번만=True)
for 줄 in inbox.첫입력줄들(순찰):          # 다음 요청에도 같은 것이 실려 온다
    inbox.순찰로그("2026-11-02", 줄, 한번만=True)
글 = 읽기()
eq(글.count("구 1차 첫 입력"), 1, "★ 같은 첫 입력을 두 번 적지 않는다")
eq(글.splitlines()[0].endswith("📱 폰 엑셀 넣기(신) 보냄 00:32:46"), True, "적은 때 · 내용 한 줄")
eq(inbox.순찰로그읽기("2026-11-02").count("\n") >= 3, True, "B 화면에서 읽을 수 있다")
eq(inbox.순찰로그읽기("2026-01-01"), "", "없는 날은 빈 것")

print("\n통과 %d / 실패 %d" % (ok, fail))
sys.exit(1 if fail else 0)
