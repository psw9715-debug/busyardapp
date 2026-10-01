# -*- coding: utf-8 -*-
"""차고지 받아쓰기 — 운영관리 엑셀을 열어 둔 PC(A)에 상주하며 순찰판을 받아 적는다.

왜 필요한가
    그날 입출차 운영관리 엑셀은 Z: 에 있고, 보통 사무실 PC(A)가 열어 두고 쓴다.
    엑셀은 열려 있는 파일을 다른 PC 가 고쳐 쓸 수 없으므로, 지금까지는 "A 에서 좀
    닫아 주세요" 하고 부탁한 뒤에야 넣을 수 있었다.
    이 프로그램을 A 에 띄워 두면, 폰에서 [운영관리 엑셀에 넣기] 를 누를 때
    **A 가 자기 엑셀에 직접 적고 저장한다.** 닫을 필요가 없다.

어떻게 받아 오는가
    폰은 공개 저장소의 inbox 가지에 요청과 판을 올린다. 이 프로그램은 그것을
    HTTPS 로 읽기만 한다 — 토큰도, git 도, 사내망 공유도 필요 없다.
    바뀐 것이 없으면 304 로 돌아오므로 GitHub 의 시간당 횟수도 거의 쓰지 않는다.

무엇을 적는가
    `고정차고지_입력` 시트의 그 차고지 블록에, 자리마다 **차량번호 한 줄만** 적는다.
    그 아래 이름·출근시각은 원래 수식이라 저절로 따라 붙는다. 공차와 승용차는 빈 칸이다.

    신차고지(6차고지)   38~97행   (순찰 양식 3행이 38행 — 35줄 아래)
    구차고지(1·2차고지)  1~34행   (순찰 양식과 행이 그대로 겹친다)
"""
import base64
import datetime
import io
import json
import os
import re
import ssl
import sys
import time
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request

APP_NAME = "차고지 받아쓰기"
REPO = "psw9715-debug/busyardapp"
# api.github.com 은 토큰 없이 한 시간에 60번뿐이다. 10초마다 보면 금세 막힌다.
# raw 는 그 제한이 없으므로 받아 오기만 하는 이쪽은 raw 로 읽는다.
RAW = f"https://raw.githubusercontent.com/{REPO}/inbox/inbox/{{name}}"
# 결과를 폰에 알리는 것은 올리는 일이라 토큰이 있어야 한다. 설치할 때 받아 둔다.
# 올리기는 하루에 몇 번뿐이므로 api.github.com 의 한도(토큰 있으면 시간당 5천)로 넉넉하다.
API = f"https://api.github.com/repos/{REPO}/contents/inbox/{{name}}"
#
# 얼마나 자주 보는가
#   폰은 셀룰러, 이 PC 는 사내망 안에 있어 폰이 이 PC 를 직접 부를 길이 없다.
#   그래서 이쪽에서 우편함을 들여다보는 수밖에 없는데, 아무도 순찰하지 않는
#   낮에까지 10초마다 볼 일은 없다. 순찰하는 밤에만 바짝 보고, 낮에는 길게 쉰다.
#   낮에 급히 넣어야 하면 시작 메뉴에서 한 번 껐다 켜면 그 자리에서 본다.
POLL_BUSY = 10            # 21시~9시 — 순찰하고 엑셀에 넣는 시간
POLL_IDLE = 900           # 그 밖 — 15분에 한 번만 (하루 요청 수가 1/90 로 줄어든다)
BUSY_FROM, BUSY_TO = 21, 9


def poll_sec(now=None):
    h = (now or datetime.datetime.now()).hour
    return POLL_BUSY if h >= BUSY_FROM or h < BUSY_TO else POLL_IDLE
STALE = datetime.timedelta(minutes=10)      # 이보다 오래된 요청은 적지 않는다

BASE = r"Z:\교통사업처_버스운영센터\상황실"
KEYWORD = "입출차 운영관리"
SHEET = "고정차고지_입력"
YARDS = {
    "new": {"data": "yard-data.js", "offset": 35},
    "old": {"data": "yard-old-data.js", "offset": 0},
}

HOME = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "차고지받아쓰기")
LOG_FILE = os.path.join(HOME, "받아쓰기.log")
LAST_FILE = os.path.join(HOME, "마지막요청.txt")
TOKEN_FILE = os.path.join(HOME, "토큰.txt")


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    os.makedirs(HOME, exist_ok=True)
    try:
        with io.open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass
    if sys.stdout:                   # 창 없이 묶은 exe 는 내보낼 곳이 없다
        print(line)


# ---- 우편함 읽기 ---------------------------------------------------------

def _ssl_context():
    """사내망이 HTTPS 를 자체 인증서로 다시 서명한다. 윈도우는 믿지만 파이썬 3.13 의
    엄격 검사가 그 형식을 거부하므로, 인증서 확인은 두고 엄격 검사만 뺀다."""
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


_etags = {}


def fetch(name):
    """inbox 의 파일 하나. 지난번과 같으면 None (바뀐 것이 없다)."""
    # raw 는 5분쯤 묵은 것을 내줄 수 있다. 시각을 붙여 늘 지금 것을 받는다.
    url = f"{RAW.format(name=urllib.parse.quote(name))}?t={int(time.time())}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "busyard-agent",
        **({"If-None-Match": _etags[name]} if name in _etags else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as res:
            if res.headers.get("ETag"):
                _etags[name] = res.headers["ETag"]
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (304, 404):
            return None          # 바뀐 것이 없거나 아직 없는 파일
        raise


def token():
    """설치할 때 받아 둔 토큰. 없으면 엑셀만 고치고 폰에는 알리지 못한다."""
    # 설치 프로그램이 넣어 준 파일이라 인코딩이 무엇일지 못 믿는다. 토큰은 영문·숫자뿐이다.
    try:
        with io.open(TOKEN_FILE, "rb") as f:
            return f.read().decode("utf-8", "ignore").strip()
    except Exception:
        return ""


def _api(name, method="GET", body=None, tok=""):
    req = urllib.request.Request(API.format(name=name), method=method,
                                 data=json.dumps(body).encode("utf-8") if body else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "busyard-agent")
    req.add_header("Authorization", f"Bearer {tok}")
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as res:
        return json.loads(res.read().decode("utf-8"))


def report(req_id, state, msg):
    """폰에 결과를 돌려준다 (inbox/status.json). 폰은 이것을 보고 결과를 띄운다.

    사무실 PC 도 같은 파일에 쓴다. 한쪽이 이미 '됐다' 고 적어 둔 것을 이쪽의
    실패로 덮지는 않는다 — 어느 PC 든 한 곳이라도 넣었으면 넣어진 것이다.
    """
    tok = token()
    if not tok:
        log("ⓘ 토큰이 없어 폰에는 알리지 못했습니다 (엑셀은 고쳤습니다)")
        return
    sha = None
    try:
        cur = _api("status.json?ref=inbox", tok=tok)
        sha = cur.get("sha")
        now = json.loads(base64.b64decode(cur["content"]).decode("utf-8"))
        if now.get("id") == req_id and now.get("state") == "done" and state != "done":
            return
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
    body = {
        "message": f"A 결과: {state}",
        "branch": "inbox",
        "content": base64.b64encode(json.dumps({
            "id": req_id, "state": state, "msg": msg, "at": at.replace("+00:00", "Z"),
        }, ensure_ascii=False).encode("utf-8")).decode("ascii"),
    }
    if sha:
        body["sha"] = sha
    try:
        _api("status.json", "PUT", body, tok)
    except urllib.error.HTTPError as e:
        if e.code not in (409, 422):
            raise
        # 사무실 PC 가 그 틈에 같은 파일을 바꿨다. 지금 것을 다시 받아 그 위에 쓴다.
        body["sha"] = _api("status.json?ref=inbox", tok=tok).get("sha")
        _api("status.json", "PUT", body, tok)
    log(f"📨 폰에 알렸습니다 — {state} · {msg}")


# ---- 자리와 칸 -----------------------------------------------------------

def _data_path(name):
    """PyInstaller 로 묶으면 임시 폴더에 풀린다"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


_cells = {}


def block_cells(yard):
    """순회 번호 -> (행, 열). 순찰 양식의 칸을 차고지만큼 내린 것이다."""
    if yard not in _cells:
        cfg = YARDS.get(yard, YARDS["new"])
        with io.open(_data_path(cfg["data"]), encoding="utf-8") as f:
            text = f.read()
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        out = {}
        for c in data["cells"]:
            if c["kind"] != "spot":
                continue
            m = re.match(r"([A-Z]+)(\d+)", c["xl"])
            col = 0
            for ch in m.group(1):
                col = col * 26 + (ord(ch) - 64)
            out[c["spot"]] = (int(m.group(2)) + cfg["offset"], col)
        _cells[yard] = out
    return _cells[yard]


def runs(want):
    """{(행,열): 값} 을 가로로 이어진 토막으로 묶는다 — 한 칸씩 쓰면 엑셀이 느리다"""
    out = []
    for row in sorted({r for r, _ in want}):
        cols = sorted(c for r, c in want if r == row)
        run, start = [], None
        for col in cols:
            if start is not None and col == start + len(run):
                run.append(want[(row, col)])
                continue
            if run:
                out.append((row, start, run))
            start, run = col, [want[(row, col)]]
        if run:
            out.append((row, start, run))
    return out


# ---- 그날 파일 찾기 (출퇴근 관리 프로그램과 같은 방식) ----------------------

def work_date(now=None):
    now = now or datetime.datetime.now()
    day = now.date() - datetime.timedelta(days=1) if now.hour < 9 else now.date()
    return day


def find_excel(date):
    year = str(date.year)
    root = next((os.path.join(BASE, d) for d in sorted(os.listdir(BASE))
                 if d.split()[-1:] == [year] and os.path.isdir(os.path.join(BASE, d))), None)
    if not root:
        raise FileNotFoundError(f"{year} 연도 폴더 없음")
    month = os.path.join(root, f"00 {date:%Y%m}")
    if not os.path.isdir(month):
        raise FileNotFoundError(f"{date:%Y%m} 월 폴더 없음")
    day = next((os.path.join(month, d) for d in sorted(os.listdir(month))
                if d.startswith(f"{date:%m%d}") and os.path.isdir(os.path.join(month, d))), None)
    if not day:
        raise FileNotFoundError(f"{date:%m%d} 날짜 폴더 없음")
    hits = [f for f in sorted(os.listdir(day))
            if KEYWORD in f and f.endswith((".xlsx", ".xlsm", ".xls")) and not f.startswith("~$")]
    if not hits:
        raise FileNotFoundError(f"{KEYWORD} 파일 없음")
    hits.sort(key=lambda f: (not f.startswith(f"{date:%m%d}"), f))
    return os.path.join(day, hits[0])


# ---- 엑셀에 적기 ---------------------------------------------------------

def running_workbook(path):
    """지금 열려 있는 그 통합문서를 찾는다. 없으면 None.

    엑셀은 열어 둔 파일을 **실행 중인 개체 표(ROT)** 에 전체 경로로 올려 둔다.
    거기서 찾으면 어느 엑셀 창에서 열었든 그 문서를 그대로 집을 수 있다 —
    이 프로그램이 있는 이유가 바로 "열어 둔 그 문서에 적는 것" 이다.
    """
    import pythoncom
    import win32com.client

    want = os.path.normcase(os.path.abspath(path))
    try:
        rot = pythoncom.GetRunningObjectTable()
        ctx = pythoncom.CreateBindCtx(0)
    except Exception:
        return None
    for moniker in rot:
        try:
            name = moniker.GetDisplayName(ctx, None)
        except Exception:
            continue
        if not name.lower().endswith((".xlsx", ".xlsm", ".xls")):
            continue
        try:
            if os.path.normcase(os.path.abspath(name)) != want:
                continue
            obj = rot.GetObject(moniker)
            return win32com.client.Dispatch(obj.QueryInterface(pythoncom.IID_IDispatch))
        except Exception:
            continue
    return None


def write_board(board, path, log=log):
    """판을 그 엑셀에 적고 저장한다. (넣은 대수, 이미 열려 있었는가)"""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()

    yard = board.get("yard", "new")
    cells = block_cells(yard)

    want = {rc: None for rc in cells.values()}
    written = 0
    for spot, e in board["entries"].items():
        rc = cells.get(int(spot))
        if not rc or e.get("status") != "filled" or not e.get("plate"):
            continue             # 공차와 승용차는 빈 칸으로 둔다
        want[rc] = int(e["plate"])
        written += 1

    wb = running_workbook(path)
    was_open = wb is not None
    if was_open:
        excel = wb.Application          # 열어 둔 사람의 엑셀을 그대로 쓴다
        mine = False
    else:
        excel = win32com.client.DispatchEx("Excel.Application")
        try:
            excel.Visible = False
            excel.DisplayAlerts = False
        except Exception:
            pass
        mine = True
        wb = excel.Workbooks.Open(path)
        if wb.ReadOnly:
            # 누가 열고 있는데 ROT 에서 못 찾은 경우다. 읽기 전용으로 적으면
            # 저장이 안 되는데도 다 된 것처럼 보이므로, 여기서 분명히 멈춘다.
            wb.Close(SaveChanges=False)
            excel.Quit()
            raise PermissionError("엑셀이 읽기 전용으로 열립니다 — 다른 곳에서 쓰고 있는 파일입니다")

    calc = None
    try:
        try:
            calc = excel.Calculation
            excel.Calculation = -4135      # 수식이 많아 한 칸씩 다시 계산하면 몇 분 걸린다
        except Exception:
            calc = None
        ws = wb.Worksheets(SHEET)
        for row, col, run in runs(want):
            ws.Range(ws.Cells(row, col), ws.Cells(row, col + len(run) - 1)).Value = (tuple(run),)
        if calc is not None:
            excel.Calculation = -4105
        wb.Save()
    finally:
        if mine:
            wb.Close(SaveChanges=False)
            excel.Quit()
    return written, was_open


# ---- 요청 처리 -----------------------------------------------------------

def last_done():
    try:
        with io.open(LAST_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception:
        return None


def remember(req_id):
    os.makedirs(HOME, exist_ok=True)
    with io.open(LAST_FILE, "w", encoding="utf-8") as f:
        f.write(req_id)


def decide(req, done, now):
    """'write' 적는다 / 'skip' 이미 했거나 우리 일이 아니다 / 'stale' 너무 오래된 요청"""
    if not req or req.get("id") == done:
        return "skip"
    if req.get("what") not in ("excel", "final"):
        return "skip"            # 종이 인쇄와 가져오기는 B(사무실 PC)가 한다
    at = datetime.datetime.fromisoformat(req["at"].replace("Z", "+00:00"))
    return "stale" if now - at > STALE else "write"


def handle(req):
    """엑셀에 적고, 다 되면 폰에 알린다.

    [최종 인쇄] 는 적는 것으로 끝나지 않고 사무실 PC 가 종이로 뽑아야 끝이다.
    그 결과는 사무실 PC 가 알리므로, 이쪽은 적기만 하고 입을 다문다.
    """
    yard = req.get("yard", "new")
    tell = req.get("what") == "excel"
    try:
        date = datetime.date.fromisoformat(req["date"]) + datetime.timedelta(days=1)
        board = fetch(f"{req['date']}-{yard}.json")
        if board is None:
            _etags.pop(f"{req['date']}-{yard}.json", None)  # 조건부 요청 때문에 비었을 수 있다
            board = fetch(f"{req['date']}-{yard}.json")
        if board is None:
            raise FileNotFoundError(f"{req['date']} {yard} 판을 못 받았습니다")
        path = find_excel(date)
        n, was_open = write_board(board, path)
    except Exception as e:
        log(f"⚠ {type(e).__name__}: {e}")
        if tell:
            try:
                report(req["id"], "error", f"A 컴퓨터: {e}")
            except Exception as e2:
                log(f"⚠ 폰에 알리지 못했습니다 — {type(e2).__name__}: {e2}")
        return

    log(f"✅ {date:%m/%d} {'열려 있던 ' if was_open else ''}엑셀에 {n}대 적고 저장했습니다")
    if tell:
        try:
            report(req["id"], "done", f"A 컴퓨터가 {'열어 둔 ' if was_open else ''}엑셀에 {n}대")
        except Exception as e:
            log(f"⚠ 적기는 했는데 폰에 알리지 못했습니다 — {type(e).__name__}: {e}")


def tick():
    req = fetch("print.json")
    if req is None:
        return
    what = decide(req, last_done(), datetime.datetime.now(datetime.timezone.utc))
    if what == "skip":
        return
    remember(req["id"])          # 적다가 죽어도 같은 요청을 두 번 적지 않게 먼저 적는다
    if what == "stale":
        log(f"⏭ {req['at']} 요청은 10분이 지나 건너뜁니다")
        return
    handle(req)


def loop(stop):
    log(f"{APP_NAME} 시작 — 밤에는 {POLL_BUSY}초, 낮에는 {POLL_IDLE // 60}분마다 확인합니다")
    last_err = None
    while not stop.is_set():
        try:
            tick()
            last_err = None
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if msg != last_err:          # 같은 오류(인터넷 끊김 등)를 도배하지 않는다
                log(f"⚠ {msg}")
                last_err = msg
            if os.environ.get("BUSYARD_DEBUG"):
                traceback.print_exc()
        stop.wait(poll_sec())


def selftest():
    """설치한 뒤 제대로 돌아가는지 보는 점검. 결과를 기록 파일에 적고 끝낸다.
    창이 없는 프로그램이라 화면에 띄울 수 없으므로 기록으로 남긴다."""
    bad = 0
    for yard, want in (("new", 196), ("old", 90)):
        n = len(block_cells(yard))
        log(f"점검 · {yard} 자리표 {n}칸 ({'정상' if n == want else '이상, ' + str(want) + '칸이어야 한다'})")
        bad += n != want
    try:
        fetch("print.json")
        log("점검 · 우편함 읽기 정상")
    except Exception as e:
        bad += 1
        log(f"점검 · 우편함 읽기 실패 — {type(e).__name__}: {e}")
    tok = token()
    if not tok:
        log("점검 · 토큰이 없다 — 엑셀은 고치지만 폰에 결과를 알리지 못한다")
    else:
        try:
            try:
                _api("status.json?ref=inbox", tok=tok)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
            log("점검 · 토큰 정상 — 폰에 결과를 알릴 수 있다")
        except Exception as e:
            bad += 1
            log(f"점검 · 토큰이 듣지 않는다 — {type(e).__name__}: {e}")
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
        ver = excel.Version
        excel.Quit()
        log(f"점검 · 엑셀 {ver} 정상")
    except Exception as e:
        bad += 1
        log(f"점검 · 엑셀을 열 수 없다 — {type(e).__name__}: {e}")
    log(f"점검 · {'모두 정상' if not bad else str(bad) + '가지 이상'}")
    return 1 if bad else 0


def main():
    """창도 트레이 아이콘도 없다. 보이지 않게 돌면서 엑셀만 고친다.
    무엇을 적었는지는 기록 파일에만 남는다. 끄려면 시작 메뉴의 [끄기]."""
    if "--점검" in sys.argv or "--selftest" in sys.argv:
        sys.exit(selftest())
    loop(threading.Event())


if __name__ == "__main__":
    main()
