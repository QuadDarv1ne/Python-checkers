"""Правила шашек: варианты игры, генерация ходов и взятий.

Вся логика правил собрана здесь, чтобы Game отвечал только за интерфейс и
состояние партии. Вариант игры описывается неизменяемым RuleSet, поэтому
переключение правил в меню не меняет код поиска и отрисовки.
"""
from dataclasses import dataclass

from checkers.constants import MOVE_OFFSETS, WHITE_CHECKERS, BLACK_CHECKERS
from checkers.enums import CheckerType, SideType
from checkers.move import Move
from checkers.point import Point


@dataclass(frozen=True)
class RuleSet:
    '''Набор правил варианта игры'''

    key: str
    name_ru: str
    # Дамка ходит и бьёт на любое расстояние (русские/международные шашки)
    queen_flying: bool = True
    # Простая шашка может бить назад
    men_capture_backward: bool = True
    # Турецкий удар: побитые шашки снимаются после завершения всей серии
    turkish_strike: bool = False
    # Если бьёт дамка, простые шашки бить не могут
    queen_must_capture: bool = False
    # Превращение в дамку завершает серию взятий
    promote_ends_chain: bool = True
    # Полуходов без взятий и без движения дамок до ничьей (15 ходов = 30)
    draw_quiet_halfmoves: int = 30
    # Сколько раз должна повториться позиция для ничьей
    repetition_limit: int = 3


RUSSIAN = RuleSet(key='russian', name_ru='Русские')

INTERNATIONAL = RuleSet(
    key='international',
    name_ru='Международные',
    queen_flying=True,
    men_capture_backward=True,
    turkish_strike=True,
)

ENGLISH = RuleSet(
    key='english',
    name_ru='Английские (чекерс)',
    queen_flying=False,
    men_capture_backward=False,
    queen_must_capture=False,
    draw_quiet_halfmoves=80,
)

RULE_SETS = {rules.key: rules for rules in (RUSSIAN, INTERNATIONAL, ENGLISH)}

DEFAULT_RULES = RUSSIAN


def rules_by_key(key) -> RuleSet:
    '''Получить набор правил по ключу с откатом на правила по умолчанию'''
    if isinstance(key, RuleSet):
        return key
    return RULE_SETS.get(str(key), DEFAULT_RULES)


# --- Вспомогательные функции -------------------------------------------------

def friendly_checkers(side: SideType) -> list:
    '''Типы шашек указанной стороны [простая, дамка]'''
    return WHITE_CHECKERS if side == SideType.WHITE else BLACK_CHECKERS


def enemy_checkers(side: SideType) -> list:
    '''Типы шашек противника'''
    return BLACK_CHECKERS if side == SideType.WHITE else WHITE_CHECKERS


def forward_offsets(side: SideType) -> list:
    '''Смещения «вперёд» для простой шашки указанной стороны'''
    if side == SideType.WHITE:
        return [offset for offset in MOVE_OFFSETS if offset.y < 0]
    return [offset for offset in MOVE_OFFSETS if offset.y > 0]


def is_queen(checker_type: CheckerType) -> bool:
    '''Является ли шашка дамкой'''
    return checker_type in (CheckerType.WHITE_QUEEN, CheckerType.BLACK_QUEEN)


def queen_type(side: SideType) -> CheckerType:
    '''Тип дамки указанной стороны'''
    return CheckerType.WHITE_QUEEN if side == SideType.WHITE else CheckerType.BLACK_QUEEN


def promotes(side: SideType, y: int, y_size: int) -> bool:
    '''Достигает ли простая шашка последнего ряда'''
    return y == 0 if side == SideType.WHITE else y == y_size - 1


# --- Генерация ходов ---------------------------------------------------------

def _man_captures(field, x: int, y: int, enemy: list, offsets: list) -> list:
    '''Взятия простой шашкой по заданным направлениям'''
    moves = []
    for offset in offsets:
        mid_x, mid_y = x + offset.x, y + offset.y
        to_x, to_y = x + offset.x * 2, y + offset.y * 2
        if not field.is_within(to_x, to_y):
            continue
        if field.type_at(mid_x, mid_y) in enemy and field.type_at(to_x, to_y) == CheckerType.NONE:
            moves.append(Move(x, y, to_x, to_y))
    return moves


def _queen_captures(field, x: int, y: int, enemy: list, friendly: list) -> list:
    '''Взятия дамкой-летуном через одну шашку на любое расстояние'''
    moves = []
    for offset in MOVE_OFFSETS:
        has_enemy_on_way = False
        for shift in range(1, field.size):
            current_x, current_y = x + offset.x * shift, y + offset.y * shift
            if not field.is_within(current_x, current_y):
                break

            checker_type = field.type_at(current_x, current_y)
            if not has_enemy_on_way:
                if checker_type in enemy:
                    has_enemy_on_way = True
                elif checker_type in friendly:
                    break
                continue

            # За побитой шашкой: пустые клетки — допустимые приземления
            if checker_type == CheckerType.NONE:
                moves.append(Move(x, y, current_x, current_y))
            else:
                break
    return moves


def required_moves(field, side: SideType, rules: RuleSet) -> list:
    '''Список обязательных взятий'''
    friendly = friendly_checkers(side)
    enemy = enemy_checkers(side)
    moves = []

    for y in range(field.y_size):
        for x in range(field.x_size):
            checker_type = field.type_at(x, y)
            if checker_type not in friendly:
                continue

            if is_queen(checker_type):
                if rules.queen_flying:
                    moves.extend(_queen_captures(field, x, y, enemy, friendly))
                else:
                    moves.extend(_man_captures(field, x, y, enemy, MOVE_OFFSETS))
                continue

            offsets = MOVE_OFFSETS if rules.men_capture_backward else forward_offsets(side)
            moves.extend(_man_captures(field, x, y, enemy, offsets))

    if rules.queen_must_capture:
        queen_moves = [move for move in moves
                       if is_queen(field.type_at(move.from_x, move.from_y))]
        if queen_moves:
            return queen_moves

    return moves


def optional_moves(field, side: SideType, rules: RuleSet) -> list:
    '''Список тихих ходов (когда взятий нет)'''
    friendly = friendly_checkers(side)
    moves = []

    for y in range(field.y_size):
        for x in range(field.x_size):
            checker_type = field.type_at(x, y)
            if checker_type not in friendly:
                continue

            if is_queen(checker_type):
                for offset in MOVE_OFFSETS:
                    limit = field.size if rules.queen_flying else 2
                    for shift in range(1, limit):
                        to_x, to_y = x + offset.x * shift, y + offset.y * shift
                        if not field.is_within(to_x, to_y):
                            break
                        if field.type_at(to_x, to_y) != CheckerType.NONE:
                            break
                        moves.append(Move(x, y, to_x, to_y))
                continue

            for offset in forward_offsets(side):
                to_x, to_y = x + offset.x, y + offset.y
                if field.is_within(to_x, to_y) and field.type_at(to_x, to_y) == CheckerType.NONE:
                    moves.append(Move(x, y, to_x, to_y))

    return moves


def moves_for_side(field, side: SideType, rules: RuleSet) -> list:
    '''Ходы стороны: взятие обязательно, если оно есть'''
    captures = required_moves(field, side, rules)
    return captures if captures else optional_moves(field, side, rules)


def capture_points(field, move: Move) -> list:
    '''Клетки шашек, которые снимаются этим ходом'''
    captured = []
    dx = 0 if move.to_x == move.from_x else (1 if move.to_x > move.from_x else -1)
    dy = 0 if move.to_y == move.from_y else (1 if move.to_y > move.from_y else -1)

    x, y = move.from_x + dx, move.from_y + dy
    while (x, y) != (move.to_x, move.to_y):
        if field.type_at(x, y) != CheckerType.NONE:
            captured.append(Point(x, y))
        x += dx
        y += dy
    return captured


def position_key(field) -> tuple:
    '''Компактный ключ позиции для поиска повторов'''
    return tuple(
        field.type_at(x, y).value
        for y in range(field.y_size)
        for x in range(field.x_size)
    )
