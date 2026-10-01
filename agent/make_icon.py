# -*- coding: utf-8 -*-
"""트레이·바로가기에 쓸 아이콘을 만든다 (tray.py 가 그리는 것과 같은 그림)."""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))


def image(size=256):
    k = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2 * k, 2 * k, 62 * k, 62 * k), 10 * k,
                        fill=(23, 23, 15, 255), outline=(230, 162, 60, 255), width=max(2, int(3 * k)))
    for x, y in ((14, 16), (36, 16), (14, 36), (36, 36)):
        d.rectangle((x * k, y * k, (x + 14) * k, (y + 12) * k), fill=(230, 162, 60, 255))
    return img


if __name__ == "__main__":
    out = os.path.join(HERE, "icon.ico")
    image(256).save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("아이콘:", out)
