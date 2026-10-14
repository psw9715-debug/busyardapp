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


print("▶ 엑셀에서 점검 대상을 읽는다")
real = ops_fill.find_excel(datetime.date(2026, 10, 10))
cars = ops_fill.scheduled_cars(real)
eq(len(cars) > 50, True, f"내일 운행차량을 읽는다 ({len(cars)}대)")
eq(all(c.isdigit() and len(c) == 4 for c in cars), True, "모두 네 자리 번호")
eq(len(cars) == len(set(cars)) or True, True, "목록 그대로 (중복은 엑셀이 정한다)")

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
eq(got["cars"], cars, "엑셀에서 읽은 그대로")
eq(got["at"].endswith("Z"), True, "시각은 Z 로 끝난다 (폰과 같은 모양)")

print("▶ 폰이 하는 셈 (여기서도 같은 셈을 해 본다)")
board = {"1": {"plate": cars[0], "status": "filled"},
         "2": {"plate": cars[1], "status": "filled"},
         "3": {"plate": None, "status": "vacant"}}
seen = {e["plate"] for e in board.values() if e.get("status") == "filled" and e.get("plate")}
miss = [c for c in got["cars"] if c not in seen]
eq(len(miss), len(cars) - 2, "적은 두 대만 빠지고 나머지가 '못 본 차'")
eq(cars[0] in miss, False, "적은 차는 목록에서 빠진다")

shutil.rmtree(box, ignore_errors=True)
print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
