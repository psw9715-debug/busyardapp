# -*- coding: utf-8 -*-
"""안내 창이 일이 끝나는 즉시 닫히는가 (전에는 15초를 그냥 떠 있었다)."""
import ctypes
import sys
import time

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\agent")
import agent  # noqa: E402

agent.log = lambda m: None
ok = fail = 0
TITLE = "차고지 받아쓰기 — 시험"


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {label}")
    else:
        fail += 1
        print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")


find = lambda: bool(ctypes.windll.user32.FindWindowW(None, TITLE))

print("▶ 띄우고, 일이 끝나면 바로 닫는다")
t0 = time.time()
told = agent.notice("시험용 안내입니다.", 120, TITLE)
eq(time.time() - t0 < 0.5, True, "띄우고 곧바로 하던 일을 이어 간다")
for _ in range(40):
    if find():
        break
    time.sleep(0.05)
eq(find(), True, "창이 떠 있다")

t = time.time()
told.close()
for _ in range(60):
    if not find():
        break
    time.sleep(0.05)
shut = time.time() - t
eq(find(), False, f"close() 하면 닫힌다 ({shut:.1f}초)")
eq(shut < 3, True, "기다리지 않고 바로")
told.join(3)

print("▶ 아무도 닫지 않으면 저절로 닫힌다")
told = agent.notice("2초 뒤 저절로 닫힙니다.", 2, TITLE)
told.join(8)
eq(find(), False, "시간이 지나면 저절로 닫힌다")

print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
