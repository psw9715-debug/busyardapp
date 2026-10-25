# -*- coding: utf-8 -*-
"""인쇄용 엑셀을 데워 두는 길이 성한가. 종이는 쓰지 않는다 (PrintOut 은 가로챈다).

    py tools\\pc\\check_print_warm.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\tools")
sys.stdout.reconfigure(encoding="utf-8")
import inbox  # noqa: E402
import print_board  # noqa: E402

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {label}")
    else:
        fail += 1
        print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")


print("▶ 데운 엑셀을 다시 쓴다")
eq(print_board.warm_print_excel(), True, "데울 수 있다")
첫번째 = print_board._데운엑셀()
두번째 = print_board._데운엑셀()
eq(첫번째 is 두번째, True, "두 번 불러도 같은 엑셀이다 (새로 띄우지 않는다)")
eq(len(print_board._모아둔것), 1, "끝낼 때 내보내려고 하나만 모아 둔다")

print("▶ 죽어 있으면 새로 띄운다")
# Quit() 만으로는 COM 개체가 죽지 않는다 (붙잡은 참조가 남아 있으면 엑셀이 버틴다).
# 그러니 '두드리면 터지는 것' 을 끼워 두고, 그때 새로 띄우는지를 본다.


class 죽은척:
    def __setattr__(self, 이름, 값):
        raise RuntimeError("이 엑셀은 죽었다")


print_board._내엑셀.앱 = 죽은척()
새것 = print_board._데운엑셀()
eq(isinstance(새것, 죽은척), False, "죽은 것을 붙들고 있지 않는다")
eq(len(print_board._모아둔것), 2, "새로 띄운 것도 모아 둔다")

print("▶ 스레드마다 제 것을 쓴다")
# COM 개체는 만든 스레드에서만 쓸 수 있다. 하나를 같이 쓰면 다른 스레드에서 터진다.
딴것 = {}


def 딴스레드():
    import pythoncom
    pythoncom.CoInitialize()
    딴것["앱"] = print_board._데운엑셀()


t = threading.Thread(target=딴스레드)
t.start()
t.join()
eq(딴것.get("앱") is not None, True, "딴 스레드도 제 것을 얻는다")
eq(딴것["앱"] is 새것, False, "딴 스레드는 다른 엑셀을 쓴다 (같이 쓰면 터진다)")

print("▶ 뽑는 길이 성한가 (종이는 쓰지 않는다)")
# COM 개체에는 가짜를 끼울 수 없으므로, '데운 엑셀' 자리에 통째로 가짜를 끼운다.
뽑은것, 닫은것 = [], []


class 가짜통합문서:
    def PrintOut(self):
        뽑은것.append(True)

    def Close(self, **k):
        닫은것.append(k)


class 가짜통합문서들:
    def Open(self, 길):
        뽑은것.append(길)
        return 가짜통합문서()


class 가짜엑셀:
    Workbooks = 가짜통합문서들()


진짜데움 = print_board._데운엑셀
print_board._데운엑셀 = lambda: 가짜엑셀()
try:
    말 = print_board.print_file(r"C:\없는파일.xlsx")
finally:
    print_board._데운엑셀 = 진짜데움
eq(말, "엑셀(기본 프린터)", "엑셀로 보냈다고 답한다")
eq(len(뽑은것), 2, "연 다음 꼭 한 번 뽑는다")
eq(닫은것, [{"SaveChanges": False}], "통합문서는 닫는다 (엑셀은 데운 채로 둔다)")
eq(getattr(print_board._내엑셀, "앱", None) is not None, True, "엑셀은 그대로 데워져 있다")

print("▶ 방금 받았으면 또 받으러 가지 않는다")
t0 = time.time()
inbox.pull()
첫 = time.time() - t0
t0 = time.time()
inbox.pull()
둘 = time.time() - t0
eq(둘 < 0.1, True, f"바로 뒤의 받기는 건너뛴다 ({둘:.3f}초, 앞은 {첫:.2f}초)")
t0 = time.time()
inbox.pull(꼭=True)
셋 = time.time() - t0
eq(셋 > 둘, True, f"꼭=True 면 그래도 받는다 ({셋:.2f}초)")

print_board._다내보내기()
print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
