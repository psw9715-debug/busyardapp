# -*- coding: utf-8 -*-
"""A 컴퓨터가 **스스로 판올림**하는 길이 성한가. 진짜로 깔지는 않는다 (깔기를 가로챈다).

2026-10-28: 고칠 때마다 A 자리로 가서 설치하는 것이 번거로워, 공유 폴더에 올려 두면
A 가 스스로 깔게 했다. 잘못 만들면 2분마다 설치본을 돌리거나, 02:10 에 엑셀을 닫아야
할 때 설치가 끼어든다. 그 두 가지를 여기서 못 박는다.

    py tools\\pc\\check_판올림.py
"""
import datetime
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\agent")
sys.stdout.reconfigure(encoding="utf-8")
import agent  # noqa: E402

적은것 = []
agent.log = lambda m: 적은것.append(m)
집 = tempfile.mkdtemp(prefix="판올림-")
agent.HOME = 집
agent.TRIES_FILE = os.path.join(집, "판올림시도.json")

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {label}")
    else:
        fail += 1
        print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")


def 설치본두기(folder, *판들):
    for 글 in 판들:
        io.open(os.path.join(folder, f"차고지받아쓰기_Setup_{글}.exe"), "w").write("가짜")


깐것 = []
깔기 = lambda 길: 깐것.append(os.path.basename(길))        # noqa: E731
낮 = datetime.datetime(2026, 10, 28, 22, 0)


print("▶ 판 번호 읽기")
eq(agent.판숫자("1.6.0"), (1, 6, 0), "1.6.0")
eq(agent.판숫자("1.10.2"), (1, 10, 2), "1.10.2 는 1.9.9 보다 높다")
eq(agent.판숫자("1.10.2") > agent.판숫자("1.9.9"), True, "숫자로 견준다 (글자 비교가 아니다)")
eq(agent.판숫자("엉뚱"), (0, 0, 0), "못 읽으면 0.0.0")

print("▶ 공유 폴더에서 가장 높은 판을 고른다")
자리 = tempfile.mkdtemp(prefix="설치본-")
eq(agent.새설치본(자리), (None, None), "아무것도 없으면 없다고 한다")
설치본두기(자리, "1.5.0", "1.6.0", "1.10.0")
io.open(os.path.join(자리, "읽어보기.txt"), "w").write("딴것")
길, 판 = agent.새설치본(자리)
eq(판, (1, 10, 0), "가장 높은 것을 고른다")
eq(os.path.basename(길), "차고지받아쓰기_Setup_1.10.0.exe", "그 파일을 가리킨다")
eq(agent.새설치본(os.path.join(자리, "없는폴더")), (None, None), "폴더가 없어도 터지지 않는다")

print("▶ 더 높은 판이면 깐다")
agent._판본때[0] = 0
깐것.clear(); 적은것.clear()
eq(agent.판올림(낮, 지금판="1.6.0", 깔기=깔기, folder=자리), True, "1.10.0 을 깐다")
eq(깐것, ["차고지받아쓰기_Setup_1.10.0.exe"], "그 설치본을 돌렸다")
eq(any("묻지 않고 깝니다" in m for m in 적은것), True, "기록에 남긴다")

print("▶ 같은 판이거나 낮으면 가만히 있는다")
agent._판본때[0] = 0
깐것.clear()
eq(agent.판올림(낮, 지금판="1.10.0", 깔기=깔기, folder=자리), False, "같은 판이면 안 깐다")
agent._판본때[0] = 0
eq(agent.판올림(낮, 지금판="2.0.0", 깔기=깔기, folder=자리), False, "내가 더 높으면 안 깐다")
eq(깐것, [], "둘 다 손대지 않았다")

print("▶ 2분에 한 번만 본다")
os.remove(agent.TRIES_FILE)
agent._판본때[0] = 0
깐것.clear()
eq(agent.판올림(낮, 지금판="1.6.0", 깔기=깔기, folder=자리), True, "한 번은 본다")
eq(agent.판올림(낮, 지금판="1.6.0", 깔기=깔기, folder=자리), False, "바로 다시 부르면 그냥 지나간다")
eq(len(깐것), 1, "설치본을 두 번 돌리지 않는다")

print("▶ 02:00~02:20 에는 깔지 않는다 (엑셀 닫고 B 가 여는 참)")
for 시, 분, 될까 in ((1, 59, True), (2, 0, False), (2, 10, False), (2, 19, False), (2, 20, True)):
    os.remove(agent.TRIES_FILE) if os.path.exists(agent.TRIES_FILE) else None
    agent._판본때[0] = 0
    깐것.clear()
    눈 = agent.판올림(datetime.datetime(2026, 10, 28, 시, 분), 지금판="1.6.0",
                    깔기=깔기, folder=자리)
    eq(눈, 될까, f"{시:02d}:{분:02d} — {'깐다' if 될까 else '안 깐다'}")

print("▶ 같은 판으로 두 번 실패하면 더 매달리지 않는다")
if os.path.exists(agent.TRIES_FILE):
    os.remove(agent.TRIES_FILE)
터지는깔기 = lambda 길: (_ for _ in ()).throw(OSError("일부러"))   # noqa: E731
적은것.clear()
for 번 in (1, 2):
    agent._판본때[0] = 0
    eq(agent.판올림(낮, 지금판="1.6.0", 깔기=터지는깔기, folder=자리), False, f"{번}번째 — 실패")
agent._판본때[0] = 0
깐것.clear()
eq(agent.판올림(낮, 지금판="1.6.0", 깔기=깔기, folder=자리), False, "세 번째는 아예 나서지 않는다")
eq(깐것, [], "설치본을 돌리지 않는다")
eq(sum("판올림 실패" in m for m in 적은것), 2, "실패는 두 번만 적는다")

print("▶ 판 번호가 설치 스크립트와 같은가")
iss = io.open(r"D:\프로그램2\꾀꼬리\busyardapp\agent\installer.iss", encoding="utf-8-sig").read()
m = re.search(r'#define AppVer "([\d.]+)"', iss)
eq(m.group(1) if m else None, agent.VERSION, f"installer.iss 의 AppVer 과 같다 ({agent.VERSION})")

print("▶ 돌고 있는 판을 공유 폴더에 알린다")
소스 = io.open(r"D:\프로그램2\꾀꼬리\busyardapp\agent\agent.py", encoding="utf-8").read()
머리 = 소스.index("def tell_alive")
알림 = 소스[머리:머리 + 1200]
eq('"판": VERSION' in 알림, True, "살아 있다는 쪽지에 판 번호를 함께 적는다")

print("▶ 설치본 자리")
eq(agent.SETUP_DIR_PARTS, ("유틸리티", "차고지순찰프로그램"), "공유 폴더의 그 자리를 본다")
eq(agent.setup_dir().endswith(os.path.join("유틸리티", "차고지순찰프로그램")), True,
   "뿌리에서 그 폴더로 내려간다")
eq(agent.share_root().rstrip("\\").lower() in
   (agent.base_dir().split("교통사업처")[0].rstrip("\\").lower(), ), True,
   "뿌리는 상황실에서 두 단계 위다")

print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
