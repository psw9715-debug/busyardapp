# -*- coding: utf-8 -*-
"""A컴퓨터 받아쓰기 검사 — "열어 둔 엑셀에 그대로 적고 저장하는가".
원본은 건드리지 않는다. 복사본을 열어 두고 그 위에서 시험한다."""
import os, sys, json, shutil, datetime, subprocess, time
HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = r"D:\프로그램2\꾀꼬리\busyardapp\agent"
sys.path.insert(0, AGENT)
sys.path.append(r"D:\프로그램2\꾀꼬리\busyardapp\tools")
import agent, openpyxl

ok = fail = 0


def eq(got, want, label):
    global ok, fail
    if got == want:
        ok += 1; print(f"  ok   {label}")
    else:
        fail += 1; print(f"  FAIL {label}\n       기대 {want!r}\n       실제 {got!r}")


# 자료 파일은 src/ 에 있다 (묶기 전에는 그쪽을 본다)
agent._data_path = lambda name: os.path.join(r"D:\프로그램2\꾀꼬리\busyardapp\src", name)

print("▶ 자리 → 칸")
cells_new, cells_old = agent.block_cells("new"), agent.block_cells("old")
eq(len(cells_new), 196, "신차고지 칸 수")
eq(cells_new[1], (38, 14), "신차고지 첫 자리는 N38")
eq(len(cells_old), 90, "구차고지 칸 수")
eq(max(r for r, _ in cells_old.values()) <= 34, True, "구차고지는 1~34행 안")

print("▶ 요청을 적을지 말지")
now = datetime.datetime(2026, 10, 2, 3, 0, tzinfo=datetime.timezone.utc)
mk = (lambda what, mins=0, i="a": {"id": i, "what": what, "date": "2026-10-01",
                                   "at": (now - datetime.timedelta(minutes=mins)).isoformat().replace("+00:00", "Z")})
eq(agent.decide(mk("excel"), None, now), "write", "엑셀 넣기 요청은 적는다")
eq(agent.decide(mk("final"), None, now), "write", "최종 인쇄 요청도 적는다")
eq(agent.decide(mk("paper"), None, now), "skip", "종이 인쇄는 사무실 PC 몫")
eq(agent.decide(mk("pull"), None, now), "skip", "가져오기도 사무실 PC 몫")
eq(agent.decide(mk("excel", i="a"), "a", now), "skip", "같은 요청을 두 번 적지 않는다")
eq(agent.decide(mk("excel", mins=11), None, now), "stale", "10분이 지난 요청은 건너뛴다")
eq(agent.decide(None, None, now), "skip", "요청이 없으면 아무것도")
eq(agent.decide(mk("save"), None, now), "write", "앱을 열 때의 '엑셀 저장' 부탁도 우리 몫")

print("▶ GitHub 를 먼저 본다 — Z: 는 GitHub 에 닿지 않을 때만 (2026-11-03 사용자 결정)")
# 11-03 00:32·00:52 에 A 의 Z: 가 몇 분씩 막혀 엑셀 넣기가 늦었다. 폰이 올린 것은 GitHub 에
# 이미 있으므로 A 가 바로 본다 (커밋 번호로 받아 CDN 의 묵은 것을 피한다).
import io, tempfile  # noqa: E402
칸 = tempfile.mkdtemp(prefix="agentreq-")
지금 = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
진짜자리, 진짜마지막 = agent.result_dir, agent.LAST_FILE
agent.result_dir = lambda: 칸
agent.LAST_FILE = os.path.join(칸, "마지막요청.txt")
진짜가져오기, 진짜처리, 진짜랜 = agent.fetch, agent.handle, agent.local_request
깃 = {"것": None, "막힘": False}
랜본것 = []


def 가짜깃(name):
    if 깃["막힘"]:
        raise OSError("GitHub 에 닿지 않음")
    return 깃["것"]


agent.fetch = 가짜깃
진짜쪽지 = agent.report
agent.report = lambda *a, **k: None      # ★ 뒤에서 도는 쪽지가 진짜 Z: 에 닿지 않게
agent.local_request = lambda: 랜본것.append(1) or 진짜랜()
집은것 = []
agent.handle = lambda req: 집은것.append(req)
mk = lambda i: {"id": i, "what": "excel", "date": "2026-10-01", "yard": "new", "at": 지금}  # noqa: E731
try:
    io.open(os.path.join(칸, "요청.json"), "w", encoding="utf-8").write(json.dumps(mk("랜것"), ensure_ascii=False))
    깃["것"] = mk("깃것")
    agent.tick()
    eq([r["id"] for r in 집은것], ["깃것"], "★ GitHub 에 온 것을 바로 집는다")
    eq(랜본것, [], "★ GitHub 가 되면 Z: 를 건드리지 않는다 (Z: 가 막혀도 늦지 않게)")

    집은것.clear(); 깃["것"] = None
    agent.tick()
    eq(집은것, [], "새 것이 없으면 아무것도 (Z: 의 지난 것을 다시 하지 않는다)")

    깃["막힘"] = True
    agent.tick()
    eq([r["id"] for r in 집은것], ["랜것"], "GitHub 에 닿지 않을 때만 Z: 로 건네받은 것을 본다")

    집은것.clear(); 깃["막힘"] = False; 깃["것"] = mk("깃것")
    agent.tick()
    깃["막힘"] = True
    agent.tick()
    eq(집은것, [], "★ 두 길을 오가도 이미 한 요청(깃것·랜것)은 다시 하지 않는다")
finally:
    agent.result_dir, agent.LAST_FILE = 진짜자리, 진짜마지막
    agent.fetch, agent.handle, agent.local_request = 진짜가져오기, 진짜처리, 진짜랜
    agent.report = 진짜쪽지
    shutil.rmtree(칸, ignore_errors=True)

print("▶ GitHub 의 inbox 커밋 번호를 읽는다 (캐시 없는 길)")
refs = ("001e# service=git-upload-pack\n0000"
        "00a4" + "a" * 40 + " HEAD\0multi_ack\n"
        "003f" + "b" * 40 + " refs/heads/inbox\n"
        "003e" + "c" * 40 + " refs/heads/main\n0000")
eq(agent._inbox_sha_from(refs), "b" * 40, "refs/heads/inbox 의 번호")
eq(agent._inbox_sha_from("0000"), None, "없으면 None")

print("▶ 번호가 그대로면 받지 않고, 바뀌면 그 번호로 받는다")
받은주소 = []
진짜번호, 진짜받기 = agent._inbox_sha, agent._get_json
번호 = ["s1"]
agent._inbox_sha = lambda: 번호[0]
agent._get_json = lambda url: 받은주소.append(url) or {"id": "x"}
agent._etags.clear()
eq(agent.fetch("print.json"), {"id": "x"}, "처음엔 받는다")
eq("/s1/inbox/print.json" in 받은주소[-1], True, "★ 커밋 번호가 든 주소로 (묵은 것을 받지 않는다)")
eq(agent.fetch("print.json"), None, "번호가 그대로면 받지 않는다")
번호[0] = "s2"
eq(agent.fetch("print.json"), {"id": "x"}, "번호가 바뀌면 다시 받는다")
eq(len(받은주소), 2, "받으러 간 것은 두 번뿐")
agent._inbox_sha, agent._get_json = 진짜번호, 진짜받기
agent._etags.clear()

print("▶ 적는 동안 띄우는 안내는 한 줄이다")
# 긴 장문은 읽지 않는다. 어느 차고지인지만 알면 된다.
eq(agent.busy_text("old"), "구차고지 차량입력중 건들지 마세요", "구차고지일 때")
eq(agent.busy_text("new"), "신차고지 차량입력중 건들지 마세요", "신차고지일 때")
eq("\n" in agent.busy_text("new"), False, "줄바꿈 없는 한 줄")
eq(len(agent.busy_text("new")) <= 30, True, "한눈에 들어오는 길이")
eq(agent.busy_text("몰라").startswith("차고지"), True, "모르는 차고지도 말은 된다")

print("▶ 앱을 열 때의 '엑셀 한 번 저장'")
# 열려 있지 않다 / 읽기 전용 / 고친 것이 없다 / 고친 것이 있다 — 네 가지
진짜찾기, 진짜열린것 = agent.find_excel, agent.running_workbook
agent.find_excel = lambda d: r"Z:\거짓\1021 운영관리.xlsx"


class 가짜wb:
    def __init__(self, read_only=False, saved=True):
        self.ReadOnly, self.Saved, self.저장횟수 = read_only, saved, 0

    def Save(self):
        self.저장횟수 += 1
        self.Saved = True


try:
    agent.running_workbook = lambda p: None
    eq(agent.save_ops()[0], False, "열려 있지 않으면 저장할 것이 없다")

    wb = 가짜wb(read_only=True, saved=False)
    agent.running_workbook = lambda p: wb
    eq(agent.save_ops()[0], False, "읽기 전용이면 저장하지 않는다")
    eq(wb.저장횟수, 0, "읽기 전용에는 손대지 않는다")

    wb = 가짜wb(saved=True)
    agent.running_workbook = lambda p: wb
    eq(agent.save_ops()[0], False, "고친 것이 없으면 그대로 둔다")
    eq(wb.저장횟수, 0, "공연히 파일 시각을 바꾸지 않는다")

    wb = 가짜wb(saved=False)
    agent.running_workbook = lambda p: wb
    된것, 말 = agent.save_ops()
    eq(된것, True, "고친 것이 있으면 저장한다")
    eq(wb.저장횟수, 1, "꼭 한 번만 저장한다")
    eq("운영관리" in 말, True, "무엇을 저장했는지 말해 준다")

    # 저장 부탁에는 창도 띄우지 않고 Z: 에 쪽지도 놓지 않는다
    띄운것, 놓은것 = [], []
    진짜알림, 진짜쪽지 = agent.notice, agent.report
    agent.notice = lambda *a, **k: 띄운것.append(a)
    agent.report = lambda *a, **k: 놓은것.append(a)
    wb = 가짜wb(saved=False)
    agent.running_workbook = lambda p: wb
    try:
        agent.handle({"id": "s1", "what": "save", "date": "2026-10-01",
                      "at": now.isoformat().replace("+00:00", "Z")})
    finally:
        agent.notice, agent.report = 진짜알림, 진짜쪽지
    eq(wb.저장횟수, 1, "부탁을 받으면 실제로 저장한다")
    eq(띄운것, [], "A 컴퓨터에 알림 창을 띄우지 않는다")
    eq(놓은것, [], "아무도 안 기다리는 일이라 쪽지도 놓지 않는다")
finally:
    agent.find_excel, agent.running_workbook = 진짜찾기, 진짜열린것

print("▶ 얼마나 자주 보는가")
eq(agent.poll_sec(datetime.datetime(2026, 10, 2, 1, 30)), 3, "새벽 1시 순찰 중에는 3초마다 (누르면 곧 받는다)")
eq(agent.poll_sec(datetime.datetime(2026, 10, 2, 22, 0)), 3, "밤 10시도 3초")
eq(agent.poll_sec(datetime.datetime(2026, 10, 2, 14, 0)), 900, "낮 2시에는 15분")
eq(agent.poll_sec(datetime.datetime(2026, 10, 2, 8, 59)), 3, "아침 9시 전까지는 3초")

print("▶ 열어 둔 엑셀에 적기")
orig = None
for d in range(0, 40):                     # 가장 가까운 날의 운영관리 파일을 찾는다
    try:
        orig = agent.find_excel(datetime.date(2026, 9, 26) + datetime.timedelta(days=d))
        break
    except FileNotFoundError:
        continue
print("   원본:", os.path.basename(orig))
copy = os.path.join(HERE, "받아쓰기-시험.xlsx")
if os.path.exists(copy):
    os.remove(copy)
shutil.copy2(orig, copy)

import pythoncom, win32com.client
pythoncom.CoInitialize()
excel = win32com.client.DispatchEx("Excel.Application")   # "A 컴퓨터가 열어 둔 엑셀" 흉내
excel.Visible = True            # 실제 A 컴퓨터처럼 보이게 열어 둔다
excel.DisplayAlerts = False
opened = excel.Workbooks.Open(copy)
print("   엑셀에 열어 둔 채로 시험합니다")

board = {"yard": "new", "date": "2026-10-01", "entries": {
    str(n): ({"plate": None, "status": "vacant", "round": 1} if n % 7 == 0 else
             {"plate": str(1500 + n), "status": "filled", "round": 1}) for n in range(1, 137)}}
board["entries"]["5"] = {"plate": None, "phone": "01012345678", "status": "car", "round": 1}

# agent 가 그 열려 있는 통합문서를 찾아 적는지 본다
t = time.time()
n, was_open = agent.write_board(board, copy, log=lambda m: None)
secs = time.time() - t
eq(was_open, True, "열려 있던 그 통합문서를 찾아서 쓴다")
print(f"   {n}대 / {secs:.0f}초")

# 저장되었는지는 디스크에서 본다
after = openpyxl.load_workbook(copy, data_only=True)["고정차고지_입력"]
got = {l: after.cell(*rc).value for l, rc in cells_new.items() if after.cell(*rc).value is not None}
eq(len(got), n, "적었다고 한 대수가 그대로 저장돼 있다")
eq(after.cell(*cells_new[1]).value, 1501, "B5-1 = 1501")
eq(after.cell(cells_new[1][0] + 1, cells_new[1][1]).value not in (None, ""), True, "이름 수식이 살아 값이 찍혔다")
eq(after.cell(*cells_new[5]).value, None, "승용차 자리는 비운다")
eq(after.cell(*cells_new[7]).value, None, "공차 자리도 비운다")
eq(after.cell(*agent.block_cells("old")[1]).value is not None, True, "구차고지 칸은 건드리지 않았다")

opened.Close(SaveChanges=False)
excel.Quit()
print("▶ 편집 중인 칸만 Esc 로 취소한다 (대화상자는 건드리지 않는다)")
eq(agent.편집창인가("EXCEL6"), True, "칸 안 편집 창이면 취소한다")
eq(agent.편집창인가("EXCEL<"), True, "수식 입력줄 편집이면 취소한다")
eq(agent.편집창인가("Button"), False, "★ 대화상자 단추면 건드리지 않는다")
eq(agent.편집창인가("Edit"), False, "★ 대화상자 글칸이면 건드리지 않는다")
eq(agent.편집끝내기("이런파일은없다.xlsx", log=lambda m: None), False, "그 엑셀 창이 없으면 아무것도 보내지 않는다")

print("▶ 엑셀 넣기도 적은 뒤 A 가 뽑는다 (2026-11-03 사용자 결정 — 종이 인쇄는 B 몫)")
진짜들 = (agent.find_excel, agent.write_board, agent.running_workbook, agent.print_block, agent.report)
뽑음, 쪽지 = [], []
agent.find_excel = lambda d: "가짜.xlsx"
agent.write_board = lambda board, path, found=None: (62, True)
agent.running_workbook = lambda p: "열린책"
agent.print_block = lambda wb, yard: 뽑음.append(yard)
agent.report = lambda req, state, msg, printed=False: 쪽지.append((state, printed))
for what in ("excel", "final"):
    뽑음.clear(); 쪽지.clear()
    agent.handle({"id": "t-" + what, "what": what, "date": "2026-11-02", "yard": "old", "board": {"entries": {}}})
    eq((뽑음, 쪽지), (["old"], [("done", True)]), f"★ {what} → 적고 그 차고지를 뽑고 '인쇄까지 함' 을 알린다")
agent.print_block = lambda wb, yard: (_ for _ in ()).throw(RuntimeError("프린터 없음"))
쪽지.clear()
agent.handle({"id": "t-x", "what": "excel", "date": "2026-11-02", "yard": "new", "board": {"entries": {}}})
eq(쪽지, [("done", False)], "뽑지 못해도 적은 것은 적었다고 알린다")
agent.find_excel, agent.write_board, agent.running_workbook, agent.print_block, agent.report = 진짜들

print("▶ 결과 쪽지에 A 가 받은 때를 함께 싣는다 (B 의 순찰 로그)")
import tempfile, time as _time  # noqa: E401,E402
칸 = tempfile.mkdtemp(prefix="받음-")
진짜자리 = agent.result_dir
agent.result_dir = lambda: 칸
agent.report({"id": "r1", "what": "excel"}, "working", "집었습니다")
_time.sleep(0.05)
agent.report({"id": "r1", "what": "excel"}, "done", "적음")
끝쪽지 = json.load(open(os.path.join(칸, "결과_r1.json"), encoding="utf-8"))
eq(끝쪽지["받음"] < 끝쪽지["at"], True, "★ 받은 때는 집은 때 그대로, 끝낸 때(at)는 그 뒤")

print("▶ 심장 소리에 '지금 하는 일' 을 싣는다 — 멎으면 어디서 멎었는지 보이게 (2026-11-03 00:52)")
agent.하는중("엑셀에 적기")
agent.tell_alive(every=0)
심장 = json.load(open(os.path.join(칸, "살아있음.json"), encoding="utf-8"))
eq(심장.get("하는일"), "엑셀에 적기", "★ 하던 일")
eq(bool(심장.get("언제부터")), True, "그 일을 언제 시작했는지")

print("▶ 공유 폴더에 못 쓴 기록은 모아 두었다가 다시 써질 때 함께 남긴다")
agent._못쓴기록.clear()
agent._공유기록남기기(os.path.join(칸, "없는폴더", "x", "A기록.log"), "줄1")   # 못 쓴다
eq(len(agent._못쓴기록), 1, "못 쓴 줄을 쥐고 있다")
agent._공유기록남기기(os.path.join(칸, "A기록.log"), "줄2")
eq(open(os.path.join(칸, "A기록.log"), encoding="utf-8").read().count("줄"), 2, "★ 다시 써지면 앞의 것까지 함께")
eq(len(agent._못쓴기록), 0, "다 남겼으면 비운다")

print("▶ 켤 때 이 PC 의 기록을 공유 폴더에 올린다 (A 에서만 보이던 것을 B 에서 보게)")
진짜로그 = agent.LOG_FILE
agent.LOG_FILE = os.path.join(칸, "로컬.log")
open(agent.LOG_FILE, "w", encoding="utf-8").write("".join(f"줄{i}\n" for i in range(1000)))
agent.로컬기록올리기(몇줄=300)
올림 = open(os.path.join(칸, "A로컬기록.log"), encoding="utf-8").read().splitlines()
eq((len(올림), 올림[-1]), (300, "줄999"), "끝에서 300줄을 올린다")
agent.LOG_FILE = 진짜로그
agent.result_dir = 진짜자리

print(f"\n통과 {ok} / 실패 {fail}")
sys.exit(1 if fail else 0)
