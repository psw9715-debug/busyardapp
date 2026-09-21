# -*- coding: utf-8 -*-
"""폰이 GitHub inbox 가지에 올린 그날 판을 받아 저장하고 인쇄한다.

폰과 PC 는 서로 직접 닿을 수 없다 (폰은 LTE, PC 는 사내 유선). 폰은 입력이
멎으면 판을 GitHub 에 올려 두고, PC 는 인쇄할 때 그것을 받아간다.
받는 쪽은 공개 저장소 읽기라 토큰이 필요 없다.

인쇄 양식은 원본 엑셀(`차고지 프린트.xlsx` 의 `신차고지` 시트)이고 값만 채운다.
2회차 기록이 있으면 1회차 번호는 흐리게, 2회차 번호는 진하게 — 앱 인쇄와 같다.

    python tools/inbox.py               # 오늘 판을 받아 저장하고 기본 프린터로 인쇄
    python tools/inbox.py --save        # 인쇄하지 않고 저장만
    python tools/inbox.py 2026-09-20    # 그 날짜 판

저장: 기록/<날짜> 신차고지.json (받은 그대로), 기록/<날짜> 신차고지.xlsx (인쇄본)
종료 코드: 0 성공, 2 그날 올라온 판 없음, 1 그 밖의 오류
"""
import copy
import datetime
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "reference", "차고지 프린트.xlsx")
SHEET = "신차고지"
OUT_DIR = os.path.join(ROOT, "기록")
API = "https://api.github.com/repos/psw9715-debug/busyardapp/contents/inbox/{date}.json?ref=inbox"
GREY = "FF8F8F8F"


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


def fetch(date):
    """그날 판. 아직 안 올라왔으면 None"""
    req = urllib.request.Request(API.format(date=date), headers={
        "Accept": "application/vnd.github.raw+json",
        "User-Agent": "busyard-inbox",
    })
    # 사내망이 HTTPS 를 자체 인증서로 다시 서명한다. 윈도우는 믿지만 파이썬 3.13 의
    # 엄격 검사가 그 인증서 형식을 거부하므로, 인증서 확인은 그대로 두고 엄격 검사만 뺀다.
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


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


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    date = args[0] if args else work_date()

    board = fetch(date)
    if board is None:
        print(f"{date} 순회판이 아직 올라오지 않았다 — 폰 [진단]에서 PC 전송 상태를 확인")
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(OUT_DIR, f"{date} 신차고지")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=1)
    n = fill(board, base + ".xlsx")
    print(f"{date} 순회판 받음 ({board.get('updatedAt', '?')} 폰 저장분) — {n}칸 채움")

    if "--save" in argv:
        return 0
    from print_board import print_file
    print(f"  {print_file(base + '.xlsx')} 로 보냈다")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
