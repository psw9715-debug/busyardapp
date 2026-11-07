# -*- coding: utf-8 -*-
"""B 가 A 를 기다리는 사이 폰이 보낸 요청을 잃지 않는가.

2026-11-03 00:32~00:36: 엑셀 넣기(00:32:46) 를 A 에게 건네고 B 가 서서 기다리는 동안
종이 인쇄를 두 번(00:33:51, 00:35:32) 눌렀다. 폰은 inbox/print.json 한 장을 덮어쓰고,
B 는 기다림이 끝난 뒤 **맨 마지막 것(엑셀 00:35:34) 만** 읽어 종이 인쇄 둘이 사라졌다.

    py tools\\pc\\check_밀린요청.py
"""
import os
import sys

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


def mk(i, what, yard="new"):
    return {"id": i, "what": what, "yard": yard}


# 새 것이 앞 (git log 차례)
그날밤 = [mk("e2", "excel"), mk("p2", "paper"), mk("p1", "paper"), mk("e1", "excel"), mk("옛", "paper")]
ids = lambda rs: [r["id"] for r in rs]  # noqa: E731

print("▶ 밀린 요청 고르기")
eq(ids(inbox.밀린요청(그날밤, "옛", set())), ["p2", "e2"],
   "★ 마지막으로 한 것 뒤의 요청을 모두 — 같은 것을 여러 번 눌렀으면 마지막 하나만, 오래된 차례로")
eq(ids(inbox.밀린요청(그날밤, "e1", set())), ["p2", "e2"], "e1 은 이미 했다")
eq(ids(inbox.밀린요청(그날밤, "e1", {"p2"})), ["e2"], "★ 기다리는 사이 뽑은 종이는 다시 뽑지 않는다")
eq(ids(inbox.밀린요청(그날밤, "e2", set())), [], "새 것이 없으면 아무것도")
eq(ids(inbox.밀린요청([mk("p", "paper", "old"), mk("q", "paper", "new"), mk("x", "excel")], "x", set())),
   ["q", "p"], "차고지가 다르면 둘 다 뽑는다")
eq(ids(inbox.밀린요청([mk("a", "paper")], None, set())), ["a"], "처음 켰을 때")

print("\n▶ 기다리는 사이에 할 수 있는 것")
eq([inbox.기다리며할것(mk("x", w)) for w in ("paper", "pull", "check", "excel", "final", "save")],
   [True, True, True, False, False, False], "종이·가져오기·다시세기는 A 를 기다리지 않는다")

print("\n▶ 결과는 최근 것들을 함께 싣는다 (폰이 연달아 눌러도 앞 결과를 잃지 않게)")
앞 = {"id": "e1", "state": "done", "msg": "엑셀", "최근": [{"id": "e1", "state": "done", "msg": "엑셀"}]}
합 = inbox.결과합치기(앞, {"id": "p1", "state": "done", "msg": "종이"})
eq([x["id"] for x in 합["최근"]], ["p1", "e1"], "★ 새 결과가 앞, 앞 결과도 남는다")
eq((합["id"], 합["msg"]), ("p1", "종이"), "맨 위는 새 결과 (옛 폰도 그대로 읽는다)")
eq(len(inbox.결과합치기({"최근": [{"id": str(i)} for i in range(12)]}, {"id": "n"})["최근"]), 10, "열 개까지만")
eq([x["id"] for x in inbox.결과합치기(None, {"id": "a"})["최근"]], ["a"], "처음")

print("\n▶ A 의 살아있음 — Z: 가 옛 내용을 보여 줘도 파일 시각으로 안다 (2026-11-03 01:53)")
# 01:55:38 에 본 살아있음.json: 파일 시각 01:55:21, 그런데 읽은 내용은 01:50:07.
# 내용만 보고 'A 꺼짐' 이라 폰에 알렸지만, A 는 10초 만에 엑셀에 넣고 인쇄까지 했다.
import json, tempfile, time  # noqa: E401,E402
import ops_fill  # noqa: E402
칸 = tempfile.mkdtemp(prefix="심장-")
진짜심장 = ops_fill.AGENT_ALIVE
ops_fill.AGENT_ALIVE = os.path.join(칸, "살아있음.json")
open(ops_fill.AGENT_ALIVE, "w", encoding="utf-8").write(json.dumps({"at": "2026-11-02T16:50:07Z"}))
eq(inbox.agent_alive(), True, "★ 내용은 오래됐어도 파일이 방금 바뀌었으면 살아 있다")
옛 = time.time() - 600
os.utime(ops_fill.AGENT_ALIVE, (옛, 옛))
eq(inbox.agent_alive(), False, "내용도 파일 시각도 오래됐으면 멎었다")
ops_fill.AGENT_ALIVE = 진짜심장

print("\n▶ 2회차 다시 세기 — A 가 저장한 뒤에 센다 (2026-11-08 저장 안 한 엑셀로 셌다)")
기다린것 = []
진짜기다림, 진짜상태, 진짜점검, 진짜올림 = inbox.wait_for_agent, inbox.write_status, inbox.push_checklist, inbox.write_file
inbox.wait_for_agent = lambda i, log, secs=360: 기다린것.append((i, secs)) or {"state": "done", "msg": "A 컴퓨터: 저장함"}
상태들 = []
inbox.write_status = lambda st: 상태들.append(st)
inbox.push_checklist = lambda req, log: None
inbox.write_file = lambda *a, **k: None
inbox.순찰기록_DIR = tempfile.mkdtemp(prefix="순찰기록-")
inbox.handle({"id": "k1", "what": "check", "저장": True, "date": "2026-11-07", "yard": "new"}, lambda m: None)
eq(기다린것, [("k1", 45)], "★ A 의 저장 쪽지를 45초까지 기다린 뒤 센다")
기다린것.clear()
inbox.handle({"id": "k2", "what": "check", "date": "2026-11-07", "yard": "new"}, lambda m: None)
eq(기다린것, [], "저장이 안 붙은 것은 기다리지 않는다 (옛 폰)")
inbox.wait_for_agent, inbox.write_status, inbox.push_checklist, inbox.write_file = 진짜기다림, 진짜상태, 진짜점검, 진짜올림

print("\n통과 %d / 실패 %d" % (ok, fail))
sys.exit(1 if fail else 0)
