# -*- coding: utf-8 -*-
"""A 컴퓨터 → 사무실 PC → 폰 으로 결과가 건너가는지 본다.
진짜 Z: 도, 진짜 우편함도 건드리지 않는다 — 쪽지 자리와 올리는 자리를 가로챈다."""
import sys, os, io, json, tempfile, datetime
AG = r"D:\프로그램2\꾀꼬리\busyardapp\agent"
TL = r"D:\프로그램2\꾀꼬리\busyardapp\tools"
sys.path.insert(0, AG); sys.path.insert(0, TL)
import agent, ops_fill, inbox

ok = fail = 0
def eq(got, want, label):
    global ok, fail
    if got == want: ok += 1; print(f"  ok   {label}")
    else: fail += 1; print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")

box = tempfile.mkdtemp(prefix="handoff-")
_dir = os.path.join(box, "받아쓰기")
agent.result_dir = lambda: _dir
agent.result_file = lambda: os.path.join(_dir, "결과.json")
agent.RESULT_FILE = agent.result_file()          # 아래 검사에서 들여다보는 자리
ops_fill.AGENT_RESULT = agent.result_file()
# 진짜 Z: 의 "살아있음" 을 보지 않도록 시험용 자리로 돌려 둔다
ops_fill.AGENT_ALIVE = os.path.join(_dir, "살아있음.json")
agent.log = lambda m: None
logs = []
log = logs.append

print("▶ A 가 쪽지를 놓는다")
agent.report({"id": "요청1", "what": "excel"}, "done", "A 컴퓨터가 열어 둔 엑셀에 116대 적음")
note = json.load(io.open(agent.RESULT_FILE, encoding="utf-8"))
eq(sorted(note), ["at", "id", "msg", "printed", "state", "what"], "쪽지에 든 것")
eq((note["id"], note["state"], note["what"]), ("요청1", "done", "excel"), "누가 무엇을 했는지")
eq(note["at"].endswith("Z"), True, "시각은 Z 로 끝난다")

print("▶ 사무실 PC 가 그 쪽지를 집는다")
eq(inbox.agent_note("요청1")["msg"], "A 컴퓨터가 열어 둔 엑셀에 116대 적음", "이 요청 것이면 집는다")
eq(inbox.agent_note("다른요청"), None, "남의 요청 쪽지는 집지 않는다")

print("▶ 쪽지가 오면 사무실 PC 는 엑셀을 또 건드리지 않는다")
called = []
ops_fill.run = lambda **k: called.append("run") or "내가 넣음"
ops_fill.run_final = lambda **k: called.append(("final", k.get("recorded"))) or "내가 넣고 인쇄"
sent = {}
inbox.write_status = lambda st: sent.update(st)
inbox.wait_for_agent = lambda i, log, secs=30: inbox.agent_note(i)

inbox.handle({"id": "요청1", "what": "excel", "date": "2026-10-01", "yard": "new"}, log)
eq(called, [], "A 가 적었으면 복사본을 또 만들지 않는다")
eq((sent["state"], sent["msg"]), ("done", "A 컴퓨터가 열어 둔 엑셀에 116대 적음"), "폰에는 A 의 결과가 그대로 간다")
eq(sent["id"], "요청1", "요청 번호도 그대로")

print("▶ 최종 인쇄 — 적힌 원본을 있는 그대로 뽑는다")
called.clear(); sent.clear()
agent.report({"id": "요청2", "what": "final"}, "done", "A 컴퓨터가 열어 둔 엑셀에 118대 적음")
inbox.handle({"id": "요청2", "what": "final", "date": "2026-10-01", "yard": "new"}, log)
eq(called, [("final", "A 컴퓨터가 열어 둔 엑셀에 118대 적음")], "적지 않고 원본을 뽑으라고 넘긴다")
eq(sent["state"], "done", "인쇄까지 마친 뒤에 폰에 알린다")

print("▶ A 가 꺼져 있으면 사무실 PC 가 전처럼 한다")
called.clear(); sent.clear(); os.remove(agent.RESULT_FILE)
inbox.handle({"id": "요청3", "what": "excel", "date": "2026-10-01", "yard": "new"}, log)
eq(called, ["run"], "쪽지가 없으면 복사본에 적는다")
eq(sent["msg"], "내가 넣음 · A 컴퓨터 받아쓰기가 꺼져 있었음",
   "A 가 꺼져 있었다는 사정까지 폰에 알린다")

# A 가 살아 있는데 쪽지만 없었으면 그 꼬리말은 붙이지 않는다
import datetime as _dt
ops_fill.AGENT_ALIVE = os.path.join(box, "받아쓰기", "살아있음.json")
os.makedirs(os.path.dirname(ops_fill.AGENT_ALIVE), exist_ok=True)
io.open(ops_fill.AGENT_ALIVE, "w", encoding="utf-8").write(json.dumps(
    {"pc": "A", "at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}))
called.clear(); sent.clear()
inbox.handle({"id": "요청3b", "what": "excel", "date": "2026-10-01", "yard": "new"}, log)
eq(sent["msg"], "내가 넣음", "A 가 켜져 있으면 꼬리말을 붙이지 않는다")
os.remove(ops_fill.AGENT_ALIVE)
called.clear(); sent.clear()
inbox.handle({"id": "요청4", "what": "final", "date": "2026-10-01", "yard": "new"}, log)
eq(called, [("final", None)], "최종 인쇄도 전처럼 복사본으로")

print("▶ 1차고지도 같은 길로 간다")
called.clear(); sent.clear()
agent.report({"id": "요청old", "what": "excel", "yard": "old"}, "done", "A 컴퓨터가 열어 둔 엑셀에 76대 적음")
inbox.handle({"id": "요청old", "what": "excel", "date": "2026-10-08", "yard": "old"}, log)
eq(called, [], "1차고지도 A 가 적었으면 사무실 PC 는 손대지 않는다")
eq(sent["msg"], "A 컴퓨터가 열어 둔 엑셀에 76대 적음", "그 결과가 그대로 폰에 간다")

print("▶ A 가 못 했다고 하면 그대로 폰에 알린다")
called.clear(); sent.clear()
agent.report({"id": "요청5", "what": "excel"}, "error", "A 컴퓨터: Z: 를 찾을 수 없습니다")
inbox.handle({"id": "요청5", "what": "excel", "date": "2026-10-01", "yard": "new"}, log)
eq(called, [], "못 했다는데 내가 덮어 적지 않는다")
eq((sent["state"], sent["msg"]), ("fail", "A 컴퓨터: Z: 를 찾을 수 없습니다"), "실패 이유가 폰까지 간다")

print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
