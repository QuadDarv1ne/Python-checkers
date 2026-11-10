"""Темы оформления доски и интерфейса.

Тема — неизменяемый набор цветов. Game рисует доску цветами темы, а
main.py — панель статуса, историю ходов и тосты, поэтому смена темы
затрагивает всё окно сразу.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    '''Набор цветов интерфейса'''

    key: str
    name_ru: str

    # Доска
    board_light: str
    board_dark: str
    canvas_bg: str
    coordinate: str

    # Подсветка клеток
    hover_border: str
    select_border: str
    move_dot: str
    last_move: str
    hover_target: str
    hint_from: str
    hint_to: str

    # Панель и диалоги
    panel_bg: str
    panel_fg: str
    panel_muted: str
    separator: str
    accent: str
    accent_fg: str

    # Заглушки шашек, если изображения недоступны
    white_piece: str
    black_piece: str


CLASSIC = Theme(
    key='classic',
    name_ru='Классика',
    board_light='#E7CFA9',
    board_dark='#927456',
    canvas_bg='#f5f1e8',
    coordinate='#6b5a45',
    hover_border='#54b346',
    select_border='#944444',
    move_dot='#944444',
    last_move='#4a90d9',
    hover_target='#54b346',
    hint_from='#FFD700',
    hint_to='#54b346',
    panel_bg='#f5f1e8',
    panel_fg='#3b322a',
    panel_muted='#7a6a58',
    separator='#d8cdb9',
    accent='#8a5a2b',
    accent_fg='#ffffff',
    white_piece='#f5f5f5',
    black_piece='#333333',
)

DARK = Theme(
    key='dark',
    name_ru='Тёмная',
    board_light='#6f6a63',
    board_dark='#3b3833',
    canvas_bg='#24262b',
    coordinate='#a8a196',
    hover_border='#4fbf67',
    select_border='#d9605c',
    move_dot='#e0b341',
    last_move='#5aa9e6',
    hover_target='#4fbf67',
    hint_from='#e0b341',
    hint_to='#4fbf67',
    panel_bg='#24262b',
    panel_fg='#e8e4dc',
    panel_muted='#9b958a',
    separator='#3a3d44',
    accent='#c98b3f',
    accent_fg='#1c1e22',
    white_piece='#e8e4dc',
    black_piece='#1f2125',
)

THEMES = {theme.key: theme for theme in (CLASSIC, DARK)}

DEFAULT_THEME = CLASSIC


def theme_by_key(key: str) -> Theme:
    '''Получить тему по ключу с откатом на тему по умолчанию'''
    if isinstance(key, Theme):
        return key
    return THEMES.get(str(key), DEFAULT_THEME)
