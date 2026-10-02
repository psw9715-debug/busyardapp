# -*- coding: utf-8 -*-
"""폰이 GitHub inbox 가지에 올린 그날 판을 받아 저장하고 인쇄한다.

폰과 PC 는 서로 직접 닿을 수 없다 (폰은 LTE, PC 는 사내 유선). 둘 다 닿는 GitHub
저장소의 inbox 가지를 우편함처럼 쓴다.

    폰  inbox/<날짜>.json   그날 판 (입력이 멎을 때마다 올린다)
    폰  inbox/print.json    요청 {id, date, at, what}
                            'paper'(순찰 양식 인쇄) · 'excel'(운영관리에 넣기)
                            'final'(넣고 그 양식 그대로 인쇄) · 'pull'(엑셀에서 가져오기)
    PC  inbox/status.json   결과 {id, state, msg, at} — 폰이 이걸 보고 결과를 띄운다
    A   Z: 의 받아쓰기/결과.json   엑셀을 열어 둔 PC 가 "적었다" 를 놓는 쪽지.
                            그 PC 는 올릴 권한이 없으므로 이 PC 가 받아 폰에 전한다.
    PC  inbox/pulled.json   가져온 판 {id, yard, date, entries} — 2차 순찰의 밑바탕

PC 쪽은 전부 git 으로 주고받는다. 이 PC 의 git 은 이미 GitHub 에 로그인돼 있어 토큰이
따로 필요 없고, GitHub API 의 시간당 60회 제한이나 사내망 인증서 문제도 없다.
작업 폴더(main)는 건드리지 않고 origin/inbox 참조와 임시 색인만 쓴다.

인쇄 양식은 원본 엑셀(`차고지 프린트.xlsx` 의 `신차고지` 시트)이고 값만 채운다.
2회차 기록이 있으면 1회차 번호는 흐리게, 2회차 번호는 진하게 — 앱 화면과 같다.

    python tools/inbox.py               # 오늘 판을 받아 저장하고 기본 프린터로 인쇄
    python tools/inbox.py --save        # 인쇄하지 않고 저장만
    python tools/inbox.py 2026-09-20    # 그 날짜 판
    python tools/inbox.py --watch       # 폰의 인쇄 요청을 기다렸다가 인쇄 (sctc-copy 가 안에서 돌린다)

저장: 기록/<날짜> 신차고지.json (받은 그대로), 기록/<날짜> 신차고지.xlsx (인쇄본)
종료 코드: 0 성공, 2 그날 올라온 판 없음, 1 그 밖의 오류
"""
import copy
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

import openpyxl
from openpyxl.worksheet.properties import PageSetupProperties

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "reference", "차고지 프린트.xlsx")

# 차고지마다 인쇄 시트와 자리 자료가 다르다. 판에 담겨 오는 yard 로 고른다.
YARDS = {
    "new": {"sheet": "신차고지", "data": "yard-data.js"},
    "old": {"sheet": "구차고지", "data": "yard-old-data.js"},
}
SHEET = YARDS["new"]["sheet"]        # 옛 기록에 yard 가 없으면 신차고지로 본다
OUT_DIR = os.path.join(ROOT, "기록")
LAST_FILE = os.path.join(OUT_DIR, ".last_print")   # 이미 처리한 인쇄 요청 — 껐다 켜도 두 번 뽑지 않게
FILE_DIR = os.path.join(OUT_DIR, "받은파일")        # 폰에서 보낸 사진이 내려오는 다운로드 폴더
INBOX_REF = "refs/remotes/origin/inbox"

# 폰이 올린 차량 특이사항을 일지 프로그램에게 넘기는 곳.
# 여기에 텍스트로 떨구면 일지 프로그램(daywork.py)이 집어서 엑셀에 적는다.
DAYWORK_DIR = os.path.join(os.path.dirname(ROOT), "daywork")
DAYWORK_INBOX = os.path.join(DAYWORK_DIR, "inbox")
DAYWORK_SEEN = os.path.join(OUT_DIR, ".last_daywork.json")   # 같은 것을 두 번 떨구지 않게
GREY = "FF8F8F8F"
STALE = datetime.timedelta(minutes=10)   # 이보다 오래된 요청은 뽑지 않는다
POLL_SEC = 5


def work_date(now=None):
    """야간 근무라 오전 9시 전은 전날 순회다 (앱의 workDate 와 같은 규칙)"""
    now = now or datetime.datetime.now()
    if now.hour < 9:
        now -= datetime.timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def current_layout():
    """앱이 지금 쓰는 자리 번호 체계 (src/store.js 의 LAYOUT)"""
    with open(os.path.join(ROOT, "src", "store.js"), encoding="utf-8") as f:
        return int(re.search(r"export const LAYOUT = (\d+)", f.read()).group(1))


def spot_cells(yard="new"):
    """순회 번호 -> 엑셀 칸 (src/yard-data.js, yard-old-data.js 에서 읽는다)"""
    name = YARDS.get(yard, YARDS["new"])["data"]
    with open(os.path.join(ROOT, "src", name), encoding="utf-8") as f:
        text = f.read()
    data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    return {c["spot"]: c["xl"] for c in data["cells"] if c["kind"] == "spot"}


# ---- GitHub inbox 가지 (git) -------------------------------------------

def git(*args, stdin=None, env=None):
    return subprocess.run(
        ["git", *args], cwd=ROOT, input=stdin, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=60,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def must(r, what):
    if r.returncode != 0:
        raise RuntimeError(f"{what} 실패: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def remote_sha():
    """inbox 가지의 지금 커밋. 가볍게 자주 부를 수 있다."""
    out = must(git("ls-remote", "origin", "refs/heads/inbox"), "GitHub 확인")
    return out.split()[0] if out else None


def pull():
    must(git("fetch", "-q", "origin", f"+refs/heads/inbox:{INBOX_REF}"), "GitHub 받기")


def read(path):
    """받아 둔 inbox 가지의 파일. 없으면 None"""
    r = git("show", f"{INBOX_REF}:{path}")
    return json.loads(r.stdout) if r.returncode == 0 else None


def fetch(date, yard="new"):
    """그날 그 차고지의 판. 아직 안 올라왔으면 None

    차고지별로 이름이 나뉘기 전에 올라온 판은 날짜만 있는 이름이라 그것도 본다.
    """
    pull()
    board = read(f"inbox/{date}-{yard}.json")
    if board is None and yard == "new":
        board = read(f"inbox/{date}.json")
    return board


# ---- 차량 특이사항 (daywork) ------------------------------------------

def inbox_names():
    """우편함에 올라와 있는 파일 이름들"""
    r = git("ls-tree", "--name-only", f"{INBOX_REF}:inbox")
    return r.stdout.split() if r.returncode == 0 else []


def daywork_text(board):
    """일지 프로그램이 읽을 텍스트. 사람이 눈으로 보고 손으로 고칠 수도 있게 단순하게.

        # daywork 특이사항 2026-10-02
        # 폰 전송 2026-10-03T01:31:00 · 3건
        1120\t대차
        1121\t브레이크 소음
    """
    lines = [f"# daywork 특이사항 {board.get('date', '')}",
             f"# 폰 전송 {board.get('updatedAt', '')} · {len(board.get('entries', []))}건"]
    for e in board.get("entries", []):
        plate = str(e.get("plate", "")).strip()
        issue = str(e.get("issue", "")).replace("\t", " ").strip()
        if plate and issue:
            lines.append(f"{plate}\t{issue}")
    return "\n".join(lines) + "\n"


def _seen():
    try:
        with open(DAYWORK_SEEN, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _mark_seen(seen):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(DAYWORK_SEEN, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def take_daywork(log=print):
    """폰이 올린 특이사항을 일지 프로그램 폴더에 텍스트로 떨군다.

    같은 내용을 두 번 떨구지 않도록 폰이 찍은 시각(updatedAt)을 기억해 둔다.
    폰이 하루에 여러 번 보내면 그때마다 그날 전체 목록이 다시 오는데,
    일지 프로그램이 이미 적은 것은 건너뛰므로 중복 걱정은 없다.

    떨군 파일 경로 목록을 돌려준다.
    """
    seen = _seen()
    written = []
    for name in inbox_names():
        if not (name.startswith("daywork-") and name.endswith(".json")):
            continue
        board = read(f"inbox/{name}")
        if not board:
            continue
        date = board.get("date") or name[len("daywork-"):-len(".json")]
        stamp = board.get("updatedAt") or ""
        if seen.get(date) == stamp:
            continue                      # 지난번에 떨군 것과 같다
        entries = board.get("entries") or []
        if not entries:
            seen[date] = stamp
            continue

        try:
            os.makedirs(DAYWORK_INBOX, exist_ok=True)
            path = os.path.join(DAYWORK_INBOX, f"{date}.txt")
            with open(path, "w", encoding="utf-8", newline="\r\n") as f:
                f.write(daywork_text(board))
        except Exception as e:
            log(f"⚠ [특이사항] 일지 폴더에 떨구지 못함: {e}")
            continue

        seen[date] = stamp
        written.append(path)
        log(f"📝 [특이사항] 폰에서 {date} {len(entries)}건 받음")

    if written:
        _mark_seen(seen)
    return written


def write_status(status):
    """폰에 결과를 알린다 (inbox/status.json)"""
    write_file("inbox/status.json", status, f"PC 결과: {status['state']}")


def take_files(log=print):
    """폰이 보낸 사진·파일을 다운로드 폴더로 내리고 우편함에서 치운다.

    공개 저장소라 사진을 오래 둘 곳이 아니다. 내리는 즉시 지운다.
    (가지 이력에는 남는다 — 그것까지 비우려면 따로 손봐야 한다.)
    """
    # -z 로 받는다. 그냥 받으면 git 이 한글 이름을 "\341\204..." 꼴로 감싸 내주고,
    # 그 이름으로는 파일을 꺼낼 수 없다 (카카오톡에서 보낸 PDF 가 그래서 안 내려왔다).
    r = git("ls-tree", "-r", "-z", "--name-only", INBOX_REF, "inbox/files/")
    paths = [p for p in r.stdout.split("\0") if p.strip()] if r.returncode == 0 else []
    if not paths:
        return []
    got = []
    for path in paths:
        blob = subprocess.run(["git", "cat-file", "blob", f"{INBOX_REF}:{path}"], cwd=ROOT,
                              capture_output=True, timeout=120,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if blob.returncode != 0:
            log(f"⚠ [사진] {path} 를 꺼내지 못했다")
            continue
        # inbox/files/<날짜>/<이름> → 기록/받은파일/<날짜>/<이름>
        # 아이폰에서 온 한글 이름은 자모가 풀어져 있다(ㅈㅏㄱ...). 붙여서 저장해야
        # 탐색기에서 제 이름으로 보인다.
        rel = unicodedata.normalize("NFC", path[len("inbox/files/"):])
        out = os.path.join(FILE_DIR, *rel.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(blob.stdout)
        got.append(out)
        log(f"📷 [사진] {rel} ({len(blob.stdout) // 1024}KB) 받음")
    if got:
        drop_files(paths, f"받은 사진 {len(got)}개 치움")
    return got


def drop_files(paths, message):
    """우편함에서 파일 여러 개를 지운다"""
    index = os.path.join(tempfile.gettempdir(), "busyard-inbox.index")
    env = {"GIT_INDEX_FILE": index}
    for _ in range(3):
        pull()
        must(git("read-tree", INBOX_REF, env=env), "색인 읽기")
        for path in paths:
            must(git("update-index", "--force-remove", path, env=env), "색인에서 지우기")
        tree = must(git("write-tree", env=env), "트리 만들기")
        commit = must(git("commit-tree", tree, "-p", INBOX_REF, "-m", message), "커밋")
        if git("push", "-q", "origin", f"{commit}:refs/heads/inbox").returncode == 0:
            return
    raise RuntimeError("받은 사진을 우편함에서 치우지 못했다")


def write_file(path, obj, message):
    """inbox 가지의 파일 하나만 바꿔 올린다.

    폰이 그 사이 판을 올렸으면 push 가 거절되므로 다시 받아서 그 위에 쌓는다.
    """
    body = json.dumps(obj, ensure_ascii=False)
    index = os.path.join(tempfile.gettempdir(), "busyard-inbox.index")
    env = {"GIT_INDEX_FILE": index}
    for _ in range(3):
        pull()
        blob = must(git("hash-object", "-w", "--stdin", stdin=body), "상태 파일 만들기")
        must(git("read-tree", INBOX_REF, env=env), "색인 읽기")
        must(git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env), "색인 갱신")
        tree = must(git("write-tree", env=env), "트리 만들기")
        commit = must(git("commit-tree", tree, "-p", INBOX_REF, "-m", message), "커밋")
        if git("push", "-q", "origin", f"{commit}:refs/heads/inbox").returncode == 0:
            return
    raise RuntimeError(f"{path} 를 GitHub 에 올리지 못했다")


# ---- 엑셀 ---------------------------------------------------------------

def fill(board, out_path):
    """판을 인쇄 시트에 채워 out_path 로 저장한다. 채운 칸 수를 돌려준다."""
    if board.get("layout") != current_layout():
        raise ValueError(f"자리 번호 체계가 다르다 (폰 {board.get('layout')}, PC {current_layout()}) — "
                         "폰 앱과 PC 의 busyardapp 을 둘 다 최신으로 맞출 것")
    yard = board.get("yard", "new")
    sheet = YARDS.get(yard, YARDS["new"])["sheet"]
    cells = spot_cells(yard)
    entries = board["entries"]
    has_round2 = any(e.get("round", 1) == 2 for e in entries.values())

    wb = openpyxl.load_workbook(TEMPLATE)       # 서식이 살아 있어야 하므로 data_only 를 쓰지 않는다
    for name in wb.sheetnames:
        if name != sheet:
            wb.remove(wb[name])                 # 인쇄할 시트만 남긴다
    ws = wb[sheet]

    # 종이 한 장에 맞춰 나오게 못을 박는다 — 구차고지는 A1:O34 가로 한 장이다.
    ws.print_area = {"old": "A1:O34", "new": "A1:O62"}[yard if yard in ("old", "new") else "new"]
    ws.page_setup.orientation = "landscape" if yard == "old" else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    n = 0
    for spot, e in entries.items():
        xl = cells.get(int(spot))
        if not xl:
            continue
        cell = ws[xl]
        if e.get("status") == "car":
            # 승용차 전화번호는 종이에 찍지 않는다 — 개인 번호이고, 2차 순찰 전에 빠질 차다.
            # 번호는 폰에서 그 칸을 눌러 본다.
            continue
        if e.get("status") == "filled" and e.get("plate"):
            cell.value = e["plate"]
        else:
            continue                            # 공차는 종이에서 빈 칸
        if has_round2 and e.get("round", 1) == 1:
            font = copy.copy(cell.font)
            font.color = GREY
            font.b = False
            cell.font = font
        n += 1
    wb.save(out_path)
    return n


def print_xlsx(path):
    """엑셀로 기본 프린터에 보낸다. sctc-copy 의 작업 스레드에서도 불리므로 COM 을 여기서 연다."""
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except ImportError:
        pass
    from print_board import print_file
    return print_file(path)


def save_and_print(date, do_print=True, yard="new"):
    """그날 판을 받아 저장하고 (인쇄하고) 한 줄 요약을 돌려준다. 판이 없으면 None"""
    board = fetch(date, yard)
    if board is None:
        return None
    os.makedirs(OUT_DIR, exist_ok=True)
    yard = "구차고지" if board.get("yard") == "old" else "신차고지"
    base = os.path.join(OUT_DIR, f"{date} {yard}")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=1)
    n = fill(board, base + ".xlsx")
    if do_print:
        print_xlsx(base + ".xlsx")
    return f"{date} {n}대"


# ---- 폰의 인쇄 요청 기다리기 ----------------------------------------------

def decide(req, handled_id, now):
    """'print' 뽑는다 / 'skip' 이미 했거나 요청 없음 / 'stale' 너무 오래된 요청"""
    if not req or req.get("id") == handled_id:
        return "skip"
    at = datetime.datetime.fromisoformat(req["at"].replace("Z", "+00:00"))
    return "stale" if now - at > STALE else "print"


def _load_last():
    try:
        with open(LAST_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def _save_last(id_):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        f.write(id_)


def agent_note(req_id):
    """A 컴퓨터(엑셀을 열어 둔 PC)가 Z: 에 놓아 둔 쪽지. 이 요청 것이 아니면 None.

    A 는 GitHub 에 올릴 권한이 없다. 그래서 "적었다" 를 Z: 에 한 줄 놓고, 이미 그
    권한을 들고 도는 이 PC 가 폰에 전해 준다.
    """
    import ops_fill
    try:
        with open(ops_fill.AGENT_RESULT, encoding="utf-8") as f:
            note = json.load(f)
    except Exception:
        return None
    return note if note.get("id") == req_id else None


def wait_for_agent(req_id, log, secs=30):
    """A 컴퓨터가 적고 쪽지를 놓을 때까지 잠깐 기다린다. 안 오면 내가 한다."""
    until = time.time() + secs
    while time.time() < until:
        note = agent_note(req_id)
        if note:
            log(f"📨 [순회판] A 컴퓨터: {note['msg']}")
            return note
        time.sleep(2)
    return None


def handle(req, log, notify=None):
    """폰이 보낸 요청 하나를 처리하고 결과를 폰에 알린다"""
    now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: E731
    kind = req.get("what", "paper")
    what = {"excel": "운영관리 엑셀", "pull": "엑셀에서 가져오기",
            "final": "최종 인쇄"}.get(kind, "종이 인쇄")
    try:
        if kind == "pull":
            import ops_fill
            yard = req.get("yard", "old")
            entries = ops_fill.read_board(yard, log=log)
            write_file("inbox/pulled.json", {
                "id": req["id"], "yard": yard, "date": req["date"], "entries": entries,
            }, f"{req['date']} 엑셀에서 가져온 판")
            state, msg = "done", f"{len(entries)}대 가져옴"
        elif kind in ("excel", "final"):
            import ops_fill
            yard = req.get("yard", "new")
            note = wait_for_agent(req["id"], log)      # A 가 원본에 적는 쪽이 빠르고 확실하다
            if note and note["state"] != "done":
                raise RuntimeError(note["msg"])        # A 가 못 했다면 그대로 폰에 알린다
            if kind == "excel":
                state, msg = ("done", note["msg"]) if note else (
                    "done", ops_fill.run(board_date=req["date"], log=log, yard=yard))
            else:
                state, msg = "done", ops_fill.run_final(
                    board_date=req["date"], log=log, yard=yard,
                    recorded=note["msg"] if note else None)
        else:
            summary = save_and_print(req["date"], yard=req.get("yard", "new"))
            state, msg = ("nodata", f"{req['date']} 판이 GitHub 에 없습니다") if summary is None else ("done", summary)
    except Exception as e:                    # 프린터·엑셀 오류도 폰에 그대로 알린다
        state, msg = "fail", str(e)
    log(f"{'🖨' if state == 'done' else '⚠'} [순회판] 폰 요청({what}) — {msg}")
    write_status({"id": req["id"], "state": state, "msg": msg, "at": now()})
    if notify:
        notify(state == "done", f"{what} — {msg}")


def watch(log=print, stop=None, notify=None, on_daywork=None):
    """inbox 가지를 5초마다 보고, 폰이 보낸 요청을 처리한다. stop() 이 참이면 끝낸다.

    on_daywork(떨군 파일 목록) — 차량 특이사항이 새로 왔을 때 부른다.
    받는 일은 여기서 하고, 엑셀에 적는 일은 일지 프로그램이 한다.
    """
    handled = _load_last()
    seen = None
    last_err = None
    log("📡 [순회판] 폰 인쇄 요청 대기 시작")
    while not (stop and stop()):
        try:
            sha = remote_sha()
            if sha and sha != seen:
                pull()
                seen = sha
                for got in take_files(log):          # 사진이 함께 와 있으면 먼저 내린다
                    if notify:
                        notify(True, f"사진 받음 — {os.path.basename(got)}")
                dropped = take_daywork(log)          # 차량 특이사항도 같은 기회에 집는다
                if dropped and on_daywork:
                    on_daywork(dropped)
                req = read("inbox/print.json")
                what = decide(req, handled, datetime.datetime.now(datetime.timezone.utc))
                if what != "skip":
                    handled = req["id"]
                    _save_last(handled)       # 뽑다가 죽어도 같은 요청을 다시 뽑지 않게 먼저 적는다
                    if what == "print":
                        handle(req, log, notify)
                    else:
                        log(f"⏭ [순회판] {req['at']} 요청은 10분이 지나 뽑지 않음")
            last_err = None
        except Exception as e:
            if str(e) != last_err:            # 같은 오류(인터넷 끊김 등)를 5초마다 도배하지 않는다
                log(f"⚠ [순회판] {e}")
                last_err = str(e)
        time.sleep(POLL_SEC)


def main(argv):
    if "--watch" in argv:
        watch()
        return 0
    args = [a for a in argv if not a.startswith("--")]
    date = args[0] if args else work_date()
    summary = save_and_print(date, do_print="--save" not in argv)
    if summary is None:
        print(f"{date} 순회판이 아직 올라오지 않았다 — 폰 [진단]에서 PC 전송 상태를 확인")
        return 2
    print(f"{summary} — {'저장만 했다' if '--save' in argv else '인쇄로 보냈다'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
