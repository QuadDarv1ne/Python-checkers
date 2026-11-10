"""Поиск лучшего хода: порядок ходов, таблица транспозиций, углубление.

Поиск работает с «полными ходами» (Turn): серия обязательных взятий одной
шашкой считается одним ходом, как в правилах. Это делает оценку корректной
и для турецкого удара.

Ускорения:
- порядок ходов — сначала взятия с большим числом побитых шашек и превращения;
- таблица транспозиций — повторно встреченные позиции не пересчитываются;
- итеративное углубление — поиск идёт от глубины 1 вверх, поэтому в любой
  момент есть готовый лучший ход (важно для лимита по времени и отмены).
"""
import random
import threading
from dataclasses import dataclass, field as dataclass_field
from math import inf
from time import perf_counter
from typing import Callable, Optional

from checkers import rules as R
from checkers.constants import WHITE_CHECKERS
from checkers.enums import CheckerType, SideType
from checkers.field import Field
from checkers.move import Move

# Ход = последовательность шагов одной шашкой
Turn = tuple

# Границы таблицы транспозиций, чтобы память не росла бесконечно
MAX_TRANSPOSITION_ENTRIES = 200_000


@dataclass
class SearchResult:
    '''Результат поиска'''

    move: Optional[Move] = None
    turn: Turn = ()
    score: float = 0.0
    depth: int = 0
    nodes: int = 0
    elapsed: float = 0.0
    cancelled: bool = False


# --- Применение хода ---------------------------------------------------------

def apply_turn(field: Field, turn: Turn, rules: R.RuleSet) -> dict:
    '''Выполнить полный ход и вернуть данные для отката'''
    legs = turn
    first = legs[0]
    start_type = field.type_at(first.from_x, first.from_y)
    side = SideType.WHITE if start_type in WHITE_CHECKERS else SideType.BLACK

    captured = []
    seen = set()
    for leg in legs:
        for point in R.capture_points(field, leg):
            key = (point.x, point.y)
            if key in seen:
                continue
            seen.add(key)
            captured.append((point, field.type_at(point.x, point.y)))
            # При турецком ударе шашка остаётся на доске до конца серии
            if not rules.turkish_strike:
                field.at(point.x, point.y).change_type(CheckerType.NONE)

    last = legs[-1]
    promoted = False
    if not R.is_queen(start_type) and R.promotes(side, last.to_y, field.y_size):
        promoted = True

    field.at(last.to_x, last.to_y).change_type(R.queen_type(side) if promoted else start_type)
    field.at(first.from_x, first.from_y).change_type(CheckerType.NONE)

    return {
        'turn': turn,
        'start_type': start_type,
        'start': (first.from_x, first.from_y),
        'end': (last.to_x, last.to_y),
        'captured': captured,
        'promoted': promoted,
        'side': side,
    }


def undo_turn(field: Field, undo: dict):
    '''Откатить ход, выполненный apply_turn'''
    end_x, end_y = undo['end']
    start_x, start_y = undo['start']
    field.at(end_x, end_y).change_type(CheckerType.NONE)
    field.at(start_x, start_y).change_type(undo['start_type'])
    for point, checker_type in undo['captured']:
        field.at(point.x, point.y).change_type(checker_type)


def apply_move(field: Field, move: Move, rules: R.RuleSet) -> dict:
    '''Совместимость: применить один шаг хода'''
    return apply_turn(field, (move,), rules)


# --- Генерация полных ходов --------------------------------------------------

def _man_capture_turns(field: Field, x: int, y: int, side: SideType,
                       rules: R.RuleSet, captured: set, path: list) -> list:
    '''Все продолжения серии взятий простой шашкой'''
    friendly = R.friendly_checkers(side)
    enemy = R.enemy_checkers(side)
    offsets = R.MOVE_OFFSETS if rules.men_capture_backward else R.forward_offsets(side)

    continuations = []
    for offset in offsets:
        mid_x, mid_y = x + offset.x, y + offset.y
        to_x, to_y = x + offset.x * 2, y + offset.y * 2
        if not field.is_within(to_x, to_y):
            continue
        if (mid_x, mid_y) in captured:
            continue
        if field.type_at(mid_x, mid_y) not in enemy:
            continue
        if field.type_at(to_x, to_y) != CheckerType.NONE:
            continue

        # Турецкий удар: побитая шашка остаётся на доске, поэтому её нужно
        # временно убрать, иначе она загородит продолжение серии
        field.at(mid_x, mid_y).change_type(CheckerType.NONE)
        field.at(x, y).change_type(CheckerType.NONE)
        field.at(to_x, to_y).change_type(friendly[0])

        promoted = rules.promote_ends_chain and R.promotes(side, to_y, field.y_size)
        if promoted:
            field.at(to_x, to_y).change_type(R.queen_type(side))
            continuations.append(path + [Move(x, y, to_x, to_y)])
        else:
            deeper = _man_capture_turns(field, to_x, to_y, side, rules,
                                        captured | {(mid_x, mid_y)},
                                        path + [Move(x, y, to_x, to_y)])
            continuations.extend(deeper or [path + [Move(x, y, to_x, to_y)]])

        field.at(to_x, to_y).change_type(CheckerType.NONE)
        field.at(x, y).change_type(friendly[0])
        field.at(mid_x, mid_y).change_type(enemy[0])

    return continuations


def _queen_capture_turns(field: Field, x: int, y: int, side: SideType,
                         captured: set, path: list) -> list:
    '''Все продолжения серии взятий дамкой-летуном'''
    friendly = R.friendly_checkers(side)
    enemy = R.enemy_checkers(side)

    continuations = []
    for offset in R.MOVE_OFFSETS:
        victim = None
        for shift in range(1, field.size):
            current_x, current_y = x + offset.x * shift, y + offset.y * shift
            if not field.is_within(current_x, current_y):
                break
            checker_type = field.type_at(current_x, current_y)
            if victim is None:
                if checker_type in enemy:
                    if (current_x, current_y) in captured:
                        break
                    victim = (current_x, current_y)
                elif checker_type in friendly:
                    break
                continue

            # Дальше идут только пустые клетки — допустимые приземления
            if checker_type != CheckerType.NONE:
                break

            field.at(victim[0], victim[1]).change_type(CheckerType.NONE)
            field.at(x, y).change_type(CheckerType.NONE)
            field.at(current_x, current_y).change_type(friendly[1])

            deeper = _queen_capture_turns(field, current_x, current_y, side,
                                          captured | {victim},
                                          path + [Move(x, y, current_x, current_y)])
            continuations.extend(deeper or [path + [Move(x, y, current_x, current_y)]])

            field.at(current_x, current_y).change_type(CheckerType.NONE)
            field.at(x, y).change_type(friendly[1])
            field.at(victim[0], victim[1]).change_type(enemy[0])

    return continuations


def generate_turns(field: Field, side: SideType, rules: R.RuleSet) -> list:
    '''Все допустимые полные ходы стороны'''
    capture_turns = []
    for y in range(field.y_size):
        for x in range(field.x_size):
            checker_type = field.type_at(x, y)
            if checker_type not in R.friendly_checkers(side):
                continue

            if R.is_queen(checker_type):
                if rules.queen_flying:
                    capture_turns.extend(_queen_capture_turns(field, x, y, side, set(), []))
                else:
                    capture_turns.extend(_man_capture_turns(field, x, y, side, rules, set(), []))
            else:
                capture_turns.extend(_man_capture_turns(field, x, y, side, rules, set(), []))

    if rules.queen_must_capture:
        queen_turns = [turn for turn in capture_turns
                       if R.is_queen(field.type_at(turn[0].from_x, turn[0].from_y))]
        if queen_turns:
            return queen_turns

    if capture_turns:
        return capture_turns

    return [(move,) for move in R.optional_moves(field, side, rules)]


def turn_captures(field: Field, turn: Turn) -> int:
    '''Сколько шашек снимает ход'''
    seen = set()
    for leg in turn:
        for point in R.capture_points(field, leg):
            seen.add((point.x, point.y))
    return len(seen)


# --- Оценка позиции ----------------------------------------------------------

def evaluate_field(field: Field, side: SideType) -> float:
    '''Оценка позиции: материал, центр, защита, продвижение, эндшпиль'''
    enemy_side = SideType.opposite(side)

    my_score = field.get_score(side)
    enemy_score = field.get_score(enemy_side)

    if enemy_score == 0:
        return inf
    if my_score == 0:
        return -inf

    positional = 0.0
    center_x = (field.x_size - 1) / 2
    center_y = (field.y_size - 1) / 2
    total_pieces = field.white_checkers_count + field.black_checkers_count
    endgame = total_pieces <= 4

    for y in range(field.y_size):
        for x in range(field.x_size):
            checker_type = field.type_at(x, y)
            if checker_type == CheckerType.NONE:
                continue

            distance_to_center = abs(x - center_x) + abs(y - center_y)
            center_bonus = (4 - distance_to_center) * 0.1

            defense_bonus = 0.0
            own_side = SideType.WHITE if checker_type in WHITE_CHECKERS else SideType.BLACK
            for offset in R.MOVE_OFFSETS:
                if field.is_within(x + offset.x, y + offset.y):
                    if field.type_at(x + offset.x, y + offset.y) in R.friendly_checkers(own_side):
                        defense_bonus += 0.2

            # Продвижение считается в направлении самой шашки, поэтому
            # зеркальные позиции оцениваются одинаково
            if checker_type in (CheckerType.WHITE_REGULAR, CheckerType.WHITE_QUEEN):
                advance_bonus = (field.y_size - 1 - y) * 0.05
                rows_to_promotion = y
            else:
                advance_bonus = y * 0.05
                rows_to_promotion = field.y_size - 1 - y

            if endgame and not R.is_queen(checker_type):
                # В эндшпиле простая шашка тем ценнее, чем ближе к дамке
                advance_bonus += (field.y_size - rows_to_promotion) * 0.12

            if endgame and R.is_queen(checker_type):
                # Дамке важна подвижность: свободные диагонали
                mobility = 0
                for offset in R.MOVE_OFFSETS:
                    for shift in range(1, field.size):
                        nx, ny = x + offset.x * shift, y + offset.y * shift
                        if not field.is_within(nx, ny) or field.type_at(nx, ny) != CheckerType.NONE:
                            break
                        mobility += 1
                advance_bonus += mobility * 0.02

            value = center_bonus + defense_bonus + advance_bonus
            if own_side == side:
                positional += value
            else:
                positional -= value

    return (my_score / enemy_score) + positional


# --- Движок ------------------------------------------------------------------

@dataclass
class Engine:
    '''Поиск лучшего хода с итеративным углублением'''

    rules: R.RuleSet
    max_depth: int = 3
    time_limit: Optional[float] = None
    noise_scale: float = 0.0
    cancel: Optional[threading.Event] = None
    progress: Optional[Callable] = None

    __nodes: int = dataclass_field(default=0, init=False, repr=False)
    __table: dict = dataclass_field(default_factory=dict, init=False, repr=False)
    __deadline: float = dataclass_field(default=inf, init=False, repr=False)
    __cancelled: bool = dataclass_field(default=False, init=False, repr=False)
    __killers: dict = dataclass_field(default_factory=dict, init=False, repr=False)

    # -- Вспомогательное --

    def __time_is_up(self) -> bool:
        if self.__cancelled:
            return True
        if self.cancel is not None and self.cancel.is_set():
            self.__cancelled = True
            return True
        if perf_counter() >= self.__deadline:
            self.__cancelled = True
            return True
        return False

    def __order_turns(self, field: Field, turns: list, depth: int) -> list:
        '''Сначала взятия и превращения, затем остальное'''
        def score(turn):
            captured = turn_captures(field, turn)
            last = turn[-1]
            checker_type = field.type_at(turn[0].from_x, turn[0].from_y)
            side = SideType.WHITE if checker_type in WHITE_CHECKERS else SideType.BLACK
            promotion = 1 if (not R.is_queen(checker_type)
                              and R.promotes(side, last.to_y, field.y_size)) else 0
            killer = 1 if (depth, turn[0]) == self.__killers.get(depth) else 0
            return (captured, promotion, killer)

        return sorted(turns, key=score, reverse=True)

    # -- Поиск --

    def __negamax(self, field: Field, side: SideType, depth: int,
                  alpha: float, beta: float) -> float:
        self.__nodes += 1
        if (self.__nodes & 1023) == 0 and self.__time_is_up():
            return evaluate_field(field, side)

        if depth <= 0:
            return evaluate_field(field, side)

        key = (R.position_key(field), side.value, depth)
        cached = self.__table.get(key)
        if cached is not None:
            return cached

        turns = generate_turns(field, side, self.rules)
        if not turns:
            # Нет ходов — поражение стороны
            return -inf + (self.max_depth - depth)

        turns = self.__order_turns(field, turns, depth)
        best = -inf
        for turn in turns:
            undo = apply_turn(field, turn, self.rules)
            value = -self.__negamax(field, SideType.opposite(side), depth - 1, -beta, -alpha)
            undo_turn(field, undo)

            if value > best:
                best = value
            if best > alpha:
                alpha = best
            if alpha >= beta:
                self.__killers[depth] = (depth, turn[0])
                break

        if len(self.__table) < MAX_TRANSPOSITION_ENTRIES:
            self.__table[key] = best
        return best

    def __search_root(self, field: Field, side: SideType, turns: list, depth: int):
        '''Оценка всех корневых ходов на заданной глубине'''
        best_score = -inf
        best_turns = []
        ordered = self.__order_turns(field, turns, depth)

        for turn in ordered:
            undo = apply_turn(field, turn, self.rules)
            value = -self.__negamax(field, SideType.opposite(side), depth - 1, -inf, inf)
            undo_turn(field, undo)

            if self.__time_is_up():
                break

            if value > best_score:
                best_score = value
                best_turns = [turn]
            elif value == best_score:
                best_turns.append(turn)

        return best_score, best_turns

    def search(self, field: Field, side: SideType, root_moves: list = None) -> SearchResult:
        '''Найти лучший ход: итеративное углубление от 1 до max_depth'''
        started = perf_counter()
        self.__nodes = 0
        self.__cancelled = False
        self.__table.clear()
        self.__killers.clear()
        self.__deadline = started + self.time_limit if self.time_limit else inf

        turns = generate_turns(field, side, self.rules)
        if root_moves:
            allowed = {(move.from_x, move.from_y, move.to_x, move.to_y) for move in root_moves}
            filtered = [turn for turn in turns
                        if (turn[0].from_x, turn[0].from_y, turn[-1].to_x, turn[-1].to_y) in allowed]
            turns = filtered or turns

        if not turns:
            return SearchResult(elapsed=perf_counter() - started)

        best_turn = turns[0]
        best_score = evaluate_field(field, side)
        reached_depth = 0

        for depth in range(1, max(1, self.max_depth) + 1):
            score, candidates = self.__search_root(field, side, turns, depth)
            if candidates:
                best_turn = candidates[0]
                best_score = score
                reached_depth = depth
            if self.progress is not None:
                try:
                    self.progress(depth, self.max_depth, best_turn[0], best_score)
                except Exception:
                    pass
            if self.__time_is_up() or depth >= self.max_depth:
                break
            if score in (inf, -inf):
                # Найден мат — углубляться незачем
                break

        # Осмысленная случайность: лёгкие уровни иногда выбирают чуть худшие ходы
        if self.noise_scale > 0 and len(turns) > 1:
            scored = []
            for turn in turns:
                undo = apply_turn(field, turn, self.rules)
                value = -self.__negamax(field, SideType.opposite(side),
                                        max(0, reached_depth - 1), -inf, inf)
                undo_turn(field, undo)
                scored.append((value, turn))
            best_value = max(value for value, _ in scored)
            close = [turn for value, turn in scored if best_value - value <= self.noise_scale]
            if close:
                import random
                best_turn = random.choice(close)

        return SearchResult(
            move=best_turn[0],
            turn=tuple(best_turn),
            score=best_score,
            depth=reached_depth,
            nodes=self.__nodes,
            elapsed=perf_counter() - started,
            cancelled=self.__cancelled,
        )
