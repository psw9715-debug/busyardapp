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


_받은때 = [0.0]
받은지_얼마 = 10        # 이 안에 또 받으러 가지 않는다 (초)


def pull(꼭=False):
    """inbox 가지를 받아 둔다.

    바로 앞에 받았으면 건너뛴다. watch() 가 받은 직후에 fetch() 가 또 받으러 가서,
    종이 인쇄 때마다 1.4초를 거저 쓰고 있었다 (2026-10-26). 폰은 판을 먼저 올리고
    그 다음에 요청을 올리므로, 요청이 보이는 받음에는 판도 이미 함께 들어와 있다.
    """
    import time as _t
    if not 꼭 and _t.time() - _받은때[0] < 받은지_얼마:
        return
    must(git("fetch", "-q", "origin", f"+refs/heads/inbox:{INBOX_REF}"), "GitHub 받기")
    _받은때[0] = _t.time()


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


def 결과합치기(앞, status, 몇=10):
    """새 결과를 맨 위에 두고, 최근 결과들을 '최근' 에 함께 싣는다.

    ★ [2026-11-03] status.json 은 한 장이다. 엑셀 넣기와 종이 인쇄를 연달아 누르면
       뒤 결과가 앞 결과를 덮어 폰이 앞 것을 끝내 못 봤다. 폰은 제 요청 id 를 '최근' 에서 찾는다.
    """
    최근 = [status] + [x for x in ((앞 or {}).get("최근") or []) if x.get("id") != status.get("id")]
    return {**status, "최근": [{k: v for k, v in x.items() if k != "최근"} for x in 최근[:몇]]}


def write_status(status):
    """폰에 결과를 알린다 (inbox/status.json) — 최근 결과들도 함께"""
    try:
        앞 = read("inbox/status.json")
    except Exception:
        앞 = None
    write_file("inbox/status.json", 결과합치기(앞, status), f"PC 결과: {status['state']}")


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
        pull(꼭=True)
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
        pull(꼭=True)
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


def 기다리며할것(req):
    """A 를 기다리는 사이에도 바로 해도 되는 요청인가 — A 몫(엑셀 넣기·최종·저장)이 아닌 것."""
    return req.get("what", "paper") not in ("excel", "final", "save")


def 밀린요청(새것부터, 마지막, 처리함):
    """마지막으로 한 요청 뒤에 온 것들 → 오래된 차례로.

    ★ [2026-11-03] 폰은 inbox/print.json 한 장을 덮어쓴다. B 가 A 를 기다리는 동안
       누른 종이 인쇄 두 번이 다음 엑셀 요청에 덮여 사라졌다 (00:33:51·00:35:32).
       그래서 맨 끝 한 장이 아니라 그 사이의 것을 모두 본다. 같은 것(종류·차고지)을
       여러 번 눌렀으면 마지막 하나만 — 종이가 두 장 나오지 않게.
    """
    밀린 = []
    for r in 새것부터:
        if r.get("id") == 마지막:
            break
        밀린.append(r)
    끝 = {}
    for n, r in enumerate(reversed(밀린)):          # 오래된 차례
        끝[(r.get("what", "paper"), r.get("yard"))] = (n, r)
    return [r for _n, r in sorted(끝.values(), key=lambda x: x[0]) if r["id"] not in 처리함]


def 요청기록(몇=10):
    """inbox/print.json 의 지난 요청들 (새 것부터). 폰이 한 번 누를 때마다 커밋 하나다."""
    r = git("log", f"-{몇}", "--format=%H", INBOX_REF, "--", "inbox/print.json")
    out = []
    for h in (r.stdout or "").split():
        rr = git("show", f"{h}:inbox/print.json")
        if rr.returncode == 0:
            try:
                out.append(json.loads(rr.stdout))
            except ValueError:
                pass
    return out


_틈틈이 = [None]      # A 를 기다리는 동안 5초마다 부를 것 (watch 가 끼운다)


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


def hand_to_agent(req, log):
    """폰의 요청을 A 컴퓨터에 **바로** 건넨다 (Z: 의 요청.json).

    폰이 올린 것을 A 가 raw.githubusercontent.com 에서 보기까지 실제로 244초가
    걸렸다 — CDN 이 옛 것을 그대로 내주기 때문이고, 3초마다 두드려도 소용이 없다.
    반면 이 PC 는 git 으로 받으므로 몇 초면 본다. 그러니 이 PC 가 본 것을 같은
    랜의 Z: 에 그대로 놓아 주면 A 는 그 자리에서 집어 간다.

    판까지 함께 담는다 — A 가 바깥 망을 한 번도 타지 않게. 못 놓아도 그만이다
    (A 는 예전처럼 raw 로도 보고 있고, 이 PC 가 대신 적는 길도 그대로다).
    """
    try:
        import ops_fill
        yard = req.get("yard", "new")
        쪽지 = dict(req)
        board = read(f"inbox/{req['date']}-{yard}.json")
        if board is not None:
            쪽지["board"] = board
        os.makedirs(os.path.dirname(ops_fill.AGENT_REQUEST), exist_ok=True)
        tmp = ops_fill.AGENT_REQUEST + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(쪽지, f, ensure_ascii=False)
        os.replace(tmp, ops_fill.AGENT_REQUEST)     # 반만 쓰인 것을 A 가 읽지 않게
        log(f"📤 [순회판] A 컴퓨터에 바로 건넴 ({req.get('what')}"
            + (f", 판 {len(board.get('entries', {}))}자리" if board else ", 판 없음") + ")")
    except Exception as e:
        log(f"⚠ [순회판] A 컴퓨터에 바로 건네지 못함 — {e} (raw 로는 보입니다)")


def agent_note(req_id):
    """A 컴퓨터(엑셀을 열어 둔 PC)가 Z: 에 놓아 둔 쪽지. 이 요청 것이 아니면 None.

    A 는 GitHub 에 올릴 권한이 없다. 그래서 "적었다" 를 Z: 에 한 줄 놓고, 이미 그
    권한을 들고 도는 이 PC 가 폰에 전해 준다.
    """
    import ops_fill
    note = None
    # ★ [2026-11-02] A 1.9.0 부터 요청마다 따로 놓는다 (결과_요청번호.json).
    #    한 장을 돌려 쓰면 다음 요청이 덮어써 놓칠 수 있었다. 옛 한 장도 그대로 본다.
    for 길 in (os.path.join(os.path.dirname(ops_fill.AGENT_RESULT), f"결과_{req_id}.json"),
               ops_fill.AGENT_RESULT):
        try:
            with open(길, encoding="utf-8") as f:
                cand = json.load(f)
        except Exception:
            continue
        if cand.get("id") == req_id:
            note = cand
            break
    if note is None:
        return None
    # '집었습니다' 는 끝난 것이 아니다 — 그것으로 끝낸 척하면 안 된다 (2026-11-01)
    return None if note.get("state") == "working" else note


def agent_working(req_id):
    """A 가 그 요청을 **집어서 지금 적고 있는가.**

    2026-11-01 01:27 에 구차고지 판을 A 에게 건넸는데, A 가 30초 안에 답을 못 하자
    이 PC 가 가로채 대신 했다. 그런데 원본 엑셀이 열려 있어 **복사본에만** 들어갔고,
    사용자 눈에는 '엑셀에 안 들어갔다' 로 보였다. 바로 전 01:06 에는 A 가 59초 걸려
    끝냈으니 30초는 애초에 모자란 시간이었다.

    기다리는 시간만 늘리면 A 가 죽은 날 또 서서 기다린다. 그래서 A 가 **집었다는 것**을
    먼저 알리게 하고(agent.py tick), 이 PC 는 **집은 것을 보았을 때만** 길게 기다린다.
    """
    import ops_fill
    try:
        with open(ops_fill.AGENT_RESULT, encoding="utf-8") as f:
            note = json.load(f)
    except Exception:
        return False
    return note.get("id") == req_id and note.get("state") == "working"


def agent_alive(within=180):
    """A 컴퓨터의 받아쓰기가 돌고 있는가. 1분에 한 번 남기는 표시를 본다.

    2026-11-01: 300초였다. 이제 살아 있는 A 를 끝까지 기다리므로(wait_for_agent),
    멎은 것을 늦게 알아채면 그만큼 서서 기다린다. 심장 소리는 1분에 한 번이니
    세 번 놓친 180초면 멎은 것으로 본다.
    """
    import ops_fill
    try:
        with open(ops_fill.AGENT_ALIVE, encoding="utf-8") as f:
            at = json.load(f)["at"]
        when = datetime.datetime.fromisoformat(at.replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - when).total_seconds() < within
    except Exception:
        return False


def _쪽지요약():
    import ops_fill
    try:
        with open(ops_fill.AGENT_RESULT, encoding="utf-8") as f:
            n = json.load(f)
        return f"{n.get('id')} {n.get('state')} {n.get('at')}"
    except Exception as e:
        return f"못 읽음 ({type(e).__name__})"


def wait_for_agent(req_id, log, secs=360):
    """A 컴퓨터가 적고 쪽지를 놓을 때까지 기다린다. 안 집으면 내가 한다.

    2026-10-27: 180초였다. A 가 응답하지 않은 날 **3분을 그대로 서서 기다렸다**
                (01:52:29 건넴 → 01:55:30 포기). 그래서 30초로 줄였다.
    2026-11-01: 그 30초가 **너무 짧았다.** 실제로 잰 값은
                  01:05 요청 → 01:06:24 끝  (excel, 72대)  59초
                  01:27 요청 → 01:31:31 끝  (final, 79대)  4분 11초
                둘 다 30초를 한참 넘는다. 이 PC 가 32초에 가로채 같은 일을 또 했고,
                원본 엑셀이 열려 있어 **복사본에만** 들어갔다. 원본에는 A 가 4분 뒤에
                제대로 넣었지만, 그 사이 종이가 두 장 나오고 헛파일이 하나 생겼다.

    처음에는 '집었으면 길게, 안 집었으면 짧게' 로 두었는데 그것도 틀렸다. A 는 **집는
    데만 70초**가 걸렸다 (02:00:26 건넴 → 02:01:36 집음). 3초마다 들여다보지만 그 사이
    엑셀을 데우거나 앞 일을 하고 있으면 한참 뒤에야 본다.

    그래서 생각을 바로잡았다 — **살아 있는 A 와는 애초에 경쟁하지 않는다.**
      · A 가 살아 있으면 — 끝내든 못 끝내든 secs(6분)까지 **기다린다.** A 가 할 일이다.
      · A 가 꺼져 있으면 — 기다리지 않고 바로 내가 한다 (그 판단은 심장 소리로 한다).
      · 기다리는 중에 심장이 멎으면 — 그때 내가 이어받는다.

    가로채서 두 번 하면 종이가 두 장 나오고 헛파일이 생긴다. 늦는 것보다 그것이 나쁘다.
    '집었습니다' 쪽지는 이제 기록에 남기는 용도다 — 기다릴지 말지를 그것으로 정하지 않는다.
    """
    if not agent_alive():
        log("💤 [순회판] A 컴퓨터 받아쓰기가 꺼져 있다")
        return None
    until = time.time() + secs
    집었다 = False
    while True:
        남은 = until - time.time()             # 시계는 한 번만 읽는다
        if 남은 <= 0:
            break
        note = agent_note(req_id)
        if note:
            log(f"📨 [순회판] A 컴퓨터: {note['msg']}")
            return note
        if not 집었다 and agent_working(req_id):
            집었다 = True
            log("🤝 [순회판] A 컴퓨터가 집었습니다 — 끝낼 때까지 기다립니다")
        if not agent_alive():                  # 도중에 멎었다
            log("💤 [순회판] A 컴퓨터가 멎었다 (살아있음 신호가 끊김)")
            return None
        if int(남은) % 30 == 0:
            log(f"⏳ [순회판] A 를 기다리는 중 — 요청 {req_id} · 지금 결과 쪽지: {_쪽지요약()}")
        if _틈틈이[0] and int(남은) % 5 == 0:      # 그 사이 폰이 누른 종이 인쇄는 바로 뽑는다
            try:
                _틈틈이[0]()
            except Exception as e:
                log(f"⚠ [순회판] 기다리는 사이 다른 요청을 보다가 — {e}")
        time.sleep(1)
    log("⌛ [순회판] A 컴퓨터가 %d분을 넘겼다 (%s)"
        % (secs // 60, "집고도 못 끝냈다" if 집었다 else "집지도 않았다"))
    return None


def handle(req, log, notify=None):
    """폰이 보낸 요청 하나를 처리하고 결과를 폰에 알린다"""
    now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: E731
    kind = req.get("what", "paper")
    what = {"excel": "운영관리 엑셀", "pull": "엑셀에서 가져오기",
            "final": "최종 인쇄", "check": "점검 대상 다시 세기",
            "save": "A 컴퓨터 엑셀 저장"}.get(kind, "종이 인쇄")

    if kind == "save":
        # 폰이 차고지 앱을 열면서 A 컴퓨터에 '엑셀 한 번 저장' 을 부탁한 것이다.
        # 이 PC 는 할 일이 없다 — 종이로 뽑아서도 안 되고(그것이 기본 갈래다),
        # status.json 을 건드려서도 안 된다(사람이 기다리는 결과를 덮는다).
        log("💾 [순회판] 폰 요청(A 컴퓨터 엑셀 저장) — A 컴퓨터 몫이라 넘깁니다")
        hand_to_agent(req, log)
        return

    if kind in ("excel", "final"):
        hand_to_agent(req, log)       # 기다리기 전에 먼저 건넨다 — 이것이 빠른 길이다

    try:
        if kind == "check":
            # 2회차를 시작할 때 폰이 조용히 부른다. 인쇄도 입력도 하지 않고,
            # 지금 엑셀에 적힌 것만으로 '아직 찾을 차' 를 다시 세어 내려보낸다.
            state, msg = "done", "다시 셈"
        elif kind == "pull":
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
            # ★ [2026-11-02] **넣는 것은 A 만 한다** (사용자 결정). 21~02시엔 원본이 A 에
            #    열려 있어 이 PC 가 넣으면 쓸모없는 복사본(차고지입력_*.xlsx)만 생겼다 —
            #    11-02 01:05·01:52 에 실제로 그랬다. A 가 못 하면 그 사정을 폰에 알린다.
            if not note:
                raise RuntimeError(
                    "A 컴퓨터 받아쓰기가 꺼져 있습니다 — A 컴퓨터를 확인해 주세요"
                    if not agent_alive() else
                    "A 컴퓨터가 6분 안에 끝내지 못했습니다 — A 컴퓨터 엑셀을 확인해 주세요")
            if kind == "excel":
                state, msg = "done", note["msg"]
            else:
                state, msg = "done", ops_fill.run_final(
                    board_date=req["date"], log=log, yard=yard,
                    recorded=note["msg"] if note else None,
                    printed=bool(note and note.get("printed")))
        else:
            summary = save_and_print(req["date"], yard=req.get("yard", "new"))
            state, msg = ("nodata", f"{req['date']} 판이 GitHub 에 없습니다") if summary is None else ("done", summary)
    except Exception as e:                    # 프린터·엑셀 오류도 폰에 그대로 알린다
        state, msg = "fail", str(e)
    log(f"{'🖨' if state == 'done' else '⚠'} [순회판] 폰 요청({what}) — {msg}")
    # 'check' 는 폰이 2회차를 시작할 때 조용히 부르는 것이다. status.json 을 건드리면
    # 사람이 기다리고 있는 인쇄 결과를 덮어쓰므로, 그것만 적지 않는다.
    if kind != "check":
        write_status({"id": req["id"], "state": state, "msg": msg, "at": now()})
    if state == "done":
        push_checklist(req, log)
    if notify and kind != "check":
        notify(state == "done", f"{what} — {msg}")


def push_checklist(req, log):
    """오늘 밤 아직 찾아다녀야 할 차 목록을 폰에 내려보낸다 (inbox/checklist.json).

    폰은 이것과 제가 적은 판을 견주어, 2회차를 도는 동안 "아직 못 본 차" 를 센다.

    2026-10-20: 전에는 내일 운행차량을 통째로(134대) 내려보내서, 2회차 인쇄에서
    '못 본 차' 가 백 대 넘게 떴다. 지금은 엑셀 자신의 "차찾아" 를 바탕으로 한다 —
    1차고지에서 본 차도, 신차고지 1차에 적은 차도, 내일 안 나가는 휴차도 빠진 목록이다.
    """
    try:
        import ops_fill
        date = datetime.date.fromisoformat(req["date"]) + datetime.timedelta(days=1)
        cars, 헤아림 = ops_fill.checklist_cars(date=date)
        if not 헤아림["운행"]:
            return                            # 시트를 못 읽은 것이다 — 빈 목록을 내려보내지 않는다
        if 헤아림["차찾아"] >= 헤아림["운행"]:
            # 한 대도 못 찾았다 = 고정차고지_입력이 아직 비어 있다는 뜻이다.
            # (1차를 엑셀로 보내기 전에 2회차를 누른 경우) 그 134대를 내려보내면
            # 애써 줄여 둔 목록을 도로 덮어쓰므로, 적기 전에는 그냥 두고 나간다.
            log(f"⏭ [순회판] 아직 엑셀에 적힌 것이 없어 점검 대상을 그대로 둠 "
                f"(운행 {헤아림['운행']}대 전부가 차찾아)")
            return
        write_file("inbox/checklist.json", {
            "id": req["id"], "date": req["date"], "yard": req.get("yard", "new"),
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "cars": cars,
        }, f"{req['date']} 점검 대상 {len(cars)}대")
        뺀말 = f" → 휴차 {헤아림['휴차뺌']}대 뺌" if 헤아림["휴차뺌"] else ""
        log(f"📋 [순회판] 점검 대상 {len(cars)}대를 폰에 내려보냄 "
            f"(내일 운행 {헤아림['운행']}대 → 차찾아 {헤아림['차찾아']}대{뺀말})")
    except Exception as e:
        log(f"⚠ [순회판] 점검 대상을 내려보내지 못함 — {e}")


def watch(log=print, stop=None, notify=None, on_daywork=None):
    """inbox 가지를 5초마다 보고, 폰이 보낸 요청을 처리한다. stop() 이 참이면 끝낸다.

    on_daywork(떨군 파일 목록) — 차량 특이사항이 새로 왔을 때 부른다.
    받는 일은 여기서 하고, 엑셀에 적는 일은 일지 프로그램이 한다.
    """
    handled = _load_last()
    seen = None
    last_err = None
    처리함 = set()        # 기다리는 사이 먼저 한 것

    def 하기(req, 먼저=False):
        nonlocal handled
        if not 먼저:
            handled = req["id"]
            _save_last(handled)       # 뽑다가 죽어도 같은 요청을 다시 뽑지 않게 먼저 적는다
        처리함.add(req["id"])
        if decide(req, None, datetime.datetime.now(datetime.timezone.utc)) == "stale":
            log(f"⏭ [순회판] {req['at']} 요청은 10분이 지나 뽑지 않음")
            return
        handle(req, log, notify)

    def 틈틈이():
        """A 를 기다리는 사이 — 새로 온 것 가운데 A 몫이 아닌 것(종이 인쇄 등)만 바로 한다."""
        pull(꼭=True)
        for req in 밀린요청(요청기록(), handled, 처리함):
            if 기다리며할것(req):
                log(f"⚡ [순회판] A 를 기다리는 사이 온 요청을 먼저 합니다 ({req.get('what', 'paper')})")
                하기(req, 먼저=True)
    _틈틈이[0] = 틈틈이
    log("📡 [순회판] 폰 인쇄 요청 대기 시작")
    # 첫 인쇄가 느린 것은 엑셀을 띄우는 3초 때문이다. 사람이 기다리지 않는 지금
    # 미리 치러 둔다 — 누르는 순간에는 0.8초면 끝난다. 이 스레드가 쓸 것을 데운다.
    try:
        import print_board
        if print_board.warm_print_excel():
            log("🔥 [순회판] 인쇄용 엑셀을 미리 데워 뒀습니다")
    except Exception as e:
        log(f"⚠ [순회판] 인쇄용 엑셀을 데우지 못함 — {e} (인쇄는 그대로 됩니다)")
    while not (stop and stop()):
        try:
            sha = remote_sha()
            if sha and sha != seen:
                pull(꼭=True)
                seen = sha
                for got in take_files(log):          # 사진이 함께 와 있으면 먼저 내린다
                    if notify:
                        notify(True, f"사진 받음 — {os.path.basename(got)}")
                dropped = take_daywork(log)          # 차량 특이사항도 같은 기회에 집는다
                if dropped and on_daywork:
                    on_daywork(dropped)
                for req in 밀린요청(요청기록(), handled, 처리함):
                    하기(req)
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
