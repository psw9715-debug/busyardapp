# -*- coding: utf-8 -*-
"""폰이 GitHub inbox 가지에 올린 그날 판을 받아 저장하고 인쇄한다.

폰과 PC 는 서로 직접 닿을 수 없다 (폰은 LTE, PC 는 사내 유선). 둘 다 닿는 GitHub
저장소의 inbox 가지를 우편함처럼 쓴다.

    폰  inbox/<날짜>.json   그날 판 (입력이 멎을 때마다 올린다)
    폰  inbox/print.json    인쇄 요청 {id, date, at} — [인쇄] 를 누르면
    PC  inbox/status.json   인쇄 결과 {id, state, msg, at} — 폰이 이걸 보고 "인쇄 완료" 를 띄운다

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

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "reference", "차고지 프린트.xlsx")
SHEET = "신차고지"
OUT_DIR = os.path.join(ROOT, "기록")
LAST_FILE = os.path.join(OUT_DIR, ".last_print")   # 이미 처리한 인쇄 요청 — 껐다 켜도 두 번 뽑지 않게
INBOX_REF = "refs/remotes/origin/inbox"
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


def spot_cells():
    """순회 번호 -> 엑셀 칸 (src/yard-data.js 에서 읽는다)"""
    with open(os.path.join(ROOT, "src", "yard-data.js"), encoding="utf-8") as f:
        text = f.read()
    yard = json.loads(text[text.index("{"):text.rindex("}") + 1])
    return {c["spot"]: c["xl"] for c in yard["cells"] if c["kind"] == "spot"}


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


def fetch(date):
    """그날 판. 아직 안 올라왔으면 None"""
    pull()
    return read(f"inbox/{date}.json")


def write_status(status):
    """폰에 인쇄 결과를 알린다 — inbox/status.json 한 파일만 바꿔 inbox 가지에 올린다.

    폰이 그 사이 판을 올렸으면 push 가 거절되므로 다시 받아서 그 위에 쌓는다.
    """
    body = json.dumps(status, ensure_ascii=False)
    index = os.path.join(tempfile.gettempdir(), "busyard-inbox.index")
    env = {"GIT_INDEX_FILE": index}
    for _ in range(3):
        pull()
        blob = must(git("hash-object", "-w", "--stdin", stdin=body), "상태 파일 만들기")
        must(git("read-tree", INBOX_REF, env=env), "색인 읽기")
        must(git("update-index", "--add", "--cacheinfo", f"100644,{blob},inbox/status.json", env=env), "색인 갱신")
        tree = must(git("write-tree", env=env), "트리 만들기")
        commit = must(git("commit-tree", tree, "-p", INBOX_REF, "-m", f"PC 인쇄 결과: {status['state']}"), "커밋")
        if git("push", "-q", "origin", f"{commit}:refs/heads/inbox").returncode == 0:
            return
    raise RuntimeError("인쇄 결과를 GitHub 에 올리지 못했다")


# ---- 엑셀 ---------------------------------------------------------------

def fill(board, out_path):
    """판을 인쇄 시트에 채워 out_path 로 저장한다. 채운 칸 수를 돌려준다."""
    if board.get("layout") != current_layout():
        raise ValueError(f"자리 번호 체계가 다르다 (폰 {board.get('layout')}, PC {current_layout()}) — "
                         "폰 앱과 PC 의 busyardapp 을 둘 다 최신으로 맞출 것")
    cells = spot_cells()
    entries = board["entries"]
    has_round2 = any(e.get("round", 1) == 2 for e in entries.values())

    wb = openpyxl.load_workbook(TEMPLATE)       # 서식이 살아 있어야 하므로 data_only 를 쓰지 않는다
    for name in wb.sheetnames:
        if name != SHEET:
            wb.remove(wb[name])                 # 인쇄할 시트만 남긴다
    ws = wb[SHEET]

    n = 0
    for spot, e in entries.items():
        xl = cells.get(int(spot))
        if not xl or e.get("status") != "filled" or not e.get("plate"):
            continue                            # 공차는 종이에서 빈 칸
        cell = ws[xl]
        cell.value = e["plate"]
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


def save_and_print(date, do_print=True):
    """그날 판을 받아 저장하고 (인쇄하고) 한 줄 요약을 돌려준다. 판이 없으면 None"""
    board = fetch(date)
    if board is None:
        return None
    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(OUT_DIR, f"{date} 신차고지")
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


def handle(req, log):
    """인쇄 요청 하나를 처리하고 폰에 결과를 알린다"""
    now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: E731
    try:
        summary = save_and_print(req["date"])
        if summary is None:
            state, msg = "nodata", f"{req['date']} 판이 GitHub 에 없습니다"
        else:
            state, msg = "done", summary
    except Exception as e:                    # 프린터·엑셀 오류도 폰에 그대로 알린다
        state, msg = "fail", str(e)
    log(f"{'🖨' if state == 'done' else '⚠'} [순회판] 폰 인쇄 요청 — {msg}")
    write_status({"id": req["id"], "state": state, "msg": msg, "at": now()})


def watch(log=print, stop=None):
    """inbox 가지를 5초마다 보고, 새 인쇄 요청이 오면 인쇄한다. stop() 이 참이면 끝낸다."""
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
                req = read("inbox/print.json")
                what = decide(req, handled, datetime.datetime.now(datetime.timezone.utc))
                if what != "skip":
                    handled = req["id"]
                    _save_last(handled)       # 뽑다가 죽어도 같은 요청을 다시 뽑지 않게 먼저 적는다
                    if what == "print":
                        handle(req, log)
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
