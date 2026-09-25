# -*- coding: utf-8 -*-
"""순찰 판을 그날 "입출차 운영관리" 엑셀의 6차고지 칸에 그대로 써 넣는다.

지금까지는 인쇄물을 옆자리 직원에게 건네주고 손으로 옮겨 적었다. 폰이 올린 판이
이미 PC 에 오므로(tools/inbox.py), 그 판을 원본 엑셀에 직접 넣는다.

넣는 곳: `고정차고지_입력` 시트의 **38~97행**. 이 블록이 6차고지다
(1~21행 2차고지, 23~34행 1차고지 — `차량및키확인` 시트의 수식이 이 범위로 차고지를 가른다).
한 자리가 세 줄(차량번호 / 이름 / 시각)인 격자가 인쇄 양식과 똑같고 **행만 35줄** 밀려 있다.
이름과 시각은 수식이라 **차량번호만** 넣으면 저절로 채워진다.

파일 찾기는 "출퇴근 관리" 프로그램(main.py find_todays_excel_path)과 같은 방식이다.
날짜는 **근무일 + 1** — 밤에 세워 둔 차는 다음 날 아침 나가는 차라서다.

쓰기는 엑셀 자체(COM)로 한다. 파이썬으로 직접 쓰면 그림과 프린터 설정이 날아간다.
다른 사람이 열어 두었으면 읽기 전용으로 열리므로, 건드리지 않고 누가 열었는지 알린다.

    python tools/ops_fill.py            # 오늘 판을 내일 파일에 넣는다
    python tools/ops_fill.py 2026-09-26 # 넣을 엑셀 날짜를 직접
"""
import datetime
import json
import os
import re
import shutil
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = r"Z:\교통사업처_버스운영센터\상황실"
KEYWORD = "입출차 운영관리"          # 그날 폴더에 있는 다른 엑셀과 가르는 말
SHEET = "고정차고지_입력"
# 차고지마다 이 시트 안의 자리가 다르다.
#   신차고지(6차고지)   : 38~97행 — 인쇄 양식 3행이 38행이라 35줄 아래
#   구차고지(1·2차고지) : 1~34행 — 인쇄 양식과 행이 그대로 겹친다
YARDS = {
    "new": {"data": "yard-data.js", "first": 38, "last": 97, "offset": 35},
    "old": {"data": "yard-old-data.js", "first": 1, "last": 34, "offset": 0},
}
FIRST_ROW, LAST_ROW = YARDS["new"]["first"], YARDS["new"]["last"]
ROW_OFFSET = YARDS["new"]["offset"]

# 한 자리는 세 줄이다 — 1행 차량번호(수식 없음), 2행 이름, 3행 출근시각.
# 2·3행은 차량번호를 보고 끌어오는 수식이라 절대 건드리지 않는다. 우리는 1행만 쓴다.
#
# 넣을 때마다 원본 옆에 보기용 복사본을 새로 뜬다 — 이름은 차고지입력_MMDD.xlsx.
# 원본이 열려 있어 손을 못 댈 때도 이 복사본은 늘 남는다.
COPY_NAME = "차고지입력_{:%m%d}.xlsx"


def target_date(now=None):
    """넣을 엑셀의 날짜 = 근무일 + 1 (근무일은 오전 9시에 넘어간다)"""
    now = now or datetime.datetime.now()
    day = now.date() - datetime.timedelta(days=1) if now.hour < 9 else now.date()
    return day + datetime.timedelta(days=1)


def find_excel(date, base=BASE):
    """연도 'NN YYYY' / 월 '00 YYYYMM' / 일 'MMDD*' 폴더를 따라가 그날 파일을 찾는다"""
    year = str(date.year)
    root = next((os.path.join(base, d) for d in sorted(os.listdir(base))
                 if d.split()[-1:] == [year] and os.path.isdir(os.path.join(base, d))), None)
    if not root:
        raise FileNotFoundError(f"{year} 연도 폴더 없음 — {base}")

    month = os.path.join(root, f"00 {date:%Y%m}")
    if not os.path.isdir(month):
        raise FileNotFoundError(f"{date:%Y%m} 월 폴더 없음 — {month}")

    day = next((os.path.join(month, d) for d in sorted(os.listdir(month))
                if d.startswith(f"{date:%m%d}") and os.path.isdir(os.path.join(month, d))), None)
    if not day:
        raise FileNotFoundError(f"{date:%m%d} 날짜 폴더 없음 — {month}")

    hits = [f for f in sorted(os.listdir(day))
            if KEYWORD in f and f.endswith(('.xlsx', '.xlsm', '.xls')) and not f.startswith('~$')]
    if not hits:
        raise FileNotFoundError(f"{KEYWORD} 파일 없음 — {day}")
    # '복사본 …' 같은 것보다 그날 날짜로 시작하는 파일을 먼저 본다
    hits.sort(key=lambda f: (not f.startswith(f"{date:%m%d}"), f))
    return os.path.join(day, hits[0])


def make_copy(orig, date):
    """원본 옆에 차고지입력_MMDD.xlsx 를 새로 뜬다.

    시트를 덜어내지 않고 통째로 복사한다 — 이름·시각 수식이 `출근순서`, `일요일DATA`
    시트를 보고 있어서, 차고지 시트만 떼면 이름과 시각이 #REF! 로 깨진다.
    대신 열었을 때 차고지 시트가 바로 보이도록 맨 뒤로 옮겨 놓는다(fill 에서).
    """
    dst = os.path.join(os.path.dirname(orig), COPY_NAME.format(date))
    shutil.copy2(orig, dst)
    return dst


def block_cells(yard="new"):
    """순회 자리 이름 -> 이 시트의 (행, 열). 인쇄 양식 칸을 차고지만큼 내린 것이다."""
    cfg = YARDS.get(yard, YARDS["new"])
    with open(os.path.join(ROOT, "src", cfg["data"]), encoding="utf-8") as f:
        text = f.read()
    data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    cells = {}
    for c in data["cells"]:
        if c["kind"] != "spot":
            continue
        m = re.match(r"([A-Z]+)(\d+)", c["xl"])
        col = 0
        for ch in m.group(1):
            col = col * 26 + (ord(ch) - 64)
        cells[c["label"]] = (int(m.group(2)) + cfg["offset"], col)
    return cells


def _runs(want):
    """{(행, 열): 값} 을 가로로 이어진 토막으로 묶는다. (행, 첫 열, [값...]) 을 준다."""
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


def opened_by(path):
    """열어 둔 사람의 이름. 엑셀이 옆에 남기는 '~$' 파일에 적혀 있다.

    그 파일은 엑셀이 붙들고 있어 그냥은 못 연다. 공유 모드로 열어 읽는다.
    이름을 못 읽으면 "다른 사람" 이라고만 한다 — 닫아 달라고 말하는 데는 그걸로 족하다.
    """
    lock = os.path.join(os.path.dirname(path), "~$" + os.path.basename(path))
    if not os.path.exists(lock):
        return None
    try:
        import win32con
        import win32file
        h = win32file.CreateFile(
            lock, win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None, win32con.OPEN_EXISTING, 0, None)
        try:
            raw = win32file.ReadFile(h, 128)[1]
        finally:
            win32file.CloseHandle(h)
        return _name_in(raw) or "다른 사람"
    except Exception:
        return "다른 사람"


def _name_in(raw):
    """잠금 파일에 적힌 이름.

    첫 바이트가 글자 수이고 그다음이 이름이다 (04 'user'). 엑셀 판에 따라 두 바이트
    문자로 적히기도 해서 둘 다 본다. 글자가 깨지면 이름이 아니라고 보고 넘긴다.
    """
    if not raw:
        return None
    n = raw[0]
    if not 1 <= n <= 20:
        return None
    for text in (raw[1:1 + n].decode("cp949", "ignore"),
                 raw[1:1 + n * 2].decode("utf-16-le", "ignore")):
        name = "".join(ch for ch in text if ch.isprintable()).strip()
        # 글자 수가 앞에 적힌 수와 맞아야 제대로 읽은 것이다. 아니면 "다른 사람" 으로 둔다 —
        # 닫아 달라고 말하는 데에 이름이 꼭 필요한 것은 아니다.
        if len(name) == n and any(ch.isalnum() for ch in name):
            return name
    return None

def fill(path, board, cells=None, show_sheet=False):
    """그 차고지 칸을 싹 비우고 판대로 써 넣는다. (넣은 대수, 빈 칸 수) 를 돌려준다.

    승용차는 넣지 않는다 — 2차 순찰 전에 빠질 차라 운영관리에 남길 것이 아니다.
    """
    cells = cells or block_cells(board.get("yard", "new"))
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()

    # DispatchEx — 사장님이 열어 둔 엑셀에 붙지 않고 우리 것만 따로 띄운다.
    # 붙으면 우리가 끝내며 Quit 할 때 열어 두신 문서까지 닫아 버린다.
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.DisplayAlerts = False
    try:
        excel.Visible = False
        excel.ScreenUpdating = False
    except Exception:
        pass                          # 갓 띄운 엑셀이 아직 못 받는 때가 있다 — 그냥 진행
    wb = excel.Workbooks.Open(path)
    try:
        # 이 통합문서는 VLOOKUP 이 많아, 한 칸 쓸 때마다 다시 계산하면 몇 분씩 걸린다.
        # 다 쓰고 나서 한 번만 계산한다 (통합문서를 연 뒤에야 바꿀 수 있는 설정이다).
        excel.Calculation = -4135      # xlCalculationManual
        if wb.ReadOnly:
            who = opened_by(path) or "누군가"
            raise PermissionError(f"{who} 님이 엑셀을 열어 두어 쓸 수 없습니다 — 닫은 뒤 다시 눌러 주세요")
        ws = wb.Worksheets(SHEET)

        # 1회차를 돌기 전까지 이 블록은 어차피 비어 있다. 통째로 지우고 판대로 새로 쓴다.
        want = {}                             # (행, 열) -> 넣을 번호 (없으면 None = 빈 칸)
        for rc in cells.values():
            want[rc] = None
        written = 0
        for spot, e in board["entries"].items():
            rc = cells.get(_label_of(int(spot), board.get("yard", "new")))
            if not rc or e.get("status") != "filled" or not e.get("plate"):
                continue                      # 공차와 승용차는 빈 칸으로 둔다
            want[rc] = int(e["plate"])
            written += 1

        # 한 칸씩 건드리면 엑셀이 칸마다 수식 관계를 다시 훑어 몇 분이 걸린다.
        # 가로로 이어진 칸은 한 번에 넘긴다 (자리 칸은 병합된 적이 없어 안전하다).
        for row, col, run in _runs(want):
            ws.Range(ws.Cells(row, col), ws.Cells(row, col + len(run) - 1)).Value = (tuple(run),)
        if show_sheet:
            # 열었을 때 차고지 칸이 바로 보이게 이 시트를 펴 둔 채로 저장한다.
            # (시트를 '옮기면' 엑셀이 다른 통합문서로 떼어 내 버린다 — 옮기지 않는다.)
            try:
                excel.Visible = True      # 우리 전용 엑셀이라 남의 문서에 영향이 없다
                ws.Activate()
            except Exception:
                pass
        excel.Calculation = -4105  # xlCalculationAutomatic — 저장 전에 수식을 채운다
        wb.Save()
    finally:
        wb.Close(SaveChanges=False)
        try:
            excel.ScreenUpdating = True
            excel.Visible = False
        except Exception:
            pass
        excel.Quit()
    return written, len(cells) - written


_LABELS = {}


def _labels(yard="new"):
    """순회 번호 -> 자리 이름"""
    if yard not in _LABELS:
        cfg = YARDS.get(yard, YARDS["new"])
        with open(os.path.join(ROOT, "src", cfg["data"]), encoding="utf-8") as f:
            text = f.read()
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        _LABELS[yard] = {c["spot"]: c["label"] for c in data["cells"] if c["kind"] == "spot"}
    return _LABELS[yard]


def _label_of(spot, yard="new"):
    return _labels(yard).get(spot)


def run(board_date=None, date=None, log=print, yard="new"):
    """폰이 올린 판을 엑셀에 넣는다. 한 줄 요약을 돌려준다.

    board_date 는 순찰한 근무일, date 는 넣을 엑셀의 날짜(기본 근무일+1)다.
    PC 시계가 아니라 폰이 보낸 판의 날짜를 따라간다 — 자정을 넘겨 눌러도 어긋나지 않는다.
    """
    import inbox
    board_date = board_date or inbox.work_date()
    if date is None:
        date = datetime.date.fromisoformat(board_date) + datetime.timedelta(days=1)
    board = inbox.fetch(board_date, yard)
    if board is None:
        raise FileNotFoundError(f"폰이 올린 {board_date} 판이 없습니다 — 폰 [진단] → PC 전송 확인")

    orig = find_excel(date)
    log(f"📋 [엑셀] {os.path.basename(orig)}")

    dst = make_copy(orig, date)
    written, _ = fill(dst, board, show_sheet=True)
    log(f"📄 [엑셀] {os.path.basename(dst)} — {written}대")

    return f"{date:%m/%d} {written}대 — {os.path.basename(dst)} / " + fill_original(board, orig, log=log)


def fill_original(board, orig=None, date=None, log=print):
    """원본에도 넣는다. 누가 열어 두었으면 건드리지 않고 그 사실만 알린다."""
    orig = orig or find_excel(date or target_date())
    who = opened_by(orig)
    if who:
        log(f"🔒 [엑셀] 원본은 {who} 님이 열어 두어 건너뜀")
        return f"원본은 {who} 님이 열어 두어 그대로 둠 (닫은 뒤 트레이에서 다시)"
    try:
        written, _ = fill(orig, board)
    except PermissionError as e:
        log(f"🔒 [엑셀] {e}")
        return str(e)
    log(f"✅ [엑셀] 원본에 {written}대 넣음")
    return f"원본에 {written}대 넣음"


def read_board(yard="old", date=None, log=print):
    """원본 엑셀에 지금 적혀 있는 자리들을 읽는다 (2차 순찰의 밑바탕).

    읽기만 하므로 다른 사람이 열어 두어도 된다. 1행의 차량번호만 가져온다 —
    2·3행은 그 번호를 보고 끌어오는 수식이라 값이 아니다.
    """
    date = date or target_date()
    path = find_excel(date)
    log(f"📥 [엑셀] {os.path.basename(path)} 에서 읽는 중...")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb[SHEET]
        cells = block_cells(yard)
        spot_of = {label: spot for spot, label in _labels(yard).items()}
        entries = {}
        for label, (row, col) in cells.items():
            v = ws.cell(row, col).value
            if v is None:
                continue
            text = str(v).strip()
            if text.isdigit() and len(text) == 4:
                entries[str(spot_of[label])] = {"plate": text, "status": "filled", "round": 1}
    finally:
        wb.close()
    log(f"📥 [엑셀] {len(entries)}대 읽음")
    return entries


def run_original(board_date=None, date=None, log=print, yard="new"):
    """원본에만 넣는다 (트레이에서 나중에 다시 누를 때)."""
    import inbox
    board_date = board_date or inbox.work_date()
    if date is None:
        date = datetime.date.fromisoformat(board_date) + datetime.timedelta(days=1)
    board = inbox.fetch(board_date, yard)
    if board is None:
        raise FileNotFoundError(f"폰이 올린 {board_date} 판이 없습니다")
    return f"{date:%m/%d} " + fill_original(board, date=date, log=log)


def main(argv):
    date = datetime.date.fromisoformat(argv[0]) if argv else None
    try:
        print(run(date=date))
    except Exception as e:
        print(f"실패: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main([a for a in sys.argv[1:] if not a.startswith("--")]))
