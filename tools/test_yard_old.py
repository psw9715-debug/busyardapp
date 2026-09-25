# -*- coding: utf-8 -*-
"""구차고지 배치도(src/yard-old-data.js) 검사

    python -m unittest tools/test_yard_old.py
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def load():
    with open(os.path.join(ROOT, "src", "yard-old-data.js"), encoding="utf-8") as f:
        text = f.read()
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


# 사무실을 나와 도는 순서 (사용자가 불러 준 그대로)
ROUTE = [("1-3", 13), ("2-1", 9), ("2-2", 10), ("2-3", 9),
         ("조", 11), ("한노", 8), ("1-1", 15), ("1-2", 14)]


class Yard(unittest.TestCase):
    def setUp(self):
        self.yard = load()
        self.spots = sorted((c for c in self.yard["cells"] if c["kind"] == "spot"),
                            key=lambda c: c["spot"])

    def test_walking_order(self):
        want = [f"{zone}-{n}" for zone, last in ROUTE for n in range(1, last + 1)]
        got = [c["label"] for c in self.spots if not c.get("extra")]
        self.assertEqual(got, want)

    def test_counts(self):
        self.assertEqual(len([c for c in self.spots if not c.get("extra")]), 89)
        self.assertEqual(self.yard["totalSpots"], 90, "예비 칸 하나를 더해 90")

    def test_segments_follow_the_route(self):
        segs = [c["seg"] for c in self.spots if not c.get("extra")]
        self.assertEqual(segs, sorted(segs), "구간 번호는 걷는 순서대로 올라간다")
        self.assertEqual(len(set(segs)), len(ROUTE))

    def test_excel_cells_are_unique_and_in_the_sheet(self):
        xls = [c["xl"] for c in self.spots]
        self.assertEqual(len(set(xls)), len(xls))
        for xl in xls:
            m = re.match(r"^([A-O])(\d+)$", xl)
            self.assertTrue(m, xl)
            self.assertLessEqual(int(m.group(2)), 34, f"{xl} 은 구차고지 밖")

    def test_grid_is_the_sheet_shape(self):
        self.assertEqual(self.yard["cols"], 15)
        rows = [c["row"] for c in self.yard["cells"]]
        self.assertGreaterEqual(min(rows), 1)
        self.assertLessEqual(max(rows), self.yard["rows"])


if __name__ == "__main__":
    unittest.main()
