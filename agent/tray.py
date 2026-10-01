# -*- coding: utf-8 -*-
"""트레이 아이콘과 기록 창. 평소에는 시계 옆에만 떠 있고, 눌러야 창이 열린다."""
import threading
import tkinter as tk

import pystray
from PIL import Image, ImageDraw


def _icon_image():
    """차고지 칸 모양 — 작게 그려도 알아볼 수 있게 네모 넷"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), 10, fill=(23, 23, 15, 255), outline=(230, 162, 60, 255), width=3)
    for x, y in ((14, 16), (36, 16), (14, 36), (36, 36)):
        d.rectangle((x, y, x + 14, y + 12), fill=(230, 162, 60, 255))
    return img


def run(app_name, lines, stop, check_now):
    root = tk.Tk()
    root.title(app_name)
    root.geometry("560x340")
    root.configure(bg="#14140f")
    root.withdraw()                      # 시작하자마자 트레이로 내려간다

    text = tk.Text(root, bg="#14140f", fg="#e8e2d2", insertbackground="#e8e2d2",
                   font=("Consolas", 10), borderwidth=0, highlightthickness=0)
    text.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh():
        at_end = text.yview()[1] > 0.99
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("end", "\n".join(lines[-200:]))
        text.configure(state="disabled")
        if at_end:
            text.see("end")
        if not stop.is_set():
            root.after(1000, refresh)
    refresh()

    def show(*_):
        root.after(0, lambda: (root.deiconify(), root.lift()))

    def hide(*_):
        root.withdraw()

    def quit_all(*_):
        stop.set()
        icon.stop()
        root.after(0, root.destroy)

    icon = pystray.Icon(app_name, _icon_image(), app_name, pystray.Menu(
        pystray.MenuItem("기록 보기", show, default=True),
        pystray.MenuItem("지금 확인", lambda *_: threading.Thread(target=check_now, daemon=True).start()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("종료", quit_all),
    ))
    threading.Thread(target=icon.run, daemon=True).start()

    root.protocol("WM_DELETE_WINDOW", hide)   # 닫기는 트레이로 내리는 것이다
    root.mainloop()
