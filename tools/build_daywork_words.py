# -*- coding: utf-8 -*-
"""PC 일일일지 프로그램의 단어장을 폰 앱이 쓸 모듈로 뽑는다.

    python tools/build_daywork_words.py

버튼 순서를 PC 프로그램의 get_display_order() 와 같은 규칙으로 맞춘다 —
사용횟수 내림차순, 같으면 words.json 에 적힌 차례. 두 곳의 배열이 달라지면
손이 기억하는 자리가 어긋나서 밤에 헷갈린다.

PC 에서 단어를 고치거나 많이 쓴 순서가 바뀌면 이걸 다시 돌리고 배포한다.
"""
import io
import json
import os

PC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "daywork")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "daywork", "src", "words.js")

HEAD = """// 특이사항 어휘 — PC 프로그램의 words.json + word_counts.json 에서 뽑았다.
//
// 18일치 일지에 실제로 적힌 특이사항은 스무 가지가 채 안 된다. 그래서 말로
// 부르는 것 말고 버튼으로 집는 길도 함께 둔다 — 손이 비면 버튼이 더 빠르고 정확하다.
// 순서는 PC 프로그램의 버튼 배열과 같은 규칙(사용횟수 내림차순, 동점이면 기존 순서)이다.
//
// `python tools/build_daywork_words.py` 로 다시 뽑는다.
export const WORDS = [
"""


def main():
    words_path = os.path.join(PC_DIR, "words.json")
    counts_path = os.path.join(PC_DIR, "word_counts.json")
    if not os.path.exists(words_path):
        raise SystemExit(f"PC 단어장을 찾지 못했다: {words_path}")

    words = json.load(io.open(words_path, encoding="utf-8"))
    counts = {}
    if os.path.exists(counts_path):
        counts = json.load(io.open(counts_path, encoding="utf-8"))

    order = sorted(range(len(words)), key=lambda i: (-counts.get(words[i], 0), i))

    body = "".join(
        "  { text: %s, count: %d },\n" % (json.dumps(words[i], ensure_ascii=False), counts.get(words[i], 0))
        for i in order
    )
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(HEAD + body + "];\n")

    print(f"{OUT} 갱신: {len(words)}개")
    print("앞 5개:", [words[i] for i in order[:5]])


if __name__ == "__main__":
    main()
