"""Всплывающие уведомления вместо модальных диалогов.

Тост — небольшая плашка в правом нижнем углу окна: не блокирует игру,
исчезает сама и не мешает кликать по доске (события мыши проходят мимо).
"""
from tkinter import Frame, Label

TOAST_MS = 2600
MAX_TOASTS = 3

# Цвета по типу сообщения
KINDS = {
    'info': ('#3b322a', '#ffffff'),
    'ok': ('#2f6b3a', '#ffffff'),
    'warn': ('#8a5a2b', '#ffffff'),
    'error': ('#8c3a35', '#ffffff'),
}


class ToastManager:
    '''Очередь плашек в углу родительского окна'''

    def __init__(self, root, offset_y: int = 0):
        self.__root = root
        self.__offset_y = offset_y
        self.__toasts: list[Frame] = []

    def show(self, text: str, kind: str = 'info'):
        '''Показать сообщение'''
        try:
            self.__root.update_idletasks()
        except Exception:
            return

        background, foreground = KINDS.get(kind, KINDS['info'])
        toast = Frame(self.__root, bg=background, bd=0, highlightthickness=0)
        label = Label(toast, text=text, bg=background, fg=foreground,
                      font=('Segoe UI', 9), padx=12, pady=6, justify='left')
        label.pack()
        toast.place(relx=1.0, rely=1.0, x=-12, y=-12 - self.__offset_y, anchor='se')
        toast.lift()

        # Старые плашки сдвигаются вверх
        self.__toasts.append(toast)
        while len(self.__toasts) > MAX_TOASTS:
            self.__dismiss(self.__toasts[0])

        self.__restack()
        self.__root.after(TOAST_MS, lambda: self.__dismiss(toast))

    def __restack(self):
        '''Разложить плашки стопкой снизу вверх'''
        y = -12 - self.__offset_y
        for toast in reversed(self.__toasts):
            try:
                toast.place_configure(y=y, relx=1.0, rely=1.0, x=-12, anchor='se')
                toast.update_idletasks()
                y -= toast.winfo_reqheight() + 6
            except Exception:
                continue

    def __dismiss(self, toast):
        if toast not in self.__toasts:
            return
        self.__toasts.remove(toast)
        try:
            toast.destroy()
        except Exception:
            pass
        self.__restack()
