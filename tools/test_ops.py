# -*- coding: utf-8 -*-
"""tools/ops_fill.py 검사 — 그날 운영관리 엑셀을 찾고, 6차고지 칸을 제대로 짚는가

    python -m unittest tools/test_ops.py
"""
import datetime
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ops_fill  # noqa: E402


class TargetDate(unittest.TestCase):
    """밤에 도는 순찰은 다음 날 아침 나가는 차를 적는 것이라 하루 뒤 파일에 넣는다"""

    def test_night_goes_to_next_day(self):
        self.assertEqual(ops_fill.target_date(datetime.datetime(2026, 9, 25, 23, 30)),
                         datetime.date(2026, 9, 26))

    def test_after_midnight_still_the_same_shift(self):
        # 새벽 0시 40분도 25일 근무 — 그래도 26일 파일
        self.assertEqual(ops_fill.target_date(datetime.datetime(2026, 9, 26, 0, 40)),
                         datetime.date(2026, 9, 26))

    def test_after_nine_is_a_new_shift(self):
        self.assertEqual(ops_fill.target_date(datetime.datetime(2026, 9, 26, 9, 0)),
                         datetime.date(2026, 9, 27))


class FindExcel(unittest.TestCase):
    """출퇴근 관리 프로그램과 같은 방식으로 찾는다 (연도 'NN YYYY' / 월 '00 YYYYMM' / 일 'MMDD*')"""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.day = os.path.join(self.base, '08 2026', '00 202609', '0926(휴일)')
        os.makedirs(self.day)

    def touch(self, name, where=None):
        p = os.path.join(where or self.day, name)
        open(p, 'w').close()
        return p

    def test_finds_holiday_named_file(self):
        want = self.touch('0926(휴일) [임시]입출차 운영관리 (일휴일) v.260425.xlsx')
        self.assertEqual(ops_fill.find_excel(datetime.date(2026, 9, 26), self.base), want)

    def test_ignores_other_workbooks_and_lock_files(self):
        self.touch('260924_26년 9월 일 배차표.xlsx')
        self.touch('~$0926 입출차 운영관리.xlsx')
        want = self.touch('0926 [임시]입출차 운영관리 (토).xlsx')
        self.assertEqual(ops_fill.find_excel(datetime.date(2026, 9, 26), self.base), want)

    def test_prefers_the_day_file_over_a_copy(self):
        self.touch('복사본 0926(임시)입출차 운영관리.xlsx')
        want = self.touch('0926(휴일) [임시]입출차 운영관리.xlsx')
        self.assertEqual(ops_fill.find_excel(datetime.date(2026, 9, 26), self.base), want)

    def test_missing_day_folder(self):
        with self.assertRaises(FileNotFoundError):
            ops_fill.find_excel(datetime.date(2026, 9, 27), self.base)


class BlockCells(unittest.TestCase):
    """6차고지 블록(38~97행)은 인쇄 양식과 같은 격자이고 행만 35줄 밀려 있다"""

    def setUp(self):
        self.cells = ops_fill.block_cells()

    def test_covers_every_spot(self):
        self.assertEqual(len(self.cells), 196)

    def test_first_spot(self):
        self.assertEqual(self.cells['B5-1'], (38, 14))      # 인쇄 양식 N3 → N38

    def test_all_inside_the_block(self):
        rows = [r for r, _ in self.cells.values()]
        cols = [c for _, c in self.cells.values()]
        self.assertGreaterEqual(min(rows), ops_fill.FIRST_ROW)
        self.assertLessEqual(max(rows), ops_fill.LAST_ROW)
        self.assertTrue(all((r - ops_fill.FIRST_ROW) % 3 == 0 for r in rows), '한 자리는 세 줄짜리')
        self.assertGreaterEqual(min(cols), 1)
        self.assertLessEqual(max(cols), 15)

    def test_no_two_spots_share_a_cell(self):
        self.assertEqual(len(set(self.cells.values())), len(self.cells))


class OldYardCells(unittest.TestCase):
    """구차고지는 같은 시트 1~34행이고, 인쇄 양식과 행이 그대로 겹친다(밀림 0줄)"""

    def setUp(self):
        self.cells = ops_fill.block_cells("old")

    def test_covers_every_spot(self):
        self.assertEqual(len(self.cells), 90)      # 걷는 순서 89 + 예비 1

    def test_inside_the_block(self):
        rows = [r for r, _ in self.cells.values()]
        self.assertGreaterEqual(min(rows), 1)
        self.assertLessEqual(max(rows), 34)

    def test_no_offset(self):
        # 인쇄 양식(구차고지-순서)의 칸 주소가 그대로 쓰인다
        import json
        with io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "src", "yard-old-data.js"), encoding="utf-8") as f:
            text = f.read()
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        for c in data["cells"]:
            if c["kind"] != "spot":
                continue
            row = int("".join(ch for ch in c["xl"] if ch.isdigit()))
            self.assertEqual(self.cells[c["label"]][0], row, c["label"])

    def test_two_yards_do_not_overlap(self):
        new_rows = {r for r, _ in ops_fill.block_cells("new").values()}
        old_rows = {r for r, _ in self.cells.values()}
        self.assertFalse(new_rows & old_rows, "신차고지와 구차고지 칸이 겹치면 안 된다")


if __name__ == '__main__':
    unittest.main()
