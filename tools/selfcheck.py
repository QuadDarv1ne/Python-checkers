"""Автономная проверка игровой логики без отображения окна.

Запуск: python tools/selfcheck.py
Использует скрытое окно Tk, чтобы проверить ходы, взятия и работу ИИ.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk

from checkers.game import Game
from checkers.field import Field
from checkers.move import Move
from checkers.point import Point
from checkers.enums import CheckerType, SideType, DifficultyType

PASSED = []
FAILED = []


def check(name, condition):
    if condition:
        PASSED.append(name)
        print(f"  OK   {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name}")


def make_game():
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.MEDIUM, sounds_enabled=False)
    return root, canvas, game


def test_initial_field():
    print("[1] Начальная расстановка")
    field = Field(8, 8)
    check("12 белых шашек", field.white_checkers_count == 12)
    check("12 чёрных шашек", field.black_checkers_count == 12)
    check("клетка (0,0) пуста", field.type_at(0, 0) == CheckerType.NONE)
    check("белая на (0,5)", field.type_at(0, 5) == CheckerType.WHITE_REGULAR)
    check("чёрная на (1,2)", field.type_at(1, 2) == CheckerType.BLACK_REGULAR)


def test_queen_moves_no_crash():
    print("[2] Ходы дамки не выходят за границы")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.MEDIUM, sounds_enabled=False)

    # Пустое поле с одной белой дамкой в углу
    game._Game__field = Field(8, 8)
    for y in range(8):
        for x in range(8):
            game._Game__field.at(x, y).change_type(CheckerType.NONE)
    game._Game__field.at(0, 7).change_type(CheckerType.WHITE_QUEEN)

    moves = game._Game__get_moves_list(SideType.WHITE)
    check("дамка в углу имеет 7 ходов", len(moves) == 7)
    check("все ходы в пределах поля",
          all(0 <= m.to_x < 8 and 0 <= m.to_y < 8 for m in moves))
    root.destroy()


def test_forced_continuation():
    print("[3] Обязательное продолжение серии взятий")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.MEDIUM, sounds_enabled=False)

    field = Field(8, 8)
    for y in range(8):
        for x in range(8):
            field.at(x, y).change_type(CheckerType.NONE)
    # Белая шашка на (2,5) бьёт чёрную (3,4), затем чёрную (5,2)
    field.at(2, 5).change_type(CheckerType.WHITE_REGULAR)
    field.at(3, 4).change_type(CheckerType.BLACK_REGULAR)
    field.at(5, 2).change_type(CheckerType.BLACK_REGULAR)
    game._Game__field = field

    first = Move(2, 5, 4, 3)
    required_before = game._Game__get_required_moves_list(SideType.WHITE)
    check("первый удар доступен", first in required_before)

    game._Game__handle_player_turn(first)
    check("серия взятий продолжается", game.is_player_turn is True)
    check("шашка зафиксирована на (4,3)",
          game._Game__must_continue_from == Point(4, 3))

    available = game._Game__get_available_moves(SideType.WHITE)
    check("доступен только удар этой же шашкой",
          len(available) == 1 and available[0].from_x == 4 and available[0].from_y == 3)

    second = available[0]
    game._Game__handle_player_turn(second)
    check("после серии ход переходит сопернику", game.is_player_turn is False)
    check("серия сброшена", game._Game__must_continue_from is None)
    check("съедены обе чёрные", game.black_checkers_count == 0)
    root.destroy()


def test_ai_single_move():
    print("[4] ИИ делает ровно один ход за ход")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.EASY, sounds_enabled=False)

    # Начальная позиция: у чёрных ровно один доступный ход (обычные без взятий)
    before = game.black_checkers_count
    white_before = game.white_checkers_count

    # Заставим ИИ сделать один ход напрямую
    move = game._Game__predict_optimal_move(SideType.BLACK)
    check("ИИ вернул ровно один ход", move is not None)
    check("ИИ вернул один объект, а не список", isinstance(move, Move))

    # Проверим, что predict_optimal_moves не применяет несколько ходов
    moves_list = game._Game__predict_optimal_moves(SideType.BLACK)
    check("обёртка возвращает 1 ход", len(moves_list) == 1)
    root.destroy()


def test_ai_forced_capture_sequence():
    print("[5] ИИ завершает обязательную серию взятий")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.EASY, sounds_enabled=False)

    field = Field(8, 8)
    for y in range(8):
        for x in range(8):
            field.at(x, y).change_type(CheckerType.NONE)
    # Игрок — белые. Ход ИИ (чёрные): чёрная (2,2) бьёт белую (3,3), затем белую (5,5)
    field.at(2, 2).change_type(CheckerType.BLACK_REGULAR)
    field.at(3, 3).change_type(CheckerType.WHITE_REGULAR)
    field.at(5, 5).change_type(CheckerType.WHITE_REGULAR)
    # Запасная белая шашка, чтобы партия не завершилась и не сбросила поле
    field.at(7, 7).change_type(CheckerType.WHITE_REGULAR)
    game._Game__field = field

    game._Game__handle_enemy_turn()

    check("ИИ съел обе белые из серии", game.white_checkers_count == 1)
    check("серия сброшена", game._Game__must_continue_from is None)
    check("ход вернулся игроку", game.is_player_turn is True)
    root.destroy()


def test_field_copy():
    print("[6] Копирование поля независимо")
    field = Field(8, 8)
    copy = Field.copy(field)
    copy.at(0, 5).change_type(CheckerType.NONE)
    check("копия изменяется", copy.type_at(0, 5) == CheckerType.NONE)
    check("оригинал не изменяется", field.type_at(0, 5) == CheckerType.WHITE_REGULAR)


def main():
    print("=== Самопроверка логики шашек ===")
    test_initial_field()
    test_queen_moves_no_crash()
    test_forced_continuation()
    test_ai_single_move()
    test_ai_forced_capture_sequence()
    test_field_copy()
    print("=== Итог ===")
    print(f"Пройдено: {len(PASSED)}, провалено: {len(FAILED)}")
    if FAILED:
        for name in FAILED:
            print(f"  ПРОВАЛ: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
