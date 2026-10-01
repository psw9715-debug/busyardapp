# -*- coding: utf-8 -*-
"""묶어 놓은 설치 파일을 "설치프로그램" 폴더로 옮겨 둔다.

build.ps1 이 마지막에 이것을 부른다. 파워셸 5.1 은 .ps1 을 ANSI 로 읽어 한글
경로가 깨지므로, 한글 폴더 이름은 파이썬 쪽에서 다룬다.
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "설치프로그램")


def main():
    os.makedirs(OUT, exist_ok=True)
    dist = os.path.join(HERE, "dist")
    setups = [f for f in os.listdir(dist) if "Setup" in f and f.endswith(".exe")]
    for name in setups + ["../읽어보기.txt"]:
        src = os.path.join(dist, name)
        shutil.copy2(src, os.path.join(OUT, os.path.basename(name)))
        print(f"놓았습니다: {os.path.join(OUT, os.path.basename(name))}")


if __name__ == "__main__":
    main()
