"""Курсор, нарисованный на холсте.

Tk на Windows не умеет курсоры из файла (синтаксис @file — только для X11),
поэтому системный курсор над доской скрывается (`cursor='none'`), а свой
рисуется элементами холста. Такой курсор масштабируется вместе с доской,
перекрашивается в любой цвет и не требует установки курсоров в систему.

Источники формы:
- готовые наборы из `assets/cursors` (Minimalistic V5, Oreo, Glib) — PNG,
  собранные из .cur/.ani скриптом tools/build_cursor_packs.py;
- векторные формы на случай, если наборы недоступны: контур сглаживается
  сплайном, есть светлая обводка и тень.
"""
from dataclasses import dataclass

from tkinter import PhotoImage

from checkers import cursor_packs
from checkers.theme import Theme

# Палитра курсоров: ключ, название и цвет. `native` — цвет самого набора
CURSOR_COLORS = {
    'native': ('Как в наборе', None),
    'accent': ('Как в теме', None),
    'green': ('Зелёный', '#3fbf5f'),
    'blue': ('Синий', '#3b82f6'),
    'cyan': ('Голубой', '#22c7d6'),
    'purple': ('Фиолетовый', '#a855f7'),
    'orange': ('Оранжевый', '#f97316'),
    'pink': ('Розовый', '#ec4899'),
    'yellow': ('Жёлтый', '#eab308'),
    'white': ('Белый', '#f5f5f5'),
}

DEFAULT_CURSOR_COLOR = 'native'

# PhotoImage живёт, пока на него есть ссылка: держим их в модульном кэше,
# иначе Tk удаляет изображение вместе с временным объектом курсора
_PHOTO_CACHE = {}
MAX_PHOTO_CACHE = 48

# Виды курсора
ARROW = 'arrow'
HAND = 'hand'
WAIT = 'wait'

# Контур стрелки в долях размера: остриё в (0, 0)
ARROW_SHAPE = (
    (0.00, 0.00),
    (0.06, 0.42),
    (0.14, 0.80),
    (0.30, 0.74),
    (0.42, 1.00),
    (0.56, 0.94),
    (0.44, 0.68),
    (0.72, 0.66),
    (0.46, 0.42),
    (0.20, 0.20),
)

# Контур лапки: остриё в (0, 0), «пальцы» ниже
HAND_SHAPE = (
    (0.00, 0.00),
    (0.04, 0.44),
    (0.12, 0.86),
    (0.28, 1.02),
    (0.40, 1.22),
    (0.52, 1.16),
    (0.44, 0.96),
    (0.68, 0.92),
    (0.52, 0.74),
    (0.26, 0.30),
)


def cursor_color(key: str, theme: Theme) -> str:
    '''Цвет курсора по ключу палитры (или акцентный цвет темы)'''
    if key == 'accent':
        return theme.accent
    if key == cursor_packs.NATIVE_COLOR:
        return cursor_packs.NATIVE_COLOR
    entry = CURSOR_COLORS.get(key)
    if entry is None or entry[1] is None:
        return cursor_packs.NATIVE_COLOR
    return entry[1]


def shade(color: str, factor: float) -> str:
    '''Осветлить (factor > 1) или затемнить (factor < 1) цвет #rrggbb'''
    try:
        value = color.lstrip('#')
        r, g, b = (int(value[index:index + 2], 16) for index in (0, 2, 4))
    except (ValueError, AttributeError):
        return color
    r, g, b = (max(0, min(255, int(channel * factor))) for channel in (r, g, b))
    return f'#{r:02x}{g:02x}{b:02x}'


@dataclass
class CursorStyle:
    '''Параметры отрисовки курсора'''

    color: str = cursor_packs.NATIVE_COLOR
    size: float = 24.0
    enabled: bool = True
    pack: str = ''


class CanvasCursor:
    '''Свой курсор поверх холста вместо системного'''

    TAG = 'custom_cursor'

    def __init__(self, canvas, style: CursorStyle = None, tag: str = None):
        self.__canvas = canvas
        self.style = style or CursorStyle()
        # Свой тег нужен, когда на одном холсте рисуется несколько курсоров
        self.tag = tag or self.TAG
        self.__kind = ARROW
        self.__x = -1000
        self.__y = -1000
        self.__visible = False
        self.__system_hidden = False

    # -- Настройки --

    def set_enabled(self, enabled: bool):
        '''Включить или выключить свой курсор'''
        self.style.enabled = bool(enabled)
        if not self.style.enabled:
            self.hide()
            self.__restore_system()
        else:
            self.__hide_system()

    def set_color(self, color: str):
        '''Перекрасить курсор'''
        self.style.color = color
        if self.__visible:
            self.__draw()

    def set_size(self, size: float):
        '''Задать размер курсора (обычно размер клетки доски)'''
        self.style.size = max(12.0, float(size))
        if self.__visible:
            self.__draw()

    def set_pack(self, key: str):
        '''Выбрать набор курсоров (пустая строка — векторная форма)'''
        if key and cursor_packs.pack_by_key(key) is None:
            key = ''
        self.style.pack = key
        if self.__visible:
            self.__draw()

    @property
    def enabled(self) -> bool:
        return self.style.enabled

    @property
    def kind(self) -> str:
        '''Текущий вид курсора'''
        return self.__kind

    @property
    def pack(self):
        '''Текущий набор курсоров или None'''
        return cursor_packs.pack_by_key(self.style.pack)

    # -- Системный курсор --

    def __hide_system(self):
        try:
            self.__canvas.config(cursor='none')
            self.__system_hidden = True
        except Exception:
            self.__system_hidden = False

    def __restore_system(self):
        if not self.__system_hidden:
            return
        try:
            self.__canvas.config(cursor='')
        except Exception:
            pass
        self.__system_hidden = False

    # -- Отрисовка --

    def move(self, x: float, y: float, kind: str = None):
        '''Переместить курсор и при необходимости сменить вид'''
        if kind is not None:
            self.__kind = kind
        self.__x, self.__y = x, y
        if not self.style.enabled:
            return
        if not self.__system_hidden:
            self.__hide_system()
        self.__visible = True
        self.__draw()

    def hide(self):
        '''Скрыть нарисованный курсор'''
        self.__visible = False
        try:
            self.__canvas.delete(self.tag)
        except Exception:
            pass

    def __photo(self, pack, kind: str, color: str, height: int):
        '''Готовый PhotoImage из набора (с кэшем по размеру и цвету)'''
        cache_key = (pack.key, kind, color, height)
        cached = _PHOTO_CACHE.get(cache_key)
        if cached is not None:
            return cached

        image, hotspot = cursor_packs.render(pack, kind, height, color)
        if image is None:
            return None, (0, 0)
        photo = PhotoImage(master=self.__canvas, data=_png_bytes(image), format='png')
        if len(_PHOTO_CACHE) >= MAX_PHOTO_CACHE:
            _PHOTO_CACHE.clear()
        _PHOTO_CACHE[cache_key] = (photo, hotspot)
        return photo, hotspot

    def __draw(self):
        canvas = self.__canvas
        tag = self.tag
        try:
            canvas.delete(tag)
        except Exception:
            return

        pack = self.pack
        if pack is not None:
            if self.__draw_image(pack, tag):
                return

        self.__draw_vector(tag)

    def __draw_image(self, pack, tag) -> bool:
        '''Нарисовать растровый курсор из набора'''
        height = int(round(self.style.size))
        color = self.style.color or cursor_packs.NATIVE_COLOR
        photo, (hot_x, hot_y) = self.__photo(pack, self.__kind, color, height)
        if photo is None:
            return False
        self.__canvas.create_image(self.__x - hot_x, self.__y - hot_y,
                                   image=photo, anchor='nw', tag=tag)
        return True

    def __points(self, shape, size: float, dx: float = 0.0, dy: float = 0.0,
                 scale: float = 1.0) -> list:
        return [coordinate for point in shape
                for coordinate in (self.__x + point[0] * size * scale + dx,
                                   self.__y + point[1] * size * scale + dy)]

    def __draw_vector(self, tag):
        '''Запасная отрисовка: векторная форма, если наборов нет'''
        canvas = self.__canvas
        size = self.style.size
        color = self.style.color
        if not color or color == cursor_packs.NATIVE_COLOR:
            color = '#3fbf5f'
        dark = shade(color, 0.55)
        light = shade(color, 1.45)

        if self.__kind == WAIT:
            radius = size * 0.44
            x, y = self.__x, self.__y
            canvas.create_oval(x - radius + 1.2, y - radius + 1.6,
                               x + radius + 1.2, y + radius + 1.6,
                               fill=dark, outline='', stipple='gray50', tag=tag)
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                               fill=shade(color, 1.9), outline=dark, width=1.4, tag=tag)
            canvas.create_line(x, y, x, y - radius * 0.66, fill=dark,
                               width=1.6, capstyle='round', tag=tag)
            canvas.create_line(x, y, x + radius * 0.48, y, fill=dark,
                               width=1.6, capstyle='round', tag=tag)
            return

        shape = HAND_SHAPE if self.__kind == HAND else ARROW_SHAPE

        canvas.create_polygon(
            self.__points(shape, size, dx=1.4, dy=1.8),
            fill=dark, outline='', stipple='gray50', smooth=True, splinesteps=16,
            tag=tag,
        )
        canvas.create_polygon(
            self.__points(shape, size),
            fill=light, outline='', smooth=True, splinesteps=16, tag=tag,
        )
        inner = [(point[0] * 0.86 + 0.07, point[1] * 0.86 + 0.05) for point in shape]
        canvas.create_polygon(
            self.__points(inner, size),
            fill=color, outline='', smooth=True, splinesteps=16, tag=tag,
        )


def _png_bytes(image) -> bytes:
    '''PNG в base64-строке: Tk PhotoImage понимает data= только так'''
    import base64
    import io

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')
