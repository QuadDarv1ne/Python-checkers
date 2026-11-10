"""Предпросмотр наборов курсоров из assets/cursors.

Запуск: python tools/cursor_preview.py
Окно показывает все наборы крупно: стрелка, лапка и ожидание.
Нужен только для визуальной проверки, игра его не использует.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk

from checkers import cursor_packs
from checkers.cursor import ARROW, HAND, WAIT, CanvasCursor, CursorStyle
from checkers.theme import DARK

KINDS = (ARROW, HAND, WAIT)
SIZE = 84
CELL = 110
LABEL_WIDTH = 260


def main():
    packs = list(cursor_packs.list_packs().values())
    if not packs:
        raise SystemExit('Нет наборов: сначала запустите tools/build_cursor_packs.py')

    root = tk.Tk()
    root.title('Наборы курсоров')
    width = LABEL_WIDTH + CELL * len(KINDS)
    height = min(900, CELL * len(packs) + 20)
    canvas = tk.Canvas(root, width=width, height=height, bg=DARK.canvas_bg,
                       highlightthickness=0, cursor='none')
    canvas.pack()

    for row, pack in enumerate(packs):
        y = 10 + row * CELL
        canvas.create_text(14, y + CELL // 2, anchor='w', fill=DARK.panel_fg,
                           text=pack.name, font=('Segoe UI', 11))
        for column, kind in enumerate(KINDS):
            x = LABEL_WIDTH + column * CELL + 16
            cursor = CanvasCursor(canvas, CursorStyle(size=SIZE, pack=pack.key),
                                  tag=f'preview_{row}_{kind}')
            cursor.move(x, y + 14, kind)

    root.after(30000, root.destroy)
    root.mainloop()


if __name__ == '__main__':
    main()
