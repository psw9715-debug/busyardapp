# -*- coding: utf-8 -*-
"""배포 버전 도장을 찍는다.

사파리와 서비스 워커가 옛 파일을 붙잡고 있을 때 어느 버전이 돌고 있는지
눈으로 확인할 수 있어야 해서, 커밋 시각을 앱 안에 넣어 둔다.
서비스 워커 캐시 이름도 같이 갱신해 새 배포가 확실히 내려가게 한다.

    python tools/stamp_build.py
"""
import io
import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def main():
    # 커밋 해시는 이 파일을 만든 시점 기준이라 헷갈린다. 배포 시각만 남긴다.
    build = datetime.now(KST).strftime('%Y-%m-%d %H:%M')

    with io.open('src/build.js', 'w', encoding='utf-8') as f:
        f.write('// 자동 생성 파일 — `python tools/stamp_build.py` 로 갱신.\n')
        f.write(f"export const BUILD = '{build}';\n")

    # 서비스 워커 캐시 이름을 바꿔 옛 캐시를 확실히 버리게 한다
    sw = io.open('sw.js', encoding='utf-8').read()
    cache_id = datetime.now(KST).strftime('%Y%m%d%H%M')
    sw = re.sub(r"const CACHE = '[^']*';", f"const CACHE = 'busyard-{cache_id}';", sw, count=1)
    io.open('sw.js', 'w', encoding='utf-8').write(sw)

    print(f'build: {build}')
    print(f'cache: busyard-{cache_id}')


if __name__ == '__main__':
    main()
