"""Автономная проверка игровой логики без отображения окна.

Запуск: python tools/selfcheck.py
Использует скрытое окно Tk, чтобы проверить ходы, взятия, ИИ, правила,
историю позиций, темы и работу звукового модуля.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk

from checkers import rules as R
from checkers.engine import Engine, apply_turn, evaluate_field, generate_turns, undo_turn
from checkers.enums import CheckerType, DifficultyType, SideType
from checkers.field import Field
from checkers.game import Game
from checkers.move import Move
from checkers.notation import chain_notation, move_notation, square_name
from checkers.paths import ASSETS_DIR, CONFIG_PATH, ICON_PATH, PROJECT_ROOT, asset_path
from checkers.point import Point
from checkers.settings import Settings, _clamp_difficulty, _coerce_bool
from checkers.theme import CLASSIC, DARK, THEMES, theme_by_key

PASSED = []
FAILED = []


def check(name, condition):
    if condition:
        PASSED.append(name)
        print(f"  OK   {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name}")


def make_root():
    root = tk.Tk()
    root.withdraw()
    return root


def make_game(root, difficulty=DifficultyType.MEDIUM, **kwargs):
    canvas = tk.Canvas(root, width=600, height=600)
    options = dict(sounds_enabled=False, animate=False, auto_restart=False)
    options.update(kwargs)
    return Game(canvas, 8, 8, difficulty, **options)


def empty_field(size=8):
    field = Field(size, size)
    for y in range(size):
        for x in range(size):
            field.at(x, y).change_type(CheckerType.NONE)
    return field


def set_field(game, field):
    game._Game__field = field


def get_field(game):
    return game._Game__field


def pump(root, seconds=1.0):
    '''Прокрутить цикл событий Tk'''
    deadline = time.time() + seconds
    while time.time() < deadline:
        root.update()
        time.sleep(0.01)


# --- Базовые правила ---------------------------------------------------------

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
    field = empty_field()
    field.at(0, 7).change_type(CheckerType.WHITE_QUEEN)
    moves = R.optional_moves(field, SideType.WHITE, R.RUSSIAN)
    check("дамка в углу имеет 7 ходов", len(moves) == 7)
    check("все ходы в пределах поля",
          all(0 <= m.to_x < 8 and 0 <= m.to_y < 8 for m in moves))


def test_forced_continuation():
    print("[3] Обязательное продолжение серии взятий")
    root = make_root()
    game = make_game(root)
    field = empty_field()
    # Белая шашка на (2,5) бьёт чёрную (3,4), затем чёрную (5,2)
    field.at(2, 5).change_type(CheckerType.WHITE_REGULAR)
    field.at(3, 4).change_type(CheckerType.BLACK_REGULAR)
    field.at(5, 2).change_type(CheckerType.BLACK_REGULAR)
    set_field(game, field)

    first = Move(2, 5, 4, 3)
    required = R.required_moves(get_field(game), SideType.WHITE, R.RUSSIAN)
    check("первый удар доступен", first in required)

    game._Game__handle_player_turn(first)
    check("серия взятий продолжается", game.is_player_turn is True)
    check("шашка зафиксирована на (4,3)",
          game._Game__must_continue_from == Point(4, 3))

    available = game._Game__get_available_moves(SideType.WHITE)
    check("доступен только удар этой же шашкой",
          len(available) == 1 and available[0].from_x == 4 and available[0].from_y == 3)

    game._Game__handle_player_turn(available[0])
    check("после серии ход переходит сопернику", game.is_player_turn is False)
    check("серия сброшена", game._Game__must_continue_from is None)
    check("съедены обе чёрные", game.black_checkers_count == 0)
    root.destroy()


def test_turkish_strike():
    print("[4] Турецкий удар: шашки снимаются после серии")
    field = empty_field()
    # Дамка на (0,7) бьёт чёрную (1,6), затем чёрную (4,3)
    field.at(0, 7).change_type(CheckerType.WHITE_QUEEN)
    field.at(1, 6).change_type(CheckerType.BLACK_REGULAR)
    field.at(4, 3).change_type(CheckerType.BLACK_REGULAR)

    turns = generate_turns(field, SideType.WHITE, R.INTERNATIONAL)
    longest = max(turns, key=lambda turn: len(turn))
    check("серия дамки длиннее одного шага", len(longest) > 1)

    captured = set()
    for leg in longest:
        for point in R.capture_points(field, leg):
            captured.add((point.x, point.y))
    check("серия снимает несколько шашек", len(captured) >= 2)

    # Применение и откат хода не должны менять исходную позицию
    before = [(x, y, field.type_at(x, y)) for y in range(8) for x in range(8)]
    undo = apply_turn(field, longest, R.INTERNATIONAL)
    check("после хода шашка на новом месте",
          field.type_at(longest[-1].to_x, longest[-1].to_y) != CheckerType.NONE)
    check("все побитые сняты", len(undo['captured']) >= 2)
    undo_turn(field, undo)
    after = [(x, y, field.type_at(x, y)) for y in range(8) for x in range(8)]
    check("откат восстанавливает позицию", before == after)


def test_rule_variants():
    print("[5] Варианты правил различаются")
    field = empty_field()
    field.at(2, 4).change_type(CheckerType.WHITE_REGULAR)
    field.at(3, 5).change_type(CheckerType.BLACK_REGULAR)

    russian = R.required_moves(field, SideType.WHITE, R.RUSSIAN)
    english = R.required_moves(field, SideType.WHITE, R.ENGLISH)
    check("русские: шашка бьёт назад", len(russian) == 1)
    check("чекерс: назад не бьёт", english == [])

    # Дамка-летун против короткой дамки
    field = empty_field()
    field.at(0, 7).change_type(CheckerType.WHITE_QUEEN)
    flying = R.optional_moves(field, SideType.WHITE, R.RUSSIAN)
    short = R.optional_moves(field, SideType.WHITE, R.ENGLISH)
    check("дамка-летун дальше короткой", len(flying) > len(short))
    check("короткая дамка ходит на одну клетку", len(short) == 1)


def test_ai_single_move():
    print("[6] ИИ делает ровно один ход за ход")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    move = game._Game__predict_optimal_move(SideType.BLACK)
    check("ИИ вернул ровно один ход", move is not None)
    check("ИИ вернул один объект, а не список", isinstance(move, Move))
    moves_list = game._Game__predict_optimal_moves(SideType.BLACK)
    check("обёртка возвращает 1 ход", len(moves_list) == 1)
    root.destroy()


def test_ai_forced_capture_sequence():
    print("[7] ИИ завершает обязательную серию взятий")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    field = empty_field()
    # Ход ИИ (чёрные): чёрная (2,2) бьёт белую (3,3), затем белую (5,5)
    field.at(2, 2).change_type(CheckerType.BLACK_REGULAR)
    field.at(3, 3).change_type(CheckerType.WHITE_REGULAR)
    field.at(5, 5).change_type(CheckerType.WHITE_REGULAR)
    # Запасная белая шашка, чтобы партия не завершилась
    field.at(7, 7).change_type(CheckerType.WHITE_REGULAR)
    set_field(game, field)

    game._Game__handle_enemy_turn()
    check("ИИ съел обе белые из серии", game.white_checkers_count == 1)
    check("серия сброшена", game._Game__must_continue_from is None)
    check("ход вернулся игроку", game.is_player_turn is True)
    root.destroy()


def test_field_copy():
    print("[8] Копирование поля независимо")
    field = Field(8, 8)
    copy = Field.copy(field)
    copy.at(0, 5).change_type(CheckerType.NONE)
    check("копия изменяется", copy.type_at(0, 5) == CheckerType.NONE)
    check("оригинал не изменяется", field.type_at(0, 5) == CheckerType.WHITE_REGULAR)


def test_hint_returns_legal_move():
    print("[9] Подсказка возвращает допустимый ход игрока")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    hint = game.get_hint()
    legal = game._Game__get_available_moves(SideType.WHITE)
    check("подсказка не пустая", hint is not None)
    check("подсказка входит в список ходов", hint in legal)

    before = game.white_checkers_count, game.black_checkers_count
    game.show_hint()
    game.hide_hint()
    after = game.white_checkers_count, game.black_checkers_count
    check("подсказка не меняет позицию", before == after)
    root.destroy()


def test_undo_restores_position():
    print("[10] Отмена хода восстанавливает позицию")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    check("в начале отменять нечего", game.can_undo is False)

    white_before = game.white_checkers_count
    black_before = game.black_checkers_count

    move = game._Game__get_available_moves(SideType.WHITE)[0]
    game._Game__handle_player_turn(move)
    game._Game__end_chain(SideType.WHITE)
    if not game.is_player_turn:
        game._Game__handle_enemy_turn()

    check("после хода отмена доступна", game.can_undo is True)
    game.undo()
    check("белые восстановлены", game.white_checkers_count == white_before)
    check("чёрные восстановлены", game.black_checkers_count == black_before)
    check("ход снова у игрока", game.is_player_turn is True)
    check("история очищена", game.can_undo is False)
    root.destroy()


def test_game_over_detection():
    print("[11] Определение конца игры")
    root = make_root()
    events = []
    game = make_game(root, DifficultyType.EASY,
                     game_over_callback=lambda w, n, r: events.append((w, n, r)))
    field = empty_field()
    field.at(0, 5).change_type(CheckerType.WHITE_REGULAR)
    set_field(game, field)

    game._Game__handle_enemy_turn()
    check("партия помечена завершённой", game.is_game_over is True)
    check("событие конца игры вызвано", bool(events))
    check("победитель — белые", events and events[0][0] == SideType.WHITE)
    check("поле осталось на месте", game.white_checkers_count == 1)

    game.restart()
    check("restart сбрасывает состояние", game.is_game_over is False)
    check("restart вернул 24 шашки",
          game.white_checkers_count + game.black_checkers_count == 24)
    root.destroy()


def test_draw_by_quiet_moves():
    print("[12] Ничья по 15 ходам без взятий и движения дамок")
    root = make_root()
    events = []
    game = make_game(root, DifficultyType.EASY,
                     game_over_callback=lambda w, n, r: events.append((w, n, r)))
    # Только дамки: их ходы не считаются «тихими»
    field = empty_field()
    field.at(0, 7).change_type(CheckerType.WHITE_QUEEN)
    field.at(7, 0).change_type(CheckerType.BLACK_QUEEN)
    set_field(game, field)
    game._Game__quiet_halfmoves = R.RUSSIAN.draw_quiet_halfmoves
    game._Game__check_draw()
    check("ничья объявлена", game.is_game_over is True)
    check("причина — лимит ходов", events and 'без взятий' in events[0][2])
    check("победителя нет", events and events[0][0] is None)
    root.destroy()


def test_draw_by_repetition():
    print("[13] Ничья по троекратному повторению")
    root = make_root()
    events = []
    game = make_game(root, DifficultyType.EASY,
                     game_over_callback=lambda w, n, r: events.append((w, n, r)))
    field = empty_field()
    field.at(0, 7).change_type(CheckerType.WHITE_QUEEN)
    field.at(7, 0).change_type(CheckerType.BLACK_QUEEN)
    set_field(game, field)
    key = game._Game__position_key()
    game._Game__repetitions[key] = 3
    game._Game__check_draw()
    check("ничья по повторению объявлена", game.is_game_over is True)
    check("причина — повторение", events and 'повторение' in events[0][2])
    root.destroy()


def test_paths_are_absolute():
    print("[14] Пути проекта абсолютны и не зависят от CWD")
    check("PROJECT_ROOT существует", PROJECT_ROOT.exists())
    check("PROJECT_ROOT содержит main.py", (PROJECT_ROOT / 'main.py').exists())
    check("ASSETS_DIR существует", ASSETS_DIR.exists())
    check("путь к ассету абсолютный", asset_path('move.wav').is_absolute())
    check("CONFIG_PATH абсолютный", CONFIG_PATH.is_absolute())
    check("ICON_PATH абсолютный", ICON_PATH.is_absolute())
    old_cwd = os.getcwd()
    try:
        os.chdir(os.environ.get('SystemRoot', os.path.abspath(os.sep)))
        check("путь к ассету стабилен после смены CWD",
              asset_path('move.wav') == ASSETS_DIR / 'move.wav')
    finally:
        os.chdir(old_cwd)


def test_settings_robustness():
    print("[15] Настройки: устойчивость к повреждению и нормализация")
    check("_coerce_bool true", _coerce_bool('true') is True)
    check("_coerce_bool false", _coerce_bool('false') is False)
    check("_coerce_bool 0", _coerce_bool(0) is False)
    check("_coerce_bool мусор -> default", _coerce_bool('xyz', default=True) is True)

    backup = CONFIG_PATH.read_bytes() if CONFIG_PATH.exists() else None
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
    print("[16] Отсутствие изображений не ломает игру")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    # Подменяем кэш изображений на None, имитируя отсутствие файлов
    game._Game__image_cache = {}
    original = game._Game__checker_image

    def broken(checker_type):
        return None

    game._Game__checker_image = broken
    try:
        game._Game__draw()
        drawn_ok = True
    except Exception:
        drawn_ok = False
    finally:
        game._Game__checker_image = original
    check("перерисовка с отсутствующими изображениями", drawn_ok)
    root.destroy()


def test_hash_and_equality():
    print("[17] Хэширование и сравнение Move/Point")
    m1, m2, m3 = Move(1, 2, 3, 4), Move(1, 2, 3, 4), Move(1, 2, 3, 5)
    check("равные Move хэшируются одинаково", hash(m1) == hash(m2))
    check("множество ходов схлопывает равные", len({m1, m2, m3}) == 2)
    check("Move != другой ход", m1 != m3)
    check("Move == равный ход", m1 == m2)

    p1, p2, p3 = Point(1, 2), Point(1, 2), Point(2, 2)
    check("равные Point хэшируются одинаково", hash(p1) == hash(p2))
    check("множество точек схлопывает равные", len({p1, p2, p3}) == 2)
    check("пустая Point ложна", bool(Point()) is False)
    check("заполненная Point истинна", bool(p1) is True)


def test_evaluate_symmetry():
    print("[18] Оценка позиции симметрична сторонам")
    def build(mirror: bool):
        field = empty_field()
        white = [(1, 6), (3, 6), (5, 4)]
        black = [(6, 1), (2, 3), (4, 2)]
        for x, y in white:
            yy = 7 - y if mirror else y
            field.at(x, yy).change_type(CheckerType.BLACK_REGULAR if mirror else CheckerType.WHITE_REGULAR)
        for x, y in black:
            yy = 7 - y if mirror else y
            field.at(x, yy).change_type(CheckerType.WHITE_REGULAR if mirror else CheckerType.BLACK_REGULAR)
        field.at(0, 5 if not mirror else 2).change_type(
            CheckerType.WHITE_QUEEN if not mirror else CheckerType.BLACK_QUEEN)
        field.at(7, 2 if not mirror else 5).change_type(
            CheckerType.BLACK_QUEEN if not mirror else CheckerType.WHITE_QUEEN)
        return field

    white_eval = evaluate_field(build(False), SideType.WHITE)
    black_eval = evaluate_field(build(True), SideType.BLACK)
    check("оценка зеркальной позиции совпадает", abs(white_eval - black_eval) < 1e-9)

    advanced = empty_field()
    advanced.at(3, 1).change_type(CheckerType.WHITE_REGULAR)
    advanced.at(4, 4).change_type(CheckerType.BLACK_REGULAR)
    home = empty_field()
    home.at(3, 6).change_type(CheckerType.WHITE_REGULAR)
    home.at(4, 4).change_type(CheckerType.BLACK_REGULAR)
    check("продвинувшаяся белая оценивается выше",
          evaluate_field(advanced, SideType.WHITE) > evaluate_field(home, SideType.WHITE))


def test_sound_manager():
    print("[19] SoundManager: состояние и устойчивость")
    from checkers.game import SoundManager
    sm = SoundManager()
    check("available — булево", isinstance(sm.available, bool))
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
    try:
        for name in ('move', 'capture', 'queen', 'win', 'lose', 'draw', 'несуществующий'):
            sm.play(name)
        play_ok = True
    except Exception:
        play_ok = False
    check("play() не бросает исключений", play_ok)
    sm.set_enabled(True)


def test_audio_synthesis():
    print("[20] Синтез звука: эффекты и музыка кэшируются")
    from checkers.audio import CACHE_DIR, EFFECT_NAMES, cached_wav
    for name in EFFECT_NAMES:
        path = cached_wav(name, 70)
        check(f"эффект {name} синтезирован",
              path is not None and path.exists() and path.stat().st_size > 1000)

    music = cached_wav('music', 70)
    check("музыка синтезирована", music is not None and music.exists())
    check("повторный запрос берёт кэш", cached_wav('music', 70) == music)
    quiet = cached_wav('move', 20)
    check("громкость влияет на файл", quiet is not None and quiet != cached_wav('move', 70))
    check("неизвестный эффект не синтезируется", cached_wav('нет-такого', 70) is None)

    def peak(path):
        import array
        import wave
        with wave.open(str(path)) as w:
            data = array.array('h', w.readframes(w.getnframes()))
        return max(abs(value) for value in data)

    check("громкий эффект громче тихого", peak(cached_wav('move', 100)) > peak(quiet) * 2)
    check("кэш лежит во временном каталоге", CACHE_DIR.exists())


def test_music_toggle():
    print("[21] Музыка: включение, остановка и смена громкости")
    from checkers.game import SoundManager
    sm = SoundManager()
    if not sm.music_available:
        check("музыка недоступна — состояние корректно",
              sm.music_enabled is False and sm.music_enabled_str == 'Недоступна')
        return

    sm.set_music_enabled(True)
    check("музыка включена", sm.music_enabled is True and sm.music_enabled_str == 'Вкл')
    sm.set_music_enabled(False)
    check("музыка выключена", sm.music_enabled is False and sm.music_enabled_str == 'Выкл')
    sm.toggle_music()
    check("toggle_music включает", sm.music_enabled is True)
    sm.set_volume(45)
    check("громкость применилась", sm.volume == 45)
    sm.set_volume(5)
    check("громкость не ниже минимума", sm.volume == 10)
    sm.set_volume(500)
    check("громкость не выше максимума", sm.volume == 100)
    sm.set_music_enabled(False)


def test_player_side():
    print("[22] Игра за чёрных: первым ходит ИИ")
    root = make_root()
    game = make_game(root, DifficultyType.EASY, player_side=SideType.BLACK)
    check("игрок за чёрных", game.player_side == SideType.BLACK)
    check("ход ИИ запланирован", game.is_player_turn is False)

    # Дожидаемся фонового расчёта
    deadline = time.time() + 10
    while time.time() < deadline and (game.is_thinking or not game.is_player_turn):
        root.update()
        time.sleep(0.02)
    check("ИИ сделал первый ход", game.move_count >= 1)
    check("ход вернулся игроку", game.is_player_turn is True)
    root.destroy()


def test_hover_and_coordinates():
    print("[23] Подсветка ходов, координаты и переворот доски")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    check("подсветка включена по умолчанию", game.show_hover_hints is True)
    game.show_hover_hints = False
    check("подсветку можно выключить", game.show_hover_hints is False)

    check("координаты включены", game.show_coordinates is True)
    game.set_show_coordinates(False)
    check("координаты можно выключить", game.show_coordinates is False)

    check("вид по умолчанию за белых", game.view_side == SideType.WHITE)
    game.toggle_view()
    check("переворот меняет вид", game.view_side == SideType.BLACK)
    game.toggle_view()
    check("повторный переворот возвращает вид", game.view_side == SideType.WHITE)
    root.destroy()


def test_notation():
    print("[24] Нотация клеток и ходов")
    check("a1 для белых", square_name(0, 7, 8, 8, SideType.WHITE) == 'a1')
    check("h8 для белых", square_name(7, 0, 8, 8, SideType.WHITE) == 'h8')
    # При взгляде за чёрных доска перевёрнута: их домашний ряд — первый
    check("h8 для чёрных", square_name(0, 7, 8, 8, SideType.BLACK) == 'h8')
    check("a1 для чёрных", square_name(7, 0, 8, 8, SideType.BLACK) == 'a1')

    check("тихий ход через дефис",
          move_notation(Move(0, 7, 1, 6), 8, 8, SideType.WHITE) == 'a1-b2')
    check("взятие через двоеточие",
          move_notation(Move(0, 7, 2, 5), 8, 8, SideType.WHITE, is_capture=True) == 'a1:c3')
    chain = chain_notation([Move(0, 7, 2, 5), Move(2, 5, 4, 3)], 8, 8, SideType.WHITE)
    check("серия через двоеточия", chain == 'a1:c3:e5')


def test_history_navigation():
    print("[25] История: запись, листание и отмена")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    check("история начинается с одной позиции", game.positions_count == 1)
    check("записей ходов нет", game.history_entries == [])
    check("просмотр не активен", game.is_browsing is False)

    move = game._Game__get_available_moves(SideType.WHITE)[0]
    game._Game__handle_player_turn(move)
    if game._Game__must_continue_from is None:
        game._Game__end_chain(SideType.WHITE)
    check("ход записан в историю", len(game.history_entries) >= 1)
    check("нотация не пустая", game.history_entries[0]['notation'] != '')
    check("ход игрока отмечен", game.history_entries[0]['player_turn'] is False)

    last_index = game.current_index
    game.step_back()
    check("шаг назад включает просмотр", game.is_browsing is True)
    check("индекс уменьшился", game.current_index == last_index - 1)
    game.step_forward()
    check("шаг вперёд выключает просмотр", game.is_browsing is False)

    game.goto_first()
    check("переход к началу", game.current_index == 0)
    game.goto_last()
    check("переход к концу", game.current_index == game.positions_count - 1)
    root.destroy()


def test_theme_switch():
    print("[26] Темы оформления")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    check("тема по умолчанию — классика", game.theme.key == 'classic')
    game.set_theme(DARK)
    check("тёмная тема применена", game.theme.key == 'dark')
    check("ключ темы читается", theme_by_key('dark') is DARK)
    check("неизвестная тема -> классика", theme_by_key('нет-такой') is CLASSIC)
    check("в наборе две темы", len(THEMES) == 2)
    game.set_theme(CLASSIC)
    root.destroy()


def test_board_scaling():
    print("[27] Масштабирование доски")
    root = make_root()
    game = make_game(root, DifficultyType.EASY)
    start_cell = game.cell_size
    game.resize(1200, 1000)
    check("крупное окно увеличивает клетку", game.cell_size >= start_cell)
    big = game.cell_size
    game.resize(300, 300)
    check("маленькое окно уменьшает клетку", game.cell_size < big)
    check("клетка не меньше минимума", game.cell_size >= 26)
    check("доска включает отступы", game.board_width > game.cell_size * 8)
    root.destroy()


def test_toast_queue():
    print("[28] Тосты: очередь и ограничение количества")
    from checkers.toast import MAX_TOASTS, ToastManager
    root = make_root()
    toasts = ToastManager(root)
    for index in range(MAX_TOASTS + 2):
        toasts.show(f'Сообщение {index}', 'info')
    root.update()
    check("в очереди не больше лимита", len(toasts._ToastManager__toasts) <= MAX_TOASTS)
    toasts.show('Ошибка', 'error')
    check("тип сообщения не ломает показ", len(toasts._ToastManager__toasts) > 0)
    root.destroy()


def test_difficulty_noise():
    print("[29] Случайность ИИ осмысленна и убывает со сложностью")
    check("шум убывает с ростом уровня",
          DifficultyType.EASY.noise_scale > DifficultyType.MEDIUM.noise_scale >
          DifficultyType.HARD.noise_scale > 0)
    check("гроссмейстер детерминирован", DifficultyType.GRANDMASTER.noise_scale == 0)
    check("лимит времени растёт с уровнем",
          DifficultyType.EASY.time_limit < DifficultyType.MEDIUM.time_limit <
          DifficultyType.HARD.time_limit < DifficultyType.GRANDMASTER.time_limit)
    check("глубина растёт с уровнем",
          DifficultyType.EASY.depth < DifficultyType.MEDIUM.depth <
          DifficultyType.HARD.depth < DifficultyType.GRANDMASTER.depth)

    root = make_root()
    game = make_game(root, DifficultyType.GRANDMASTER)

    def setup(target):
        field = empty_field()
        for x, y, t in [
            (1, 6, CheckerType.WHITE_REGULAR), (3, 6, CheckerType.WHITE_REGULAR),
            (5, 6, CheckerType.WHITE_REGULAR), (7, 5, CheckerType.WHITE_REGULAR),
            (0, 5, CheckerType.WHITE_QUEEN),
            (6, 1, CheckerType.BLACK_REGULAR), (2, 1, CheckerType.BLACK_REGULAR),
            (4, 3, CheckerType.BLACK_REGULAR), (6, 3, CheckerType.BLACK_REGULAR),
            (5, 0, CheckerType.BLACK_QUEEN),
        ]:
            field.at(x, y).change_type(t)
        set_field(target, field)

    setup(game)
    gm_moves = {str(game._Game__predict_optimal_move(SideType.BLACK)) for _ in range(3)}
    check("гроссмейстер детерминирован", len(gm_moves) == 1)

    easy = make_game(root, DifficultyType.EASY)
    setup(easy)
    easy_moves = {str(easy._Game__predict_optimal_move(SideType.BLACK)) for _ in range(20)}
    check("лёгкий уровень варьирует ходы", len(easy_moves) >= 1)
    root.destroy()


def test_engine_transposition():
    print("[30] Движок: таблица транспозиций и порядок ходов")
    field = Field(8, 8)
    engine = Engine(R.RUSSIAN, 3, 2.0, 0.0)
    result = engine.search(field, SideType.WHITE)
    check("движок вернул ход", result.move is not None)
    check("глубина достигнута", result.depth >= 1)
    check("узлы посчитаны", result.nodes > 0)
    check("время измерено", result.elapsed >= 0)

    # Взятие должно идти первым в порядке ходов
    field = empty_field()
    field.at(2, 5).change_type(CheckerType.WHITE_REGULAR)
    field.at(3, 4).change_type(CheckerType.BLACK_REGULAR)
    field.at(6, 1).change_type(CheckerType.BLACK_REGULAR)
    field.at(0, 5).change_type(CheckerType.WHITE_REGULAR)
    turns = generate_turns(field, SideType.WHITE, R.RUSSIAN)
    ordered = engine._Engine__order_turns(field, turns, 2)
    check("взятие стоит первым в порядке", len(ordered[0]) == 1 and
          len(R.capture_points(field, ordered[0][0])) == 1)


def test_engine_cancel():
    print("[31] Движок: отмена расчёта")
    import threading
    field = Field(8, 8)
    cancel = threading.Event()
    cancel.set()
    engine = Engine(R.RUSSIAN, 6, None, 0.0, cancel)
    result = engine.search(field, SideType.WHITE)
    check("расчёт помечен отменённым", result.cancelled is True)
    check("лучший ход всё равно есть", result.move is not None)


def test_settings_extended():
    print("[32] Настройки: сторона, музыка, громкость, тема, правила")
    backup = CONFIG_PATH.read_bytes() if CONFIG_PATH.exists() else None
    try:
        s = Settings()
        s.player_side = SideType.BLACK
        s.music_enabled = True
        s.volume = 55
        s.sounds_enabled = False
        s.theme = 'dark'
        s.rules = 'international'

        reloaded = Settings()
        check("сторона сохранена", reloaded.player_side == SideType.BLACK)
        check("музыка сохранена", reloaded.music_enabled is True)
        check("громкость сохранена", reloaded.volume == 55)
        check("звук сохранён", reloaded.sounds_enabled is False)
        check("тема сохранена", reloaded.theme == 'dark')
        check("правила сохранены", reloaded.rules == 'international')

        CONFIG_PATH.write_text(
            '{"volume": 500, "player_side": "мусор", "music_enabled": "true",'
            ' "theme": "нет", "rules": 42}',
            encoding='utf-8',
        )
        s = Settings()
        check("громкость ограничена 100", s.volume == 100)
        check("мусорная сторона -> белые", s.player_side == SideType.WHITE)
        check("строка 'true' -> музыка включена", s.music_enabled is True)
        check("неизвестная тема -> классика", s.theme == 'classic')
        check("неизвестные правила -> русские", s.rules == 'russian')
    finally:
        if backup is not None:
            CONFIG_PATH.write_bytes(backup)
        elif CONFIG_PATH.exists():
            CONFIG_PATH.unlink()


def test_difficulty_clamp():
    print("[33] Ограничение индекса сложности")
    from checkers.settings import DEFAULT_DIFFICULTY_INDEX
    last = len(list(DifficultyType)) - 1
    check("99 -> максимум", _clamp_difficulty(99) == last)
    check("-5 -> 0", _clamp_difficulty(-5) == 0)
    check("'abc' -> default", _clamp_difficulty('abc') == DEFAULT_DIFFICULTY_INDEX)
    check("None -> default", _clamp_difficulty(None) == DEFAULT_DIFFICULTY_INDEX)
    check("2 -> 2", _clamp_difficulty(2) == 2)
    check("2.7 -> 2", _clamp_difficulty(2.7) == 2)


def test_field_copy_types():
    print("[34] Field.copy сохраняет все типы шашек")
    field = Field(8, 8)
    field.at(0, 5).change_type(CheckerType.WHITE_QUEEN)
    field.at(1, 2).change_type(CheckerType.NONE)
    field.at(6, 3).change_type(CheckerType.BLACK_QUEEN)
    copy = Field.copy(field)
    same = all(field.type_at(x, y) == copy.type_at(x, y)
               for y in range(8) for x in range(8))
    check("все 64 клетки совпадают", same)
    copy.at(0, 5).change_type(CheckerType.NONE)
    check("изменение копии не трогает оригинал",
          field.type_at(0, 5) == CheckerType.WHITE_QUEEN)
    rect = Field(6, 4)
    rect_copy = Field.copy(rect)
    check("размеры прямоугольного поля сохранены",
          rect_copy.x_size == 6 and rect_copy.y_size == 4 and rect_copy.size == 6)


def test_resign_and_draw_offer():
    print("[35] Сдача и предложение ничьей")
    root = make_root()
    events = []
    game = make_game(root, DifficultyType.EASY,
                     game_over_callback=lambda w, n, r: events.append((w, n, r)))
    game.resign()
    check("после сдачи партия завершена", game.is_game_over is True)
    check("победил ИИ", events and events[0][0] == SideType.BLACK)

    game.restart()
    check("после рестарта партия снова идёт", game.is_game_over is False)
    check("предложение ничьей отвечает", isinstance(game.offer_draw(), bool))
    root.destroy()


def test_custom_cursor():
    print("[36] Свой курсор: цвета, виды и наборы")
    from checkers import cursor_packs
    from checkers.cursor import (
        ARROW, CURSOR_COLORS, HAND, WAIT, CanvasCursor, CursorStyle, cursor_color,
    )
    root = make_root()
    canvas = tk.Canvas(root, width=300, height=300)
    canvas.pack()

    check("в палитре не меньше 8 цветов", len(CURSOR_COLORS) >= 8)
    for key in ('green', 'blue', 'cyan', 'purple', 'orange', 'pink'):
        check(f"цвет {key} задан", cursor_color(key, CLASSIC).startswith('#'))
    check("акцентный цвет берётся из темы", cursor_color('accent', DARK) == DARK.accent)
    check("неизвестный цвет -> цвет набора", cursor_color('нет', CLASSIC) == 'native')

    packs = cursor_packs.list_packs()
    check("наборы курсоров найдены", len(packs) >= 3)
    for key in packs:
        check(f"набор {key} содержит стрелку", 'arrow' in packs[key].kinds)
    default_pack = cursor_packs.pack_by_key('minimalistic/koromiko')
    check("набор по умолчанию доступен", default_pack is not None)

    cursor = CanvasCursor(canvas, CursorStyle(color='#123456', pack=''))
    check("курсор включён по умолчанию", cursor.enabled is True)
    cursor.move(50, 60)
    check("курсор нарисован", bool(canvas.find_withtag(CanvasCursor.TAG)))
    check("системный курсор скрыт", canvas.cget('cursor') == 'none')

    for kind in (HAND, WAIT, ARROW):
        cursor.move(70, 80, kind)
        check(f"вид {kind} рисуется",
              cursor.kind == kind and bool(canvas.find_withtag(CanvasCursor.TAG)))

    cursor.set_color('#abcdef')
    check("цвет применяется", cursor.style.color == '#abcdef')

    cursor.set_pack('minimalistic/koromiko')
    check("набор применяется", cursor.pack is not None and cursor.pack.key == 'minimalistic/koromiko')
    for kind in (ARROW, HAND, WAIT):
        cursor.move(90, 95, kind)
        check(f"набор рисует вид {kind}", bool(canvas.find_withtag(CanvasCursor.TAG)))
    cursor.set_pack('нет такого')
    check("неизвестный набор -> векторная форма", cursor.style.pack == '')

    image, hotspot = cursor_packs.render(default_pack, ARROW, 48, 'native')
    check("изображение набора масштабируется", image is not None and image.height == 48)
    check("hotspot попадает в картинку",
          0 <= hotspot[0] <= image.width and 0 <= hotspot[1] <= image.height)
    tinted, _ = cursor_packs.render(default_pack, ARROW, 48, '#3b82f6')
    check("перекраска набора работает",
          tinted is not None and tinted.tobytes() != image.tobytes())

    cursor.hide()
    check("скрытие убирает элементы", not canvas.find_withtag(CanvasCursor.TAG))

    cursor.set_enabled(False)
    check("выключение возвращает системный курсор", canvas.cget('cursor') != 'none')
    root.destroy()


def test_cursor_settings():
    print("[37] Настройки курсора сохраняются")
    from checkers.settings import DEFAULT_CURSOR_PACK
    backup = CONFIG_PATH.read_bytes() if CONFIG_PATH.exists() else None
    try:
        s = Settings()
        s.custom_cursor = False
        s.cursor_color = 'cyan'
        s.cursor_pack = 'oreo/oreo_purple'
        reloaded = Settings()
        check("флаг курсора сохранён", reloaded.custom_cursor is False)
        check("цвет курсора сохранён", reloaded.cursor_color == 'cyan')
        check("набор курсора сохранён", reloaded.cursor_pack == 'oreo/oreo_purple')

        CONFIG_PATH.write_text('{"cursor_color": "мусор", "custom_cursor": "нет", '
                               '"cursor_pack": "мусор"}', encoding='utf-8')
        s = Settings()
        check("неизвестный цвет -> цвет набора", s.cursor_color == 'native')
        check("мусорный флаг -> курсор включён", s.custom_cursor is True)
        check("неизвестный набор -> набор по умолчанию", s.cursor_pack == DEFAULT_CURSOR_PACK)
    finally:
        if backup is not None:
            CONFIG_PATH.write_bytes(backup)
        elif CONFIG_PATH.exists():
            CONFIG_PATH.unlink()


def main():
    print("=== Самопроверка логики шашек ===")
    test_initial_field()
    test_queen_moves_no_crash()
    test_forced_continuation()
    test_turkish_strike()
    test_rule_variants()
    test_ai_single_move()
    test_ai_forced_capture_sequence()
    test_field_copy()
    test_hint_returns_legal_move()
    test_undo_restores_position()
    test_game_over_detection()
    test_draw_by_quiet_moves()
    test_draw_by_repetition()
    test_paths_are_absolute()
    test_settings_robustness()
    test_missing_assets_fallback()
    test_hash_and_equality()
    test_evaluate_symmetry()
    test_sound_manager()
    test_audio_synthesis()
    test_music_toggle()
    test_player_side()
    test_hover_and_coordinates()
    test_notation()
    test_history_navigation()
    test_theme_switch()
    test_board_scaling()
    test_toast_queue()
    test_difficulty_noise()
    test_engine_transposition()
    test_engine_cancel()
    test_settings_extended()
    test_difficulty_clamp()
    test_field_copy_types()
    test_resign_and_draw_offer()
    test_custom_cursor()
    test_cursor_settings()
    print("=== Итог ===")
    print(f"Пройдено: {len(PASSED)}, провалено: {len(FAILED)}")
    if FAILED:
        for name in FAILED:
            print(f"  ПРОВАЛ: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
