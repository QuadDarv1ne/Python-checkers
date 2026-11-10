"""Шахматная нотация клеток и ходов.

Клетки именуются как на доске: файлы a–h слева направо, ранги 1–8 снизу
вверх — с точки зрения стороны, за которую играет игрок. Поэтому при игре
за чёрных нумерация переворачивается вместе с доской.
"""
from checkers.enums import SideType

FILES = 'abcdefgh'


def square_name(x: int, y: int, x_size: int, y_size: int,
                side: SideType = SideType.WHITE) -> str:
    '''Название клетки доски (x, y) для указанной стороны'''
    if side == SideType.BLACK:
        file_index = x_size - 1 - x
        rank = y + 1
    else:
        file_index = x
        rank = y_size - y
    file_index = max(0, min(len(FILES) - 1, file_index))
    return f'{FILES[file_index]}{rank}'


def move_notation(move, x_size: int, y_size: int,
                  side: SideType = SideType.WHITE, is_capture: bool = False) -> str:
    '''Нотация одного хода: a3-b4 для тихого, a3:c5 для взятия'''
    separator = ':' if is_capture else '-'
    start = square_name(move.from_x, move.from_y, x_size, y_size, side)
    end = square_name(move.to_x, move.to_y, x_size, y_size, side)
    return f'{start}{separator}{end}'


def chain_notation(legs, x_size: int, y_size: int,
                   side: SideType = SideType.WHITE, is_capture: bool = True) -> str:
    '''Нотация серии ходов одной шашкой: a3:c5:e7'''
    if not legs:
        return ''
    separator = ':' if is_capture else '-'
    parts = [square_name(legs[0].from_x, legs[0].from_y, x_size, y_size, side)]
    for leg in legs:
        parts.append(square_name(leg.to_x, leg.to_y, x_size, y_size, side))
    return separator.join(parts)
