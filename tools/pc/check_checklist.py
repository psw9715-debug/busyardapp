# -*- coding: utf-8 -*-
"""1차 순찰 뒤 "오늘 점검할 차" 목록이 폰까지 내려가는가.
진짜 저장소는 건드리지 않는다 — 임시 저장소를 만들어 그 안에서 본다."""
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, r"D:\프로그램2\꾀꼬리\busyardapp\tools")
import inbox  # noqa: E402
import ops_fill  # noqa: E402

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {label}")
    else:
        fail += 1
        print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")


print("▶ 엑셀에서 내일 운행차량을 읽는다")
real = ops_fill.find_excel(datetime.date(2026, 10, 10))
운행 = ops_fill.scheduled_cars(real)
eq(len(운행) > 50, True, f"내일 운행차량을 읽는다 ({len(운행)}대)")
eq(all(c.isdigit() and len(c) == 4 for c in 운행), True, "모두 네 자리 번호")

print("▶ 그 가운데 아직 못 찾은 차만 추린다")
# 이것이 2026-10-20 에 고친 핵심이다. 전에는 운행차량을 통째로 내려보내서
# 2회차 인쇄에 '못 본 차' 가 백 대 넘게 떴다. 한두 대만 남아야 맞다.
찾을것 = ops_fill.pending_cars(real)
eq(set(찾을것) <= set(운행), True, "차찾아는 운행차량 안에서 나온다")
eq(len(찾을것) < len(운행), True, f"운행 {len(운행)}대보다 적다 (차찾아 {len(찾을것)}대)")

휴차 = ops_fill.resting_cars(real)
eq(len(휴차) > 10, True, f"차고지참고에서 휴차를 읽는다 ({len(휴차)}대)")
eq(all(c.isdigit() and len(c) == 4 for c in 휴차), True, "휴차도 모두 네 자리 번호")

cars, 헤아림 = ops_fill.checklist_cars(real)
eq(set(cars) <= set(찾을것), True, "점검 목록은 차찾아에서만 나온다")
eq(set(cars) & 휴차, set(), "휴차는 한 대도 들어 있지 않다")
eq(헤아림["운행"], len(운행), "헤아림에 운행 대수가 맞게 들어간다")
eq(헤아림["차찾아"] - 헤아림["휴차뺌"], len(cars), "차찾아에서 휴차를 뺀 수가 목록 길이")
eq(len(cars) < len(운행) / 2, True,
   f"옛 방식({len(운행)}대)보다 확 줄었다 (지금 {len(cars)}대)")

print("▶ 그 목록을 우편함에 올린다")
box = tempfile.mkdtemp(prefix="check-")
origin = os.path.join(box, "origin.git")
work = os.path.join(box, "work")
run = lambda *a: subprocess.run(a, cwd=work, capture_output=True, text=True, encoding="utf-8")
subprocess.run(["git", "init", "-q", "--bare", origin], capture_output=True)
subprocess.run(["git", "init", "-q", "-b", "main", work], capture_output=True)
run("git", "config", "user.email", "t@t")
run("git", "config", "user.name", "t")
run("git", "remote", "add", "origin", origin)
os.makedirs(os.path.join(work, "inbox"))
io.open(os.path.join(work, "inbox", "print.json"), "w", encoding="utf-8").write("{}")
run("git", "add", "-A")
run("git", "commit", "-qm", "첫 커밋")
run("git", "push", "-q", "origin", "main:refs/heads/inbox")

inbox.ROOT = work
inbox.OUT_DIR = os.path.join(box, "기록")
logs = []
inbox.push_checklist({"id": "요청1", "date": "2026-10-09", "yard": "new"}, logs.append)

inbox.pull()
got = inbox.read("inbox/checklist.json")
eq(got is not None, True, "checklist.json 이 올라갔다")
eq(got["id"], "요청1", "그 요청의 것임을 적는다")
eq(got["date"], "2026-10-09", "근무일을 적는다")
eq(got["cars"], cars, "추려 낸 목록 그대로 (운행차량 전부가 아니다)")
eq(len(got["cars"]) < len(운행), True,
   f"폰에 내려간 것은 {len(got['cars'])}대 — 옛 방식이면 {len(운행)}대였다")
eq(got["at"].endswith("Z"), True, "시각은 Z 로 끝난다 (폰과 같은 모양)")

print("▶ 아직 엑셀에 적기 전이면 애써 줄인 목록을 덮지 않는다")
# 아직 아무것도 안 적힌 날은 운행차량 전부가 '차찾아' 로 나온다. 그때 2회차를 누르면
# (= 이 호출) 그 전부를 내려보내서는 안 된다.
# 그날의 실제 파일에 기대면 하루 지나 그 파일이 채워지는 순간 이 시험이 깨진다
# (2026-10-22 에 실제로 깨졌다). 그래서 그 상황을 지어내서 잰다.
logs.clear()
진짜세기 = ops_fill.checklist_cars
ops_fill.checklist_cars = lambda **k: (운행, {"운행": len(운행), "차찾아": len(운행),
                                            "휴차": 0, "휴차뺌": 0, "남은것": len(운행)})
try:
    inbox.push_checklist({"id": "요청2", "date": "2026-10-20", "yard": "new"}, logs.append)
finally:
    ops_fill.checklist_cars = 진짜세기
inbox.pull()
그대로 = inbox.read("inbox/checklist.json")
eq(그대로["id"], "요청1", "앞서 내려간 목록이 그대로 남아 있다")
eq(any("아직 엑셀에 적힌 것이 없어" in s for s in logs), True, "그 까닭을 기록에 남긴다")

print("▶ 시트를 못 읽었을 때도 덮지 않는다")
logs.clear()
ops_fill.checklist_cars = lambda **k: ([], {"운행": 0, "차찾아": 0, "휴차": 0, "휴차뺌": 0, "남은것": 0})
try:
    inbox.push_checklist({"id": "요청3", "date": "2026-10-20", "yard": "new"}, logs.append)
finally:
    ops_fill.checklist_cars = 진짜세기
inbox.pull()
eq(inbox.read("inbox/checklist.json")["id"], "요청1", "읽지 못했으면 빈 목록을 내려보내지 않는다")

print("▶ 폰이 하는 셈 (여기서도 같은 셈을 해 본다)")
목록 = ["1111", "2222", "3333"]
board = {"1": {"plate": "1111", "status": "filled"},
         "2": {"plate": "2222", "status": "filled"},
         "3": {"plate": None, "status": "vacant"}}
seen = {e["plate"] for e in board.values() if e.get("status") == "filled" and e.get("plate")}
miss = [c for c in 목록 if c not in seen]
eq(miss, ["3333"], "적은 두 대는 빠지고 안 적은 한 대만 '못 본 차'")
eq(len([c for c in [] if c not in seen]), 0, "목록이 비면 못 본 차도 없다")

shutil.rmtree(box, ignore_errors=True)
print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
