# -*- coding: utf-8 -*-
"""홈화면 아이콘 PNG 생성 (외부 라이브러리 없이 zlib만 사용).

어두운 배경에 호박색 주차 구획 3칸 — 배치도를 그대로 축약한 모양.
"""
import struct
import zlib
import os

BG = (14, 14, 10)
AMBER = (230, 162, 60)
DIM = (47, 45, 30)


def make_png(size, path):
    px = [[BG for _ in range(size)] for _ in range(size)]

    m = size // 8            # 여백
    gap = max(1, size // 40)
    cell_w = (size - m * 2 - gap * 2) // 3
    cell_h = size - m * 2

    # 3칸 중 가운데만 채워진(=현재 자리) 모양
    for i in range(3):
        x0 = m + i * (cell_w + gap)
        color = AMBER if i == 1 else DIM
        border = max(1, size // 32)
        for y in range(m, m + cell_h):
            for x in range(x0, x0 + cell_w):
                edge = (
                    y < m + border or y >= m + cell_h - border
                    or x < x0 + border or x >= x0 + cell_w - border
                )
                if i == 1:
                    px[y][x] = color
                elif edge:
                    px[y][x] = color

    raw = b''.join(b'\x00' + b''.join(bytes(p) for p in row) for row in px)

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b'')
    )
    with open(path, 'wb') as f:
        f.write(png)
    print(f'{path}  {size}x{size}  {len(png)}B')


if __name__ == '__main__':
    os.makedirs('icons', exist_ok=True)
    for s in (180, 192, 512):
        make_png(s, f'icons/icon-{s}.png')
