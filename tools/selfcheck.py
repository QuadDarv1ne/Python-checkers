"""Автономная проверка игровой логики без отображения окна.

Запуск: python tools/selfcheck.py
Использует скрытое окно Tk, чтобы проверить ходы, взятия и работу ИИ.
"""
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk

from checkers.game import Game
from checkers.field import Field
from checkers.move import Move
from checkers.point import Point
from checkers.enums import CheckerType, SideType, DifficultyType
from checkers.paths import PROJECT_ROOT, ASSETS_DIR, CONFIG_PATH, ICON_PATH, asset_path
from checkers.settings import Settings, _coerce_bool

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


def test_hint_returns_legal_move():
    print("[7] Подсказка возвращает допустимый ход игрока")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.EASY, sounds_enabled=False)

    hint = game.get_hint()
    legal = game._Game__get_available_moves(SideType.WHITE)
    check("подсказка не пустая", hint is not None)
    check("подсказка входит в список ходов", hint in legal)

    # Показать/скрыть не должно менять позицию
    before = game.white_checkers_count, game.black_checkers_count
    game.show_hint()
    game.hide_hint()
    after = game.white_checkers_count, game.black_checkers_count
    check("подсказка не меняет позицию", before == after)
    root.destroy()


def test_undo_restores_position():
    print("[8] Отмена хода восстанавливает позицию")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.EASY, sounds_enabled=False)

    check("в начале отменять нечего", game.can_undo is False)

    # Сохраним снимок и выполним ход игрока + ответ ИИ
    game._Game__save_snapshot()
    check("после снимка отмена доступна", game.can_undo is True)

    white_before = game.white_checkers_count
    black_before = game.black_checkers_count

    move = game._Game__get_available_moves(SideType.WHITE)[0]
    game._Game__handle_player_turn(move)
    if not game.is_player_turn:
        game._Game__handle_enemy_turn()

    game.undo()
    check("белые восстановлены", game.white_checkers_count == white_before)
    check("чёрные восстановлены", game.black_checkers_count == black_before)
    check("ход снова у игрока", game.is_player_turn is True)
    check("история пуста", game.can_undo is False)
    root.destroy()


def test_game_over_detection():
    print("[9] Определение конца игры")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.EASY, sounds_enabled=False)

    # Импортируем messagebox, чтобы подменить диалог
    from tkinter import messagebox
    shown = []
    original_showinfo = messagebox.showinfo
    messagebox.showinfo = lambda *a, **k: shown.append(a)

    try:
        # Поле, где у чёрных нет ни одной шашки — белые должны победить
        field = Field(8, 8)
        for y in range(8):
            for x in range(8):
                field.at(x, y).change_type(CheckerType.NONE)
        field.at(0, 5).change_type(CheckerType.WHITE_REGULAR)
        game._Game__field = field

        game._Game__handle_enemy_turn()
        check("объявлена победа белых", any('Белые' in str(a) for a in shown))
    finally:
        messagebox.showinfo = original_showinfo
    root.destroy()


def test_paths_are_absolute():
    print("[10] Пути проекта абсолютны и не зависят от CWD")
    check("PROJECT_ROOT существует", PROJECT_ROOT.exists())
    check("PROJECT_ROOT содержит main.py", (PROJECT_ROOT / 'main.py').exists())
    check("ASSETS_DIR существует", ASSETS_DIR.exists())
    check("путь к ассету абсолютный", asset_path('move.wav').is_absolute())
    check("CONFIG_PATH абсолютный", CONFIG_PATH.is_absolute())
    check("ICON_PATH абсолютный", ICON_PATH.is_absolute())
    # Смена рабочей директории не должна менять пути
    old_cwd = os.getcwd()
    try:
        os.chdir(os.environ.get('SystemRoot', os.path.abspath(os.sep)))
        check("путь к ассету стабилен после смены CWD",
              asset_path('move.wav') == ASSETS_DIR / 'move.wav')
    finally:
        os.chdir(old_cwd)


def test_settings_robustness():
    print("[11] Настройки: устойчивость к повреждению и нормализация")
    check("_coerce_bool true", _coerce_bool('true') is True)
    check("_coerce_bool false", _coerce_bool('false') is False)
    check("_coerce_bool 0", _coerce_bool(0) is False)
    check("_coerce_bool мусор -> default", _coerce_bool('xyz', default=True) is True)

    # Резервное копирование текущего config.json
    backup = None
    if CONFIG_PATH.exists():
        backup = CONFIG_PATH.read_bytes()
    try:
        CONFIG_PATH.write_text('{ broken', encoding='utf-8')
        s = Settings()
        check("битый json -> сложность по умолчанию", s.difficulty == 1)
        check("битый json -> звук включён", s.sounds_enabled is True)

        CONFIG_PATH.write_text('{"difficulty": 99, "sounds_enabled": "false"}', encoding='utf-8')
        s = Settings()
        check("сложность ограничена 3", s.difficulty == 3)
        check("строка 'false' -> False", s.sounds_enabled is False)

        s.save()
        leftovers = list(CONFIG_PATH.parent.glob('.config-*.tmp'))
        check("нет временных файлов после save", leftovers == [])
        check("config.json валиден после save",
              isinstance(json.loads(CONFIG_PATH.read_text(encoding='utf-8')), dict))
    finally:
        if backup is not None:
            CONFIG_PATH.write_bytes(backup)
        elif CONFIG_PATH.exists():
            CONFIG_PATH.unlink()


def test_missing_assets_fallback():
    print("[12] Отсутствие изображений не ломает игру")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.EASY, sounds_enabled=False)

    # Подменяем изображения на None, имитируя отсутствие файлов
    game._Game__images = {t: None for t in game._Game__images}
    # Перерисовка не должна бросать исключение
    try:
        game._Game__draw()
        drawn_ok = True
    except Exception:
        drawn_ok = False
    check("перерисовка с отсутствующими изображениями", drawn_ok)
    root.destroy()


def test_hash_and_equality():
    print("[13] Хэширование и сравнение Move/Point")
    m1, m2, m3 = Move(1, 2, 3, 4), Move(1, 2, 3, 4), Move(1, 2, 3, 5)
    check("равные Move хэшируются одинаково", hash(m1) == hash(m2))
    check("множество ходов схлопывает равные", len({m1, m2, m3}) == 2)
    check("Move != другой ход", m1 != m3)
    check("Move == равный ход", m1 == m2)
    check("Move != не-ход", (m1 == 'x') is False and m1 != 'x')

    p1, p2, p3 = Point(1, 2), Point(1, 2), Point(2, 2)
    check("равные Point хэшируются одинаково", hash(p1) == hash(p2))
    check("множество точек схлопывает равные", len({p1, p2, p3}) == 2)
    check("Point != другая точка", p1 != p3)
    check("пустая Point ложна", bool(Point()) is False)
    check("заполненная Point истинна", bool(p1) is True)


def test_evaluate_symmetry():
    print("[14] Оценка позиции симметрична сторонам")
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)
    game = Game(canvas, 8, 8, DifficultyType.MEDIUM, sounds_enabled=False)

    def build(mirror: bool):
        field = Field(8, 8)
        for y in range(8):
            for x in range(8):
                field.at(x, y).change_type(CheckerType.NONE)
        white = [(1, 6), (3, 6), (5, 4)]
        black = [(6, 1), (2, 3), (4, 2)]
        for x, y in white:
            yy = 7 - y if mirror else y
            field.at(x, yy).change_type(CheckerType.BLACK_REGULAR if mirror else CheckerType.WHITE_REGULAR)
        for x, y in black:
            yy = 7 - y if mirror else y
            field.at(x, yy).change_type(CheckerType.WHITE_REGULAR if mirror else CheckerType.BLACK_REGULAR)
        # Дамки тоже зеркалятся
        field.at(0, 5 if not mirror else 2).change_type(
            CheckerType.WHITE_QUEEN if not mirror else CheckerType.BLACK_QUEEN)
        field.at(7, 2 if not mirror else 5).change_type(
            CheckerType.BLACK_QUEEN if not mirror else CheckerType.WHITE_QUEEN)
        return field

    game._Game__field = build(mirror=False)
    white_eval = game._Game__evaluate_field(SideType.WHITE)
    game._Game__field = build(mirror=True)
    black_eval = game._Game__evaluate_field(SideType.BLACK)
    check("оценка зеркальной позиции совпадает", abs(white_eval - black_eval) < 1e-9)

    # Продвижение: белая у верхнего края должна оцениваться выше, чем у своего
    for y, label in ((1, 'у вражеского края'), (6, 'у своего края')):
        field = Field(8, 8)
        for yy in range(8):
            for xx in range(8):
                field.at(xx, yy).change_type(CheckerType.NONE)
        field.at(3, y).change_type(CheckerType.WHITE_REGULAR)
        field.at(4, 4).change_type(CheckerType.BLACK_REGULAR)
        game._Game__field = field
        if label.startswith('у вражеского'):
            advanced = game._Game__evaluate_field(SideType.WHITE)
        else:
            home = game._Game__evaluate_field(SideType.WHITE)
    check("продвинувшаяся белая оценивается выше", advanced > home)
    root.destroy()


def test_sound_manager():
    print("[15] SoundManager: состояние и устойчивость")
    from checkers.game import SoundManager
    sm = SoundManager()
    check("available — булево", isinstance(sm.available, bool))
    # set_enabled(True) без бэкенда оставляет выключенным
    sm.set_enabled(True)
    check("enabled не противоречит available", sm.enabled == (sm.available and True) or not sm.available)
    sm.set_enabled(False)
    check("set_enabled(False) выключает", sm.enabled is False)
    sm.set_enabled(True)
    enabled_after_on = sm.enabled
    check("enabled_str принимает допустимые значения",
          sm.enabled_str in ('Вкл', 'Выкл', 'Недоступен'))
    if sm.available:
        sm.toggle()
        check("toggle меняет состояние", sm.enabled != enabled_after_on)
    # Вызов не должен бросать исключение ни при каком состоянии
    try:
        sm.play('move')
        sm.play('capture')
        sm.play('queen')
        sm.play('несуществующий')
        play_ok = True
    except Exception:
        play_ok = False
    check("play() не бросает исключений", play_ok)


def test_difficulty_noise():
    print("[16] Случайность ИИ осмысленна и убывает со сложностью")
    check("шум убывает с ростом уровня",
          DifficultyType.EASY.noise_scale > DifficultyType.MEDIUM.noise_scale >
          DifficultyType.HARD.noise_scale > 0)
    check("гроссмейстер детерминирован", DifficultyType.GRANDMASTER.noise_scale == 0)

    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=600, height=600)

    def setup(game):
        field = Field(8, 8)
        for y in range(8):
            for x in range(8):
                field.at(x, y).change_type(CheckerType.NONE)
        for x, y, t in [
            (1, 6, CheckerType.WHITE_REGULAR), (3, 6, CheckerType.WHITE_REGULAR),
            (5, 6, CheckerType.WHITE_REGULAR), (7, 5, CheckerType.WHITE_REGULAR),
            (0, 5, CheckerType.WHITE_QUEEN),
            (6, 1, CheckerType.BLACK_REGULAR), (2, 1, CheckerType.BLACK_REGULAR),
            (4, 3, CheckerType.BLACK_REGULAR), (6, 3, CheckerType.BLACK_REGULAR),
            (5, 0, CheckerType.BLACK_QUEEN),
        ]:
            field.at(x, y).change_type(t)
        game._Game__field = field

    # Лёгкий уровень должен варьировать ходы
    easy = Game(canvas, 8, 8, DifficultyType.EASY, sounds_enabled=False)
    setup(easy)
    easy_moves = {str(easy._Game__predict_optimal_move(SideType.BLACK)) for _ in range(40)}
    check("лёгкий уровень варьирует ходы", len(easy_moves) >= 2)

    # Гроссмейстер — детерминирован при равном шуме 0
    gm = Game(canvas, 8, 8, DifficultyType.GRANDMASTER, sounds_enabled=False)
    setup(gm)
    gm_moves = {str(gm._Game__predict_optimal_move(SideType.BLACK)) for _ in range(5)}
    check("гроссмейстер детерминирован", len(gm_moves) == 1)
    root.destroy()


def test_difficulty_clamp():
    print("[17] Ограничение индекса сложности")
    from checkers.settings import _clamp_difficulty, DEFAULT_DIFFICULTY_INDEX
    last = len(list(DifficultyType)) - 1
    check("99 -> максимум", _clamp_difficulty(99) == last)
    check("-5 -> 0", _clamp_difficulty(-5) == 0)
    check("'abc' -> default", _clamp_difficulty('abc') == DEFAULT_DIFFICULTY_INDEX)
    check("None -> default", _clamp_difficulty(None) == DEFAULT_DIFFICULTY_INDEX)
    check("2 -> 2", _clamp_difficulty(2) == 2)
    check("2.7 -> 2", _clamp_difficulty(2.7) == 2)
    # Свойство setter не должно писать мусор
    backup = CONFIG_PATH.read_bytes() if CONFIG_PATH.exists() else None
    try:
        s = Settings()
        s.difficulty = 999
        check("setter ограничивает значение", s.difficulty == last)
        s.difficulty = 'мусор'
        check("setter принимает default для мусора", s.difficulty == DEFAULT_DIFFICULTY_INDEX)
    finally:
        if backup is not None:
            CONFIG_PATH.write_bytes(backup)
        elif CONFIG_PATH.exists():
            CONFIG_PATH.unlink()


def test_field_copy_types():
    print("[18] Field.copy сохраняет все типы шашек")
    field = Field(8, 8)
    field.at(0, 5).change_type(CheckerType.WHITE_QUEEN)
    field.at(1, 2).change_type(CheckerType.NONE)
    field.at(6, 3).change_type(CheckerType.BLACK_QUEEN)
    copy = Field.copy(field)
    same = all(field.type_at(x, y) == copy.type_at(x, y)
               for y in range(8) for x in range(8))
    check("все 64 клетки совпадают", same)
    check("копия независима (дамка)", copy.at(0, 5).type == CheckerType.WHITE_QUEEN)
    copy.at(0, 5).change_type(CheckerType.NONE)
    check("изменение копии не трогает оригинал", field.type_at(0, 5) == CheckerType.WHITE_QUEEN)
    # Непрямоугольное поле
    rect = Field(6, 4)
    rect_copy = Field.copy(rect)
    check("размеры прямоугольного поля сохранены",
          rect_copy.x_size == 6 and rect_copy.y_size == 4 and rect_copy.size == 6)


def main():
    print("=== Самопроверка логики шашек ===")
    test_initial_field()
    test_queen_moves_no_crash()
    test_forced_continuation()
    test_ai_single_move()
    test_ai_forced_capture_sequence()
    test_field_copy()
    test_hint_returns_legal_move()
    test_undo_restores_position()
    test_game_over_detection()
    test_paths_are_absolute()
    test_settings_robustness()
    test_missing_assets_fallback()
    test_hash_and_equality()
    test_evaluate_symmetry()
    test_sound_manager()
    test_difficulty_noise()
    test_difficulty_clamp()
    test_field_copy_types()
    print("=== Итог ===")
    print(f"Пройдено: {len(PASSED)}, провалено: {len(FAILED)}")
    if FAILED:
        for name in FAILED:
            print(f"  ПРОВАЛ: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
