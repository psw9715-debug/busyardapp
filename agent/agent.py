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
import datetime
import gc
import io
import json
import os
import re
import ssl
import subprocess
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

# 새벽 2시 5분에 운영관리 엑셀을 저장하고 닫는다.
#   2시 10분에 B(사무실) PC 가 출퇴근 관리 프로그램으로 그 엑셀을 열어야 하는데,
#   여기서 열어 두고 있으면 저쪽은 읽기 전용으로만 열린다.
CLOSE_AT = (2, 5)
CLOSE_ASK_SEC = 60                          # 묻고 1분 뒤에는 저절로 닫는다

BASE = r"Z:\교통사업처_버스운영센터\상황실"
# Z: 로 연결돼 있지 않은 PC 도 있다. 그럴 때는 공유 폴더를 바로 찾아간다.
BASE_UNC = r"\\192.168.35.22\sctc17\교통사업처_버스운영센터\상황실"
KEYWORD = "입출차 운영관리"
# 했다/못 했다를 놓아 두는 자리 (사무실 PC 가 여기를 보고 폰에 전해 준다).
# 어느 PC 든 같은 곳을 보게, 경로는 그때그때 고른다 — base_dir() 참고.
RESULT_NAME = "받아쓰기"
SHEET = "고정차고지_입력"
YARDS = {
    "new": {"data": "yard-data.js", "offset": 35},
    "old": {"data": "yard-old-data.js", "offset": 0},
}

HOME = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "차고지받아쓰기")
LOG_FILE = os.path.join(HOME, "받아쓰기.log")
LAST_FILE = os.path.join(HOME, "마지막요청.txt")
CLOSED_FILE = os.path.join(HOME, "닫은날.txt")       # 하루에 한 번만 닫게


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


def report(req, state, msg):
    """했다/못 했다를 Z: 에 쪽지로 놓는다. 사무실 PC 가 그것을 보고 폰에 전해 준다.

    올리는 길(GitHub)은 권한이 있어야 하지만, 사무실 PC 는 이미 그 권한을 들고
    돌고 있다. 두 PC 가 함께 보는 Z: 에 한 줄 놓아 두는 것이 가장 짧은 길이다.
    """
    os.makedirs(result_dir(), exist_ok=True)
    at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
    tmp = result_file() + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump({"id": req["id"], "what": req.get("what"), "state": state,
                   "msg": msg, "at": at.replace("+00:00", "Z")}, f, ensure_ascii=False)
    os.replace(tmp, result_file())        # 반만 쓰인 쪽지를 사무실 PC 가 읽지 않게
    log(f"📨 결과를 놓았습니다 — {state} · {msg}")


def quit_excel(excel, *objs):
    """우리가 띄운 엑셀을 확실히 내보낸다.

    Quit() 만으로는 안 나간다. 시트·통합문서를 붙잡고 있던 COM 참조가 하나라도
    살아 있으면 엑셀은 보이지 않는 채로 남아 그 파일을 쥐고 있고, 그러면 사람이
    열 때 "읽기 전용" 으로 뜬다. (실제로 그렇게 두 개가 남아 있었다.)

    그래서 ① 붙잡고 있던 것을 먼저 놓고 ② Quit 하고 ③ 그래도 안 나가면 그
    프로세스만 끊는다. 우리가 DispatchEx 로 따로 띄운 것이라 남의 문서가 아니다.
    """
    pid = None
    try:
        import win32process
        pid = win32process.GetWindowThreadProcessId(excel.Hwnd)[1]
    except Exception:
        pass

    del objs                       # ws, wb ... 먼저 놓는다
    gc.collect()
    try:
        excel.DisplayAlerts = False
    except Exception:
        pass
    try:
        excel.Quit()
    except Exception:
        pass
    del excel
    gc.collect()

    if not pid:
        return
    for _ in range(20):            # 제대로 나가는 데 1~2초쯤 걸린다
        if not _alive(pid):
            return
        time.sleep(0.1)
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return "EXCEL" in (r.stdout or "").upper()


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


def base_dir():
    """상황실 공유 폴더. Z: 로 연결돼 있으면 그쪽, 아니면 공유 폴더를 바로."""
    if os.path.isdir(BASE):
        return BASE
    return BASE_UNC


def result_dir():
    return os.path.join(base_dir(), RESULT_NAME)


def result_file():
    return os.path.join(result_dir(), "결과.json")


def alive_file():
    return os.path.join(result_dir(), "살아있음.json")


_told_alive = [0.0]


def tell_alive(every=60):
    """"나 여기 돌고 있다" 를 공유 폴더에 남긴다.

    꺼져 있어서 못 적은 것인지, 켜져 있는데 못 적은 것인지 사무실 PC 가 가려
    폰에 제대로 알려 줄 수 있어야 한다. 1분에 한 번이면 넉넉하다.
    """
    if time.time() - _told_alive[0] < every:
        return
    _told_alive[0] = time.time()
    try:
        os.makedirs(result_dir(), exist_ok=True)
        tmp = alive_file() + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump({"pc": os.environ.get("COMPUTERNAME", "?"),
                       "at": datetime.datetime.now(datetime.timezone.utc)
                       .isoformat(timespec="seconds").replace("+00:00", "Z")},
                      f, ensure_ascii=False)
        os.replace(tmp, alive_file())
    except Exception:
        pass          # 공유 폴더가 잠깐 끊겨도 하던 일은 계속한다


def find_excel(date):
    year = str(date.year)
    base = base_dir()
    root = next((os.path.join(base, d) for d in sorted(os.listdir(base))
                 if d.split()[-1:] == [year] and os.path.isdir(os.path.join(base, d))), None)
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

_MAP = {}


def unc(path):
    r"""Z:\... 를 \\서버\공유\... 로 바꾼다 (연결이 없으면 그대로).

    엑셀은 열어 둔 파일을 UNC 로 올려 두는데 우리 경로는 연결된 드라이브 문자라,
    그대로 견주면 같은 파일을 서로 다른 것으로 본다.
    """
    full = os.path.abspath(path)
    drive, rest = os.path.splitdrive(full)
    if len(drive) == 2 and drive.endswith(":"):
        if drive.upper() not in _MAP:
            try:
                import win32wnet
                _MAP[drive.upper()] = win32wnet.WNetGetConnection(drive.upper()) or ""
            except Exception:
                _MAP[drive.upper()] = ""
        remote = _MAP[drive.upper()]
        if remote:
            full = remote.rstrip("\\") + rest
    return os.path.normcase(full)


def running_workbook(path):
    """지금 열려 있는 그 통합문서를 찾는다. 없으면 None.

    엑셀은 열어 둔 파일을 **실행 중인 개체 표(ROT)** 에 전체 경로로 올려 둔다.
    거기서 찾으면 어느 엑셀 창에서 열었든 그 문서를 그대로 집을 수 있다 —
    이 프로그램이 있는 이유가 바로 "열어 둔 그 문서에 적는 것" 이다.
    """
    import pythoncom
    import win32com.client

    want = unc(path)
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
            if unc(name) != want:
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
            quit_excel(excel, wb)
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
            # 우리가 띄운 엑셀이다. 남겨 두면 보이지 않는 채로 이 파일을 쥐고 있어
            # 사람이 열 때 읽기 전용으로 뜬다 — 확실히 내보낸다.
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass
            quit_excel(excel, ws, wb)
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
    """엑셀에 적고, 했다/못 했다를 Z: 에 놓는다.

    [최종 인쇄] 도 적는 것은 똑같다. 종이로 뽑는 것은 프린터가 걸린 사무실 PC 몫이라,
    그 쪽지는 사무실 PC 가 인쇄까지 마친 뒤에 폰으로 전해 준다.
    """
    yard = req.get("yard", "new")
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
        try:
            report(req, "error", f"A 컴퓨터: {e}")
        except Exception as e2:
            log(f"⚠ 결과를 놓지 못했습니다 — {type(e2).__name__}: {e2}")
        return

    log(f"✅ {date:%m/%d} {'열려 있던 ' if was_open else ''}엑셀에 {n}대 적고 저장했습니다")
    try:
        report(req, "done", f"A 컴퓨터가 {'열어 둔 ' if was_open else ''}엑셀에 {n}대 적음")
    except Exception as e:
        log(f"⚠ 적기는 했는데 결과를 놓지 못했습니다 — {type(e).__name__}: {e}")


# ---- 2시 5분, 저장하고 닫기 -----------------------------------------------

def ops_date(now):
    """그 시각에 쓰고 있는 운영관리 엑셀의 날짜 (순찰한 근무일 + 1)"""
    day = now.date() - datetime.timedelta(days=1) if now.hour < 9 else now.date()
    return day + datetime.timedelta(days=1)


def closed_day():
    try:
        with io.open(CLOSED_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def due_to_close(now):
    """닫을 때가 되었는가. 늦게 켜도(2시 20분에 켜도) 그날 것은 한 번 닫는다."""
    if now.hour != CLOSE_AT[0] or now.minute < CLOSE_AT[1]:
        return False
    return closed_day() != now.date().isoformat()


def ask_close(name, secs=CLOSE_ASK_SEC):
    """[확인]/[취소] 를 묻는다. 1분 동안 아무도 누르지 않으면 닫는 것으로 본다.

    창을 띄우지 못하는 때에도 닫는다 — 2시 10분에 저쪽이 열려야 하는 쪽이 더 중하다.
    """
    text = (f"{name}\n\n"
            "잠시 뒤 출퇴근 관리 프로그램이 이 엑셀을 열어야 합니다.\n"
            "여기서 열어 두고 있으면 그쪽은 읽기 전용으로만 열립니다.\n\n"
            "[확인] 지금 저장하고 닫기\n"
            "[취소] 그냥 열어 두기\n\n"
            f"{secs}초 뒤에는 저절로 저장하고 닫습니다.")
    try:
        import ctypes
        box = ctypes.windll.user32.MessageBoxTimeoutW
        box.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                        ctypes.c_uint, ctypes.c_ushort, ctypes.c_uint]
        flags = 0x1 | 0x30 | 0x1000 | 0x10000 | 0x40000   # 확인/취소 · 경고음 · 맨 앞으로
        answer = box(None, text, f"{APP_NAME} — 저장하고 닫습니다", flags, 0, secs * 1000)
        return answer != 2                                 # 2 = 취소. 확인(1)·시간지남(32000)은 닫는다
    except Exception:
        return True


def close_ops(now=None, ask=ask_close):
    """열어 둔 운영관리 엑셀을 저장하고 닫는다. 통합문서만 닫고 엑셀은 두어,
    그 창에서 보던 다른 문서는 그대로 남는다."""
    now = now or datetime.datetime.now()
    mark = lambda: io.open(CLOSED_FILE, "w", encoding="utf-8").write(now.date().isoformat())
    try:
        path = find_excel(ops_date(now))
    except FileNotFoundError as e:
        log(f"⏭ 닫을 엑셀을 찾지 못했습니다 — {e}")
        mark()
        return False

    import pythoncom
    pythoncom.CoInitialize()
    wb = running_workbook(path)
    if wb is None:
        mark()
        return False                       # 열려 있지 않다 — 할 일이 없다

    if not ask(os.path.basename(path)):
        log("⏭ 닫지 말라고 하셔서 그대로 둡니다")
        mark()
        return False
    try:
        if not wb.ReadOnly:
            wb.Save()
        wb.Close(SaveChanges=False)        # 방금 저장했다
        log(f"🔒 {os.path.basename(path)} 저장하고 닫았습니다")
        mark()
        return True
    except Exception as e:
        log(f"⚠ 닫지 못했습니다 — {type(e).__name__}: {e}")
        return False


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
            tell_alive()
            if due_to_close(datetime.datetime.now()):
                close_ops()
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
    try:
        os.makedirs(result_dir(), exist_ok=True)
        probe = os.path.join(result_dir(), "점검.tmp")
        with io.open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        log(f"점검 · 결과를 놓을 자리 정상 ({result_dir()})")
    except Exception as e:
        bad += 1
        log(f"점검 · 결과를 놓을 수 없다 — {type(e).__name__}: {e}")
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
