# -*- coding: utf-8 -*-
"""엑셀 셀 색을 실제 RGB로 풀어낸다.

엑셀은 색을 "테마 색 + 밝기 보정(tint)" 으로 저장하는 경우가 많아서,
그대로는 화면에 칠할 수 없다. 테마 팔레트를 읽어 tint 를 적용해 준다.
"""
import colorsys
import re
import zipfile

# xlsx 의 theme 속성이 가리키는 순서 (lt1/dk1 이 뒤바뀌어 있는 것에 주의)
THEME_ORDER = ['lt1', 'dk1', 'lt2', 'dk2',
               'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6',
               'hlink', 'folHlink']


def load_theme(xlsx_path):
    """테마 팔레트를 {이름: 'RRGGBB'} 로 읽는다."""
    with zipfile.ZipFile(xlsx_path) as z:
        name = next((n for n in z.namelist() if n.endswith('theme1.xml')), None)
        if not name:
            return {}
        xml = z.read(name).decode('utf-8')

    scheme = re.search(r'<a:clrScheme.*?</a:clrScheme>', xml, re.S)
    if not scheme:
        return {}

    out = {}
    for tag, _kind, attrs in re.findall(
            r'<a:(\w+)>\s*<a:(srgbClr|sysClr)([^/>]*)/>', scheme.group(0)):
        m = re.search(r'(?:lastClr|val)="([0-9A-Fa-f]{6})"', attrs)
        if m:
            out[tag] = m.group(1).upper()
    return out


def apply_tint(rgb_hex, tint):
    """ECMA-376 의 tint 규칙대로 밝기를 조정한다."""
    if not tint:
        return rgb_hex
    r, g, b = (int(rgb_hex[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = l * (1 + tint) if tint < 0 else l * (1 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s)
    return '{:02X}{:02X}{:02X}'.format(round(r * 255), round(g * 255), round(b * 255))


def cell_bg(cell, theme):
    """셀 배경색을 '#RRGGBB' 로. 칠이 없거나 흰색이면 None."""
    fill = cell.fill
    if fill is None or fill.patternType is None:
        return None
    fg = fill.fgColor
    if fg is None:
        return None

    if fg.type == 'rgb' and fg.rgb and isinstance(fg.rgb, str):
        hexv = fg.rgb[-6:].upper()
    elif fg.type == 'theme':
        idx = fg.theme
        if idx is None or idx >= len(THEME_ORDER):
            return None
        base = theme.get(THEME_ORDER[idx])
        if not base:
            return None
        hexv = apply_tint(base, fg.tint or 0)
    else:
        return None

    return None if hexv in ('FFFFFF', '000000') and fg.type == 'theme' and not fg.tint else '#' + hexv


# 테두리 굵기를 숫자로 (0 없음 / 1 가는선 / 2 보통 / 3 굵게)
WEIGHT = {None: 0, 'hair': 1, 'dotted': 1, 'dashed': 1,
          'thin': 2, 'medium': 3, 'thick': 3, 'double': 3}


def border_weights(ws, min_row, min_col, max_row, max_col):
    """병합 범위의 바깥쪽 테두리 굵기를 [위, 오른쪽, 아래, 왼쪽] 으로."""
    tl = ws.cell(min_row, min_col).border
    br = ws.cell(max_row, max_col).border
    tr = ws.cell(min_row, max_col).border
    bl = ws.cell(max_row, min_col).border
    return [
        WEIGHT.get(tl.top.style, 2),
        WEIGHT.get(tr.right.style, 2),
        WEIGHT.get(bl.bottom.style, 2),
        WEIGHT.get(tl.left.style, 2),
    ]
