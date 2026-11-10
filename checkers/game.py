"""Игровой процесс: состояние партии, отрисовка доски, история и ИИ.

Game не знает о конкретном окне: всё общение с интерфейсом идёт через
колбэки (обновление статуса, тосты, конец партии). Поэтому класс можно
проверять в selfcheck без показа окна.

Доска масштабируется под размер окна, рисуется в цветах выбранной темы,
может переворачиваться и подписывается координатами a–h/1–8. Каждая
позиция сохраняется в историю, поэтому партию можно листать.
"""
import threading
from dataclasses import dataclass
from time import sleep
from tkinter import Canvas, Event, messagebox

from PIL import Image, ImageTk
from PIL.Image import LANCZOS as ANTIALIAS

from checkers import rules as R
from checkers.audio import SoundManager
from checkers.constants import (
    BORDER_WIDTH,
    DEFAULT_DIFFICULTY,
    PLAYER_SIDE,
    WHITE_CHECKERS,
)
from checkers.engine import Engine, evaluate_field
from checkers.enums import CheckerType, DifficultyType, SideType
from checkers.field import Field
from checkers.move import Move
from checkers.notation import chain_notation, square_name
from checkers.paths import asset_path
from checkers.point import Point
from checkers.theme import DEFAULT_THEME, Theme

# Минимальный и максимальный размер клетки при масштабировании
MIN_CELL = 26
MAX_CELL = 132
# Доля клетки, отводимая под координаты вокруг доски
PADDING_RATIO = 0.45


@dataclass
class Snapshot:
    '''Позиция в истории партии'''

    field: Field
    player_turn: bool
    chain: bool
    notation: str
    is_capture: bool
    last_move: object
    quiet: int


class Game:
    def __init__(
        self,
        canvas: Canvas,
        x_field_size: int,
        y_field_size: int,
        difficulty: DifficultyType = DEFAULT_DIFFICULTY,
        update_callback=None,
        sounds_enabled: bool = True,
        player_side: SideType = PLAYER_SIDE,
        auto_restart: bool = True,
        game_over_callback=None,
        theme: Theme = DEFAULT_THEME,
        rules: R.RuleSet = R.DEFAULT_RULES,
        toast_callback=None,
        animate: bool = True,
    ):
        self.__canvas = canvas
        self.__field = Field(x_field_size, y_field_size)
        self.__difficulty = difficulty
        self.__rules = rules
        self.__theme = theme
        self.__update_callback = update_callback
        self.__game_over_callback = game_over_callback
        self.__toast_callback = toast_callback
        self.__animate = animate

        self.__player_side = player_side
        self.__view_side = player_side
        self.__auto_restart = auto_restart

        self.__game_over = False
        self.__game_over_reason = ''
        self.__move_count = 0
        self.__enemy_pending = False

        self.__player_turn = True

        self.__hovered_cell = Point()
        self.__selected_cell = Point()
        self.__animated_cell = Point()
        self.__last_move = None
        self.__hint_move = None
        self.__show_hover_hints = True
        self.__show_coordinates = True

        # Шашка, которой обязательно продолжать серию взятий (None, если серии нет)
        self.__must_continue_from = None
        # Побитые шашки, ещё стоящие на доске (турецкий удар)
        self.__pending_captures: list[Point] = []
        # Ноги текущей серии взятий и её признаки
        self.__chain_legs: list[Move] = []
        self.__chain_captured = 0
        self.__chain_was_queen = False

        # История позиций и указатель просмотра
        self.__positions: list[Snapshot] = []
        self.__index = 0
        self.__repetitions: dict[tuple, int] = {}
        self.__quiet_halfmoves = 0

        # Фоновый расчёт ИИ
        self.__thinking = False
        self.__think_thread = None
        self.__cancel_event = None
        self.__think_result = None
        self.__search_progress = None

        self.__sound_manager = SoundManager()
        self.__sound_manager.set_enabled(sounds_enabled)

        # Размер клетки и отступы под координаты
        self.__cell = 75
        self.__padding = int(self.__cell * PADDING_RATIO)
        self.__image_cache: dict[tuple, object] = {}

        self.__record_initial()
        self.__draw()

        # Если игрок играет за чёрных, то первым ходит ИИ
        if self.__player_side == SideType.BLACK:
            self.__schedule_enemy_turn()

    # --- Геометрия доски -----------------------------------------------------

    @property
    def cell_size(self) -> int:
        '''Текущий размер клетки в пикселях'''
        return self.__cell

    @property
    def padding(self) -> int:
        '''Отступ вокруг доски под координаты'''
        return self.__padding

    @property
    def board_width(self) -> int:
        '''Ширина доски с координатами'''
        return self.__field.x_size * self.__cell + 2 * self.__padding

    @property
    def board_height(self) -> int:
        '''Высота доски с координатами'''
        return self.__field.y_size * self.__cell + 2 * self.__padding

    def resize(self, width: int, height: int):
        '''Подобрать размер клетки под доступную область и перерисовать доску'''
        if width <= 0 or height <= 0:
            return
        cell_x = width / (self.__field.x_size + 2 * PADDING_RATIO)
        cell_y = height / (self.__field.y_size + 2 * PADDING_RATIO)
        cell = int(max(MIN_CELL, min(MAX_CELL, min(cell_x, cell_y))))
        padding = int(cell * PADDING_RATIO)
        if cell == self.__cell and padding == self.__padding:
            return
        self.__cell = cell
        self.__padding = padding
        self.__canvas.config(width=self.board_width, height=self.board_height)
        self.__draw()

    def __screen_cell(self, x: int, y: int) -> tuple[int, int]:
        '''Координаты клетки доски в координатах экрана'''
        if self.__view_side == SideType.WHITE:
            return x, y
        return self.__field.x_size - 1 - x, self.__field.y_size - 1 - y

    def __cell_from_pixel(self, px: int, py: int) -> Point:
        '''Клетка доски под точкой холста (Point() если вне доски)'''
        sx = int((px - self.__padding) // self.__cell)
        sy = int((py - self.__padding) // self.__cell)
        if not (0 <= sx < self.__field.x_size and 0 <= sy < self.__field.y_size):
            return Point()
        x, y = self.__board_cell(sx, sy)
        return Point(x, y)

    def __board_cell(self, sx: int, sy: int) -> tuple[int, int]:
        '''Клетка доски по координатам экрана'''
        if self.__view_side == SideType.WHITE:
            return sx, sy
        return self.__field.x_size - 1 - sx, self.__field.y_size - 1 - sy

    def __cell_box(self, sx: int, sy: int) -> tuple[float, float, float, float]:
        '''Пиксельные границы клетки экрана'''
        x1 = self.__padding + sx * self.__cell
        y1 = self.__padding + sy * self.__cell
        return x1, y1, x1 + self.__cell, y1 + self.__cell

    # --- Отрисовка -----------------------------------------------------------

    def __checker_image(self, checker_type: CheckerType):
        '''Изображение шашки, отмасштабированное под текущую клетку'''
        key = (checker_type, self.__cell)
        if key in self.__image_cache:
            return self.__image_cache[key]

        files = {
            CheckerType.WHITE_REGULAR: 'white-regular.png',
            CheckerType.BLACK_REGULAR: 'black-regular.png',
            CheckerType.WHITE_QUEEN: 'white-queen.png',
            CheckerType.BLACK_QUEEN: 'black-queen.png',
        }
        filename = files.get(checker_type)
        image = None
        if filename:
            try:
                source = Image.open(asset_path(filename))
                image = ImageTk.PhotoImage(source.resize((self.__cell, self.__cell), ANTIALIAS))
            except (OSError, ValueError):
                # Файл отсутствует или повреждён — шашка будет нарисована заглушкой
                image = None
        self.__image_cache[key] = image
        return image

    def __draw_checker_at(self, sx: int, sy: int, checker_type: CheckerType, tag: str):
        '''Нарисовать шашку: изображением или запасным кружком'''
        x1, y1, x2, y2 = self.__cell_box(sx, sy)
        image = self.__checker_image(checker_type)
        if image is not None:
            self.__canvas.create_image(x1, y1, image=image, anchor='nw', tag=tag)
            return

        is_white = checker_type in WHITE_CHECKERS
        inset = self.__cell * 0.15
        self.__canvas.create_oval(
            x1 + inset, y1 + inset, x2 - inset, y2 - inset,
            fill=self.__theme.white_piece if is_white else self.__theme.black_piece,
            outline=self.__theme.panel_fg if is_white else self.__theme.panel_bg,
            width=BORDER_WIDTH, tag=tag,
        )

    def __draw(self):
        '''Полная перерисовка доски'''
        self.__canvas.delete('all')
        self.__canvas.config(bg=self.__theme.canvas_bg)
        self.__canvas.create_rectangle(
            0, 0, self.board_width, self.board_height,
            fill=self.__theme.canvas_bg, width=0, tag='background',
        )
        self.__draw_field_grid()
        if self.__show_coordinates:
            self.__draw_coordinates()
        self.__draw_checkers()
        self.__notify_update()

    def __draw_field_grid(self):
        '''Сетка доски и вся подсветка клеток'''
        player_moves = self.__get_available_moves(self.__player_side) if self.__selected_cell else []
        hovered_moves = (
            self.__get_hovered_cell_moves()
            if (self.__show_hover_hints and self.__player_turn and not self.__selected_cell
                and not self.is_browsing)
            else []
        )
        selected_moves = [
            move for move in player_moves
            if self.__selected_cell.x == move.from_x and self.__selected_cell.y == move.from_y
        ]

        theme = self.__theme
        for y in range(self.__field.y_size):
            for x in range(self.__field.x_size):
                sx, sy = self.__screen_cell(x, y)
                x1, y1, x2, y2 = self.__cell_box(sx, sy)
                color = theme.board_light if (x + y) % 2 == 0 else theme.board_dark
                self.__canvas.create_rectangle(x1, y1, x2, y2, fill=color, width=0, tag='boards')

                inner = (x1 + BORDER_WIDTH // 2, y1 + BORDER_WIDTH // 2,
                         x2 - BORDER_WIDTH // 2, y2 - BORDER_WIDTH // 2)

                if x == self.__selected_cell.x and y == self.__selected_cell.y:
                    self.__canvas.create_rectangle(*inner, outline=theme.select_border,
                                                   width=BORDER_WIDTH, tag='border')
                elif x == self.__hovered_cell.x and y == self.__hovered_cell.y:
                    self.__canvas.create_rectangle(*inner, outline=theme.hover_border,
                                                   width=BORDER_WIDTH, tag='border')

                if self.__last_move and (
                    (x == self.__last_move.from_x and y == self.__last_move.from_y)
                    or (x == self.__last_move.to_x and y == self.__last_move.to_y)
                ):
                    self.__canvas.create_rectangle(*inner, outline=theme.last_move,
                                                   width=BORDER_WIDTH, tag='last_move_border')

                for move in selected_moves:
                    if x == move.to_x and y == move.to_y:
                        radius = self.__cell / 3
                        cx, cy = x1 + self.__cell / 2, y1 + self.__cell / 2
                        self.__canvas.create_oval(
                            cx - radius, cy - radius, cx + radius, cy + radius,
                            fill=theme.move_dot, width=0, tag='posible_move_circle',
                        )

                for move in hovered_moves:
                    if x == move.to_x and y == move.to_y:
                        self.__canvas.create_rectangle(
                            x1, y1, x2, y2, fill=theme.hover_target,
                            stipple='gray50', width=0, tag='hovered_move_highlight',
                        )

                if self.__hint_move:
                    if x == self.__hint_move.from_x and y == self.__hint_move.from_y:
                        self.__canvas.create_rectangle(
                            x1, y1, x2, y2, fill=theme.hint_from,
                            stipple='gray50', width=0, tag='hint_highlight',
                        )
                    if x == self.__hint_move.to_x and y == self.__hint_move.to_y:
                        self.__canvas.create_rectangle(
                            x1, y1, x2, y2, fill=theme.hint_to,
                            stipple='gray50', width=0, tag='hint_highlight',
                        )

    def __draw_coordinates(self):
        '''Подписи файлов и рангов вокруг доски.

        Имена клеток не зависят от того, с чьей стороны смотрят на доску:
        при перевороте подписи просто переезжают вместе с колонками.
        '''
        theme = self.__theme
        font = ('Segoe UI', max(7, int(self.__cell * 0.2)))
        bottom = self.__padding + self.__field.y_size * self.__cell
        left = self.__padding

        for sx in range(self.__field.x_size):
            board_x, _ = self.__board_cell(sx, 0)
            label = square_name(board_x, 0, self.__field.x_size, self.__field.y_size)[0]
            cx = self.__padding + sx * self.__cell + self.__cell / 2
            self.__canvas.create_text(cx, bottom + self.__padding / 2, text=label,
                                      fill=theme.coordinate, font=font, tag='coordinates')

        for sy in range(self.__field.y_size):
            _, board_y = self.__board_cell(0, sy)
            label = square_name(0, board_y, self.__field.x_size, self.__field.y_size)[1]
            cy = self.__padding + sy * self.__cell + self.__cell / 2
            self.__canvas.create_text(left - self.__padding / 2, cy, text=label,
                                      fill=theme.coordinate, font=font, anchor='e',
                                      tag='coordinates')

    def __draw_checkers(self):
        '''Отрисовка шашек'''
        for y in range(self.__field.y_size):
            for x in range(self.__field.x_size):
                checker_type = self.__field.type_at(x, y)
                if checker_type == CheckerType.NONE:
                    continue
                if x == self.__animated_cell.x and y == self.__animated_cell.y:
                    continue
                sx, sy = self.__screen_cell(x, y)
                self.__draw_checker_at(sx, sy, checker_type, 'checkers')

    # --- Анимация ------------------------------------------------------------

    def __animate_move(self, move: Move):
        '''Плавное перемещение шашки'''
        if not self.__animate:
            return

        self.__animated_cell = Point(move.from_x, move.from_y)
        self.__draw()

        checker_type = self.__field.type_at(move.from_x, move.from_y)
        from_sx, from_sy = self.__screen_cell(move.from_x, move.from_y)
        to_sx, to_sy = self.__screen_cell(move.to_x, move.to_y)
        start_x, start_y = self.__padding + from_sx * self.__cell, self.__padding + from_sy * self.__cell
        end_x, end_y = self.__padding + to_sx * self.__cell, self.__padding + to_sy * self.__cell

        image = self.__checker_image(checker_type)
        if image is not None:
            item = self.__canvas.create_image(start_x, start_y, image=image, anchor='nw',
                                              tag='animated_checker')
        else:
            inset = self.__cell * 0.15
            item = self.__canvas.create_oval(
                start_x + inset, start_y + inset,
                start_x + self.__cell - inset, start_y + self.__cell - inset,
                fill=self.__theme.white_piece if checker_type in WHITE_CHECKERS else self.__theme.black_piece,
                outline=self.__theme.panel_fg, width=BORDER_WIDTH, tag='animated_checker',
            )

        steps = 8
        for step in range(1, steps + 1):
            ratio = step / steps
            self.__canvas.coords(
                item,
                start_x + (end_x - start_x) * ratio,
                start_y + (end_y - start_y) * ratio,
            ) if image is None else self.__canvas.coords(
                item,
                start_x + (end_x - start_x) * ratio,
                start_y + (end_y - start_y) * ratio,
            )
            self.__canvas.update()
            sleep(0.012)

        self.__canvas.delete(item)
        self.__animated_cell = Point()

    def __animate_captures(self, points: list[Point]):
        '''Сжатие и исчезновение побитых шашек'''
        if not self.__animate or not points:
            return

        items = []
        for point in points:
            sx, sy = self.__screen_cell(point.x, point.y)
            x1, y1, x2, y2 = self.__cell_box(sx, sy)
            inset = self.__cell * 0.15
            items.append((x1 + inset, y1 + inset, x2 - inset, y2 - inset))

        frames = 5
        for frame in range(1, frames + 1):
            ratio = 1 - frame / frames * 0.8
            self.__canvas.delete('capture_fade')
            for box in items:
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                half_w = (box[2] - box[0]) / 2 * ratio
                half_h = (box[3] - box[1]) / 2 * ratio
                self.__canvas.create_oval(
                    cx - half_w, cy - half_h, cx + half_w, cy + half_h,
                    fill=self.__theme.canvas_bg, outline='', stipple='gray50',
                    width=0, tag='capture_fade',
                )
            self.__canvas.update()
            sleep(0.018)
        self.__canvas.delete('capture_fade')

    # --- Мышь ----------------------------------------------------------------

    def mouse_move(self, event: Event):
        '''Событие перемещения мыши'''
        point = self.__cell_from_pixel(event.x, event.y)
        if point.x != self.__hovered_cell.x or point.y != self.__hovered_cell.y:
            self.__hovered_cell = point
            if self.__player_turn and not self.is_browsing:
                self.__draw()

    def __get_hovered_cell_moves(self) -> list[Move]:
        '''Ходы шашки под курсором'''
        if not self.__field.is_within(self.__hovered_cell.x, self.__hovered_cell.y):
            return []
        if self.__field.type_at(self.__hovered_cell.x, self.__hovered_cell.y) not in R.friendly_checkers(self.__player_side):
            return []
        moves = self.__get_available_moves(self.__player_side)
        return [move for move in moves
                if move.from_x == self.__hovered_cell.x and move.from_y == self.__hovered_cell.y]

    def mouse_down(self, event: Event):
        '''Событие нажатия мыши'''
        if self.is_browsing:
            self.__toast('Идёт просмотр истории: вернитесь к текущей позиции', 'warn')
            return
        if not self.__player_turn or self.__game_over or self.__thinking:
            return

        point = self.__cell_from_pixel(event.x, event.y)
        if not self.__field.is_within(point.x, point.y):
            return

        if self.__hint_move:
            self.hide_hint()

        x, y = point.x, point.y
        if self.__field.type_at(x, y) in R.friendly_checkers(self.__player_side):
            if self.__must_continue_from and (x != self.__must_continue_from.x or y != self.__must_continue_from.y):
                return
            self.__selected_cell = Point(x, y)
            self.__last_move = None
            self.__draw()
            return

        move = Move(self.__selected_cell.x, self.__selected_cell.y, x, y)
        if move in self.__get_available_moves(self.__player_side):
            self.__handle_player_turn(move)
            if not self.__player_turn and not self.__game_over:
                self.__schedule_enemy_turn()

    # --- Ходы ----------------------------------------------------------------

    def __defer_captures(self) -> bool:
        '''Снимать побитые шашки только после завершения серии'''
        return self.__rules.turkish_strike

    def __handle_move(self, move: Move, draw: bool = True) -> tuple[list[Point], bool]:
        '''Совершить ход. Возвращает (побитые шашки, превращение в дамку)'''
        if draw:
            self.__animate_move(move)

        captured = R.capture_points(self.__field, move)
        moving_type = self.__field.type_at(move.from_x, move.from_y)
        side = SideType.WHITE if moving_type in WHITE_CHECKERS else SideType.BLACK

        is_queen_promotion = False
        if not R.is_queen(moving_type) and R.promotes(side, move.to_y, self.__field.y_size):
            moving_type = R.queen_type(side)
            is_queen_promotion = True

        if self.__defer_captures():
            self.__pending_captures.extend(captured)
        else:
            for point in captured:
                self.__field.at(point.x, point.y).change_type(CheckerType.NONE)

        self.__field.at(move.to_x, move.to_y).change_type(moving_type)
        self.__field.at(move.from_x, move.from_y).change_type(CheckerType.NONE)

        self.__chain_captured += len(captured)
        if R.is_queen(self.__field.type_at(move.to_x, move.to_y)):
            self.__chain_was_queen = True

        if draw:
            self.__move_count += 1
            if is_queen_promotion:
                self.__sound_manager.play('queen')
            elif captured:
                self.__sound_manager.play('capture')
            else:
                self.__sound_manager.play('move')
            self.__last_move = move
            if not self.__defer_captures() and captured:
                self.__animate_captures(captured)
            self.__draw()

        return captured, is_queen_promotion

    def __flush_captures(self):
        '''Снять отложенные (турецкий удар) побитые шашки'''
        if not self.__pending_captures:
            return
        self.__animate_captures(self.__pending_captures)
        for point in self.__pending_captures:
            if self.__field.is_within(point.x, point.y):
                self.__field.at(point.x, point.y).change_type(CheckerType.NONE)
        self.__pending_captures = []

    def __masked_moves(self, side: SideType) -> list[Move]:
        '''Ходы с учётом отложенных побитых шашек'''
        if not self.__pending_captures:
            moves = R.moves_for_side(self.__field, side, self.__rules)
        else:
            saved = [(point, self.__field.type_at(point.x, point.y))
                     for point in self.__pending_captures]
            for point, _ in saved:
                self.__field.at(point.x, point.y).change_type(CheckerType.NONE)
            try:
                moves = R.moves_for_side(self.__field, side, self.__rules)
            finally:
                for point, checker_type in saved:
                    self.__field.at(point.x, point.y).change_type(checker_type)
            # Нельзя приземляться на клетку уже побитой шашки
            moves = [move for move in moves
                     if not any(move.to_x == point.x and move.to_y == point.y
                                for point in self.__pending_captures)]

        if self.__must_continue_from:
            moves = [move for move in moves
                     if move.from_x == self.__must_continue_from.x
                     and move.from_y == self.__must_continue_from.y]
        return moves

    def __can_continue(self, move: Move, captured: list[Point], promoted: bool,
                       side: SideType) -> bool:
        '''Может ли шашка продолжить серию взятий'''
        if not captured:
            return False
        if promoted and self.__rules.promote_ends_chain:
            return False
        previous = self.__must_continue_from
        self.__must_continue_from = Point(move.to_x, move.to_y)
        try:
            continuations = [m for m in self.__masked_moves(side) if len(R.capture_points(self.__field, m)) > 0]
        finally:
            self.__must_continue_from = previous
        return bool(continuations)

    def __handle_player_turn(self, move: Move):
        '''Обработка хода игрока'''
        self.__player_turn = False
        captured, promoted = self.__handle_move(move)
        self.__selected_cell = Point()
        self.__chain_legs.append(move)

        if self.__can_continue(move, captured, promoted, self.__player_side):
            self.__must_continue_from = Point(move.to_x, move.to_y)
            self.__selected_cell = Point(move.to_x, move.to_y)
            self.__player_turn = True
            self.__record(self.__chain_notation(True), True)
            self.__draw()
            return

        self.__end_chain(self.__player_side)

    def __end_chain(self, side: SideType):
        '''Завершить серию: снять побитые шашки, записать позицию, проверить ничью'''
        was_capture = self.__chain_captured > 0
        self.__must_continue_from = None
        self.__flush_captures()

        if was_capture or self.__chain_was_queen:
            self.__quiet_halfmoves = 0
        else:
            self.__quiet_halfmoves += 1

        self.__record(self.__chain_notation(was_capture), was_capture)
        self.__chain_legs.clear()
        self.__chain_captured = 0
        self.__chain_was_queen = False

        if not self.__game_over:
            self.__check_draw()
        self.__draw()

    def __chain_notation(self, is_capture: bool) -> str:
        '''Нотация текущей серии ходов'''
        if not self.__chain_legs:
            return ''
        return chain_notation(self.__chain_legs, self.__field.x_size, self.__field.y_size,
                              self.__view_side, is_capture)

    def __handle_enemy_turn(self):
        '''Ход ИИ целиком (синхронно, без фонового расчёта)'''
        side = SideType.opposite(self.__player_side)
        self.__player_turn = False

        if not self.__masked_moves(side):
            self.__finish_game(side, 'У ИИ нет ходов')
            return

        while True:
            moves = self.__masked_moves(side)
            if not moves:
                break
            move = self.__predict_optimal_move(side, moves)
            if move is None:
                break

            captured, promoted = self.__handle_move(move)
            self.__chain_legs.append(move)

            if self.__can_continue(move, captured, promoted, side):
                self.__must_continue_from = Point(move.to_x, move.to_y)
                self.__record(self.__chain_notation(True), True)
                continue

            self.__end_chain(side)
            break

        self.__player_turn = True
        if not self.__masked_moves(self.__player_side):
            self.__finish_game(self.__player_side, 'У игрока нет ходов')
            return
        self.__notify_update()

    # --- Фоновый расчёт ИИ ---------------------------------------------------

    def __schedule_enemy_turn(self):
        '''Поставить ход ИИ в очередь, дав интерфейсу показать статус'''
        if self.__enemy_pending or self.__game_over:
            return
        self.__enemy_pending = True
        self.__player_turn = False
        self.__notify_update()

        def run():
            self.__enemy_pending = False
            if self.__game_over:
                return
            self.__start_thinking()

        try:
            self.__canvas.after(10, run)
        except Exception:
            # Холст уже уничтожен — ход не нужен
            self.__enemy_pending = False

    def __start_thinking(self):
        '''Запустить расчёт хода ИИ в отдельном потоке'''
        side = SideType.opposite(self.__player_side)
        moves = self.__masked_moves(side)
        if not moves:
            self.__player_turn = True
            self.__finish_game(side, 'У ИИ нет ходов')
            return

        self.__thinking = True
        self.__search_progress = None
        self.__think_result = None
        self.__cancel_event = threading.Event()
        cancel = self.__cancel_event
        field_copy = Field.copy(self.__field)
        rules = self.__rules
        difficulty = self.__difficulty

        def progress(depth, max_depth, move, score):
            self.__search_progress = (depth, max_depth, move, score)

        def work():
            engine = Engine(rules, difficulty.depth, difficulty.time_limit,
                            difficulty.noise_scale, cancel, progress)
            self.__think_result = engine.search(field_copy, side, root_moves=moves)

        self.__think_thread = threading.Thread(target=work, daemon=True, name='checkers-ai')
        self.__think_thread.start()
        self.__notify_update()
        self.__poll_thinking()

    def __poll_thinking(self):
        '''Ожидание готовности ИИ без блокировки интерфейса'''
        if not self.__thinking:
            return

        thread = self.__think_thread
        if thread is not None and thread.is_alive():
            self.__notify_update()
            try:
                self.__canvas.after(60, self.__poll_thinking)
            except Exception:
                self.__thinking = False
            return

        self.__thinking = False
        result = self.__think_result
        self.__think_thread = None
        self.__cancel_event = None
        self.__search_progress = None

        move = result.move if result is not None else None
        if move is None:
            self.__player_turn = True
            self.__notify_update()
            return
        self.__apply_ai_move(move)

    def __apply_ai_move(self, move: Move):
        '''Применить найденный ИИ ход и продолжить серию при необходимости'''
        side = SideType.opposite(self.__player_side)
        self.__player_turn = False
        captured, promoted = self.__handle_move(move)
        self.__chain_legs.append(move)

        if self.__can_continue(move, captured, promoted, side):
            self.__must_continue_from = Point(move.to_x, move.to_y)
            self.__record(self.__chain_notation(True), True)
            self.__draw()
            self.__schedule_enemy_turn()
            return

        self.__end_chain(side)
        self.__player_turn = True
        if not self.__masked_moves(self.__player_side):
            self.__finish_game(self.__player_side, 'У игрока нет ходов')
            return
        self.__notify_update()

    def cancel_thinking(self):
        '''Прервать расчёт: ИИ сыграет лучший найденный ход'''
        if self.__cancel_event is not None:
            self.__cancel_event.set()

    @property
    def is_thinking(self) -> bool:
        '''ИИ считает ход'''
        return self.__thinking

    @property
    def search_progress(self):
        '''Прогресс расчёта: (глубина, максимум, ход, оценка) или None'''
        return self.__search_progress

    # --- Конец партии и ничья ------------------------------------------------

    def __finish_game(self, loser_side, reason: str = ''):
        '''Завершить партию. loser_side=None означает ничью'''
        self.__game_over = True
        self.__player_turn = False
        self.__game_over_reason = reason
        self.__selected_cell = Point()
        self.__hovered_cell = Point()
        self.__must_continue_from = None
        self.__hint_move = None
        self.__draw()

        if loser_side is None:
            winner_name = 'Ничья'
            self.__sound_manager.play('draw')
        else:
            winner_side = SideType.opposite(loser_side)
            winner_name = 'Белые' if winner_side == SideType.WHITE else 'Чёрные'
            self.__sound_manager.play('win' if winner_side == self.__player_side else 'lose')

        if self.__game_over_callback:
            self.__game_over_callback(None if loser_side is None else SideType.opposite(loser_side),
                                      winner_name, reason)
        elif self.__auto_restart:
            messagebox.showinfo('Конец игры', f'{winner_name}. {reason}')
            self.restart()

    def __check_draw(self):
        '''Проверить условия ничьей по правилам'''
        limit = self.__rules.repetition_limit
        if limit and self.__repetitions.get(self.__position_key(), 0) >= limit:
            self.__finish_game(None, 'Троекратное повторение позиции')
            return
        quiet_limit = self.__rules.draw_quiet_halfmoves
        if quiet_limit and self.__quiet_halfmoves >= quiet_limit:
            self.__finish_game(None, f'{quiet_limit // 2} ходов без взятий и движения дамок')

    def resign(self):
        '''Сдаться'''
        if self.__game_over:
            return
        self.__finish_game(self.__player_side, 'Вы сдались')

    def offer_draw(self) -> bool:
        '''Предложить ничью: ИИ соглашается на равной позиции'''
        if self.__game_over or self.is_browsing:
            return False
        score = evaluate_field(self.__field, SideType.opposite(self.__player_side))
        if abs(score) <= 0.4:
            self.__finish_game(None, 'Ничья по согласию')
            return True
        self.__toast('ИИ отклонил ничью: позиция не равна', 'warn')
        return False

    def restart(self):
        '''Начать новую партию с теми же настройками'''
        self.__field = Field(self.__field.x_size, self.__field.y_size)
        self.__player_turn = True
        self.__hovered_cell = Point()
        self.__selected_cell = Point()
        self.__animated_cell = Point()
        self.__must_continue_from = None
        self.__last_move = None
        self.__hint_move = None
        self.__game_over = False
        self.__game_over_reason = ''
        self.__move_count = 0
        self.__enemy_pending = False
        self.__pending_captures = []
        self.__chain_legs = []
        self.__chain_captured = 0
        self.__chain_was_queen = False
        self.__quiet_halfmoves = 0
        self.__repetitions = {}
        self.__positions = []
        self.__index = 0
        self.__cancel_thinking_silently()
        self.__record_initial()
        self.__draw()

        if self.__player_side == SideType.BLACK:
            self.__schedule_enemy_turn()

    def __cancel_thinking_silently(self):
        if self.__cancel_event is not None:
            self.__cancel_event.set()
        self.__thinking = False
        self.__think_thread = None
        self.__cancel_event = None
        self.__think_result = None
        self.__search_progress = None

    # --- История позиций -----------------------------------------------------

    def __position_key(self) -> tuple:
        '''Ключ позиции вместе с очередью хода'''
        return (R.position_key(self.__field), self.__player_turn)

    def __record_initial(self):
        snapshot = Snapshot(
            field=Field.copy(self.__field),
            player_turn=self.__player_turn,
            chain=False,
            notation='Начальная позиция',
            is_capture=False,
            last_move=None,
            quiet=0,
        )
        self.__positions = [snapshot]
        self.__index = 0
        self.__repetitions = {self.__position_key(): 1}

    def __record(self, notation: str, is_capture: bool):
        '''Добавить текущую позицию в историю'''
        # Ветка после отката назад отбрасывается
        self.__positions = self.__positions[:self.__index + 1]
        self.__positions.append(Snapshot(
            field=Field.copy(self.__field),
            player_turn=self.__player_turn,
            chain=bool(self.__must_continue_from),
            notation=notation,
            is_capture=is_capture,
            last_move=self.__last_move,
            quiet=self.__quiet_halfmoves,
        ))
        self.__index = len(self.__positions) - 1
        key = self.__position_key()
        self.__repetitions[key] = self.__repetitions.get(key, 0) + 1

    @property
    def history_entries(self) -> list[dict]:
        '''История ходов для панели интерфейса'''
        entries = []
        for index, snapshot in enumerate(self.__positions):
            if index == 0:
                continue
            entries.append({
                'index': index,
                'number': index,
                'notation': snapshot.notation,
                'capture': snapshot.is_capture,
                'player_turn': snapshot.player_turn,
            })
        return entries

    @property
    def current_index(self) -> int:
        '''Индекс показанной позиции'''
        return self.__index

    @property
    def positions_count(self) -> int:
        '''Количество позиций в истории'''
        return len(self.__positions)

    @property
    def is_browsing(self) -> bool:
        '''Показана не последняя позиция'''
        return self.__index < len(self.__positions) - 1

    def __restore(self, index: int):
        '''Показать позицию из истории'''
        index = max(0, min(len(self.__positions) - 1, index))
        snapshot = self.__positions[index]
        self.__field = Field.copy(snapshot.field)
        self.__player_turn = snapshot.player_turn
        self.__quiet_halfmoves = snapshot.quiet
        self.__last_move = snapshot.last_move
        self.__index = index
        self.__selected_cell = Point()
        self.__hovered_cell = Point()
        self.__animated_cell = Point()
        self.__must_continue_from = None
        self.__hint_move = None
        self.__pending_captures = []
        self.__chain_legs = []
        self.__chain_captured = 0
        self.__chain_was_queen = False
        self.__draw()

    def goto(self, index: int):
        '''Перейти к позиции истории'''
        if not self.__positions:
            return
        self.__restore(index)

    def goto_first(self):
        '''К начальной позиции'''
        self.__restore(0)

    def goto_last(self):
        '''К текущей позиции партии'''
        self.__restore(len(self.__positions) - 1)

    def step_back(self):
        '''Предыдущая позиция'''
        self.__restore(self.__index - 1)

    def step_forward(self):
        '''Следующая позиция'''
        self.__restore(self.__index + 1)

    @property
    def can_step_back(self) -> bool:
        return self.__index > 0

    @property
    def can_step_forward(self) -> bool:
        return self.__index < len(self.__positions) - 1

    def undo(self) -> bool:
        '''Отменить ход игрока вместе с ответом ИИ'''
        if self.is_browsing:
            self.goto_last()
            return True
        if len(self.__positions) <= 1:
            return False

        self.__cancel_thinking_silently()
        self.__positions.pop()
        while len(self.__positions) > 1:
            last = self.__positions[-1]
            if last.player_turn and not last.chain:
                break
            self.__positions.pop()

        self.__game_over = False
        self.__game_over_reason = ''
        self.__index = len(self.__positions) - 1
        self.__restore(self.__index)
        self.__recount_repetitions()
        return True

    def __recount_repetitions(self):
        '''Пересчитать повторы позиций после отката'''
        self.__repetitions = {}
        for index, snapshot in enumerate(self.__positions):
            key = (R.position_key(snapshot.field), snapshot.player_turn)
            self.__repetitions[key] = self.__repetitions.get(key, 0) + 1
        self.__move_count = max(0, len(self.__positions) - 1)

    @property
    def can_undo(self) -> bool:
        '''Есть ли ход для отмены'''
        return len(self.__positions) > 1

    # --- Правила и поиск -----------------------------------------------------

    def __get_available_moves(self, side: SideType) -> list[Move]:
        '''Доступные ходы с учётом обязательного продолжения серии'''
        return self.__masked_moves(side)

    def __predict_optimal_move(self, side: SideType, moves_list: list[Move] = None) -> Move:
        '''Синхронный расчёт одного хода (используется подсказкой и тестами)'''
        if moves_list is None:
            moves_list = self.__masked_moves(side)
        if not moves_list:
            return None
        engine = Engine(self.__rules, self.__difficulty.depth, self.__difficulty.time_limit,
                        self.__difficulty.noise_scale)
        result = engine.search(Field.copy(self.__field), side, root_moves=moves_list)
        return result.move

    def __predict_optimal_moves(self, side: SideType) -> list[Move]:
        '''Обёртка для совместимости: всегда один ход'''
        move = self.__predict_optimal_move(side)
        return [move] if move else []

    def __evaluate_field(self, side: SideType) -> float:
        '''Оценка позиции с точки зрения стороны'''
        return evaluate_field(self.__field, side)

    def get_hint(self) -> Move:
        '''Лучший ход для игрока'''
        moves = self.__masked_moves(self.__player_side)
        if not moves:
            return None
        engine = Engine(self.__rules, max(2, self.__difficulty.depth), 1.0, 0.0)
        result = engine.search(Field.copy(self.__field), self.__player_side, root_moves=moves)
        return result.move

    def show_hint(self):
        '''Показать подсказку'''
        if not self.__player_turn or self.__game_over or self.is_browsing:
            return
        self.__hint_move = self.get_hint()
        if self.__hint_move is None:
            self.__toast('Подсказка недоступна', 'warn')
            return
        self.__draw()

    def hide_hint(self):
        '''Скрыть подсказку'''
        self.__hint_move = None
        self.__draw()

    @property
    def hint_move(self):
        return self.__hint_move

    # --- Настройки -----------------------------------------------------------

    def set_theme(self, theme: Theme):
        '''Сменить тему оформления доски'''
        self.__theme = theme
        self.__image_cache = {}
        self.__draw()

    def set_rules(self, rules: R.RuleSet):
        '''Сменить вариант правил (партия перезапускается)'''
        self.__rules = rules
        self.restart()

    def set_difficulty(self, difficulty: DifficultyType):
        '''Сменить уровень сложности'''
        self.__difficulty = difficulty

    def toggle_view(self):
        '''Перевернуть доску'''
        self.__view_side = SideType.opposite(self.__view_side)
        self.__draw()

    def set_view_side(self, side: SideType):
        '''Показать доску с точки зрения стороны'''
        self.__view_side = side
        self.__draw()

    def set_show_coordinates(self, value: bool):
        '''Показывать координаты вокруг доски'''
        self.__show_coordinates = bool(value)
        self.__draw()

    def toggle_sounds(self):
        '''Переключить звуки'''
        self.__sound_manager.toggle()

    def __toast(self, text: str, kind: str = 'info'):
        '''Сообщение в интерфейс'''
        if self.__toast_callback:
            self.__toast_callback(text, kind)

    def __notify_update(self):
        '''Уведомить интерфейс об изменении состояния'''
        if self.__update_callback:
            self.__update_callback()

    # --- Свойства ------------------------------------------------------------

    @property
    def is_player_turn(self) -> bool:
        return self.__player_turn

    @property
    def is_game_over(self) -> bool:
        return self.__game_over

    @property
    def game_over_reason(self) -> str:
        return self.__game_over_reason

    @property
    def move_count(self) -> int:
        return self.__move_count

    @property
    def player_side(self) -> SideType:
        return self.__player_side

    @property
    def view_side(self) -> SideType:
        return self.__view_side

    @property
    def rules(self) -> R.RuleSet:
        return self.__rules

    @property
    def theme(self) -> Theme:
        return self.__theme

    @property
    def white_checkers_count(self) -> int:
        return self.__field.white_checkers_count

    @property
    def black_checkers_count(self) -> int:
        return self.__field.black_checkers_count

    @property
    def sounds_enabled(self) -> bool:
        return self.__sound_manager.enabled

    @property
    def sounds_enabled_str(self) -> str:
        return self.__sound_manager.enabled_str

    @property
    def sound_manager(self) -> SoundManager:
        return self.__sound_manager

    @property
    def show_hover_hints(self) -> bool:
        return self.__show_hover_hints

    @show_hover_hints.setter
    def show_hover_hints(self, value: bool):
        self.__show_hover_hints = bool(value)
        self.__draw()

    @property
    def show_coordinates(self) -> bool:
        return self.__show_coordinates
