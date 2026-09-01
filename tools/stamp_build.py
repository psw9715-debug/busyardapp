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


MODULES = ['app.js', 'plate.js', 'voice.js', 'store.js', 'yard-data.js', 'build.js']
ASSETS = MODULES + ['app.css']


def stamp_module_urls(tag):
    """모듈·스타일 주소에 버전을 붙인다.

    ES 모듈과 CSS 는 페이지를 새로고침해도 브라우저가 캐시해 둔 것을 그대로 쓴다.
    파일은 새로 올라갔는데 실행되는 코드는 옛것인 상황이 이래서 생긴다.
    주소가 바뀌면 다른 파일로 보므로 반드시 새로 받아간다.
    """
    paths = ['index.html'] + [f'src/{m}' for m in MODULES]
    changed = 0

    for path in paths:
        try:
            text = io.open(path, encoding='utf-8').read()
        except FileNotFoundError:
            continue
        original = text
        for asset in ASSETS:
            # src/app.js  또는  ./app.js  뒤의 기존 ?v=... 를 갈아끼운다
            text = re.sub(
                r'((?:\./|src/)%s)(\?v=\d+)?' % re.escape(asset),
                lambda m: m.group(1) + '?v=' + tag,
                text,
            )
        if text != original:
            io.open(path, 'w', encoding='utf-8').write(text)
            changed += 1

    print(f'모듈·스타일 주소 갱신: {changed}개 파일 (?v={tag})')


def main():
    # 커밋 해시는 이 파일을 만든 시점 기준이라 헷갈린다. 배포 시각만 남긴다.
    build = datetime.now(KST).strftime('%Y-%m-%d %H:%M')

    with io.open('src/build.js', 'w', encoding='utf-8') as f:
        f.write('// 자동 생성 파일 — `python tools/stamp_build.py` 로 갱신.\n')
        f.write(f"export const BUILD = '{build}';\n")

    # 앱이 실행할 때마다 캐시를 건너뛰고 받아와 지금 것과 비교하는 파일
    with io.open('version.json', 'w', encoding='utf-8') as f:
        f.write('{"build": "%s"}\n' % build)

    stamp_module_urls(datetime.now(KST).strftime('%Y%m%d%H%M'))

    # 서비스 워커 캐시 이름을 바꿔 옛 캐시를 확실히 버리게 한다
    sw = io.open('sw.js', encoding='utf-8').read()
    cache_id = datetime.now(KST).strftime('%Y%m%d%H%M')
    sw = re.sub(r"const CACHE = '[^']*';", f"const CACHE = 'busyard-{cache_id}';", sw, count=1)
    io.open('sw.js', 'w', encoding='utf-8').write(sw)

    print(f'build: {build}')
    print(f'cache: busyard-{cache_id}')


if __name__ == '__main__':
    main()
