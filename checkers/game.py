from tkinter import Canvas, Event, messagebox
from PIL import Image, ImageTk
from random import choice, random
from pathlib import Path
from time import sleep
from math import inf
import threading

from checkers.field import Field
from checkers.move import Move
from checkers.constants import *
from checkers.enums import CheckerType, SideType, DifficultyType

from PIL.Image import LANCZOS as ANTIALIAS

class SoundManager:
    """Менеджер звуковых эффектов"""

    def __init__(self):
        self.__enabled = True
        try:
            from playsound import playsound
            self.__playsound = playsound
            self.__sounds = {
                'move': str(Path('assets', 'move.wav')),
                'capture': str(Path('assets', 'capture.wav')),
                'queen': str(Path('assets', 'queen.wav'))
            }
        except ImportError:
            self.__enabled = False

    def play(self, sound_name: str):
        """Воспроизвести звук в отдельном потоке"""
        if not self.__enabled:
            return

        sound_path = self.__sounds.get(sound_name)
        if not sound_path:
            return

        try:
            thread = threading.Thread(target=self.__playsound, args=(sound_path,), daemon=True)
            thread.start()
        except Exception:
            pass

    def toggle(self):
        """Переключить состояние звуков"""
        self.__enabled = not self.__enabled

    @property
    def enabled(self):
        return self.__enabled

    @property
    def enabled_str(self):
        return "Вкл" if self.__enabled else "Выкл"

class Game:
    def __init__(self, canvas: Canvas, x_field_size: int, y_field_size: int, difficulty: DifficultyType = DEFAULT_DIFFICULTY, update_callback=None):
        self.__canvas = canvas
        self.__field = Field(x_field_size, y_field_size)
        self.__difficulty = difficulty
        self.__update_callback = update_callback

        self.__player_turn = True

        self.__hovered_cell = Point()
        self.__selected_cell = Point()
        self.__animated_cell = Point()
        self.__last_move = None
        self.__hint_move = None

        self.__sound_manager = SoundManager()

        self.__init_images()

        self.__draw()

        # Если игрок играет за чёрных, то совершить ход противника
        if (PLAYER_SIDE == SideType.BLACK):
            self.__handle_enemy_turn()

    def __init_images(self):
        '''Инициализация изображений'''
        self.__images = {
            CheckerType.WHITE_REGULAR: ImageTk.PhotoImage(Image.open(Path('assets', 'white-regular.png')).resize((CELL_SIZE, CELL_SIZE), ANTIALIAS)),
            CheckerType.BLACK_REGULAR: ImageTk.PhotoImage(Image.open(Path('assets', 'black-regular.png')).resize((CELL_SIZE, CELL_SIZE), ANTIALIAS)),
            CheckerType.WHITE_QUEEN: ImageTk.PhotoImage(Image.open(Path('assets', 'white-queen.png')).resize((CELL_SIZE, CELL_SIZE), ANTIALIAS)),
            CheckerType.BLACK_QUEEN: ImageTk.PhotoImage(Image.open(Path('assets', 'black-queen.png')).resize((CELL_SIZE, CELL_SIZE), ANTIALIAS)),
        }

    def __animate_move(self, move: Move):
        '''Анимация перемещения шашки'''
        self.__animated_cell = Point(move.from_x, move.from_y)
        self.__draw()

        # Создание шашки для анимации
        animated_checker = self.__canvas.create_image(move.from_x * CELL_SIZE, move.from_y * CELL_SIZE, image=self.__images.get(self.__field.type_at(move.from_x, move.from_y)), anchor='nw', tag='animated_checker')
        
        # Вектора движения
        dx = 1 if move.from_x < move.to_x else -1
        dy = 1 if move.from_y < move.to_y else -1

        # Анимация
        for distance in range(abs(move.from_x - move.to_x)):
            for _ in range(100 // ANIMATION_SPEED):
                self.__canvas.move(animated_checker, ANIMATION_SPEED / 100 * CELL_SIZE * dx, ANIMATION_SPEED / 100 * CELL_SIZE * dy)
                self.__canvas.update()
                sleep(0.01)

        self.__animated_cell = Point()

    def __draw(self):
        '''Отрисовка сетки поля и шашек'''
        self.__canvas.delete('all')
        self.__draw_field_grid()
        self.__draw_checkers()
        self.__notify_update()

    def __draw_field_grid(self):
        '''Отрисовка сетки поля'''
        for y in range(self.__field.y_size):
            for x in range(self.__field.x_size):
                self.__canvas.create_rectangle(x * CELL_SIZE, y * CELL_SIZE, x * CELL_SIZE + CELL_SIZE, y * CELL_SIZE + CELL_SIZE, fill=FIELD_COLORS[(y + x) % 2], width=0, tag='boards')

                # Отрисовка рамок у необходимых клеток
                if (x == self.__selected_cell.x and y == self.__selected_cell.y):
                    self.__canvas.create_rectangle(x * CELL_SIZE + BORDER_WIDTH // 2, y * CELL_SIZE + BORDER_WIDTH // 2, x * CELL_SIZE + CELL_SIZE - BORDER_WIDTH // 2, y * CELL_SIZE + CELL_SIZE - BORDER_WIDTH // 2, outline=SELECT_BORDER_COLOR, width=BORDER_WIDTH, tag='border')
                elif (x == self.__hovered_cell.x and y == self.__hovered_cell.y):
                    self.__canvas.create_rectangle(x * CELL_SIZE + BORDER_WIDTH // 2, y * CELL_SIZE + BORDER_WIDTH // 2, x * CELL_SIZE + CELL_SIZE - BORDER_WIDTH // 2, y * CELL_SIZE + CELL_SIZE - BORDER_WIDTH // 2, outline=HOVER_BORDER_COLOR,  width=BORDER_WIDTH, tag='border')

                # Отрисовка выделения последнего хода
                if (self.__last_move and (x == self.__last_move.from_x and y == self.__last_move.from_y or x == self.__last_move.to_x and y == self.__last_move.to_y)):
                    self.__canvas.create_rectangle(x * CELL_SIZE + BORDER_WIDTH // 2, y * CELL_SIZE + BORDER_WIDTH // 2, x * CELL_SIZE + CELL_SIZE - BORDER_WIDTH // 2, y * CELL_SIZE + CELL_SIZE - BORDER_WIDTH // 2, outline='#4a90d9', width=BORDER_WIDTH, tag='last_move_border')

                # Отрисовка возможных точек перемещения, если есть выбранная ячейка
                if (self.__selected_cell):
                    player_moves_list = self.__get_moves_list(PLAYER_SIDE)
                    for move in player_moves_list:
                        if (self.__selected_cell.x == move.from_x and self.__selected_cell.y == move.from_y):
                            self.__canvas.create_oval(move.to_x * CELL_SIZE + CELL_SIZE / 3, move.to_y * CELL_SIZE + CELL_SIZE / 3, move.to_x * CELL_SIZE + (CELL_SIZE - CELL_SIZE / 3), move.to_y * CELL_SIZE + (CELL_SIZE - CELL_SIZE / 3), fill=POSIBLE_MOVE_CIRCLE_COLOR, width=0, tag='posible_move_circle' )

                # Подсветка ходов при наведении на шашку игрока
                if (self.__player_turn and not self.__selected_cell):
                    hovered_moves = self.__get_hovered_cell_moves()
                    for move in hovered_moves:
                        # Подсветка клетки назначения полупрозрачным зелёным
                        self.__canvas.create_rectangle(
                            move.to_x * CELL_SIZE, move.to_y * CELL_SIZE,
                            move.to_x * CELL_SIZE + CELL_SIZE, move.to_y * CELL_SIZE + CELL_SIZE,
                            fill='#54b346', stipple='gray50', tag='hovered_move_highlight'
                        )

                # Подсветка подсказки
                if (self.__hint_move):
                    # Подсветка исходной позиции жёлтым
                    if (x == self.__hint_move.from_x and y == self.__hint_move.from_y):
                        self.__canvas.create_rectangle(
                            x * CELL_SIZE, y * CELL_SIZE,
                            x * CELL_SIZE + CELL_SIZE, y * CELL_SIZE + CELL_SIZE,
                            fill='#FFD700', stipple='gray50', tag='hint_highlight'
                        )
                    # Подсветка позиции назначения зелёным
                    if (x == self.__hint_move.to_x and y == self.__hint_move.to_y):
                        self.__canvas.create_rectangle(
                            x * CELL_SIZE, y * CELL_SIZE,
                            x * CELL_SIZE + CELL_SIZE, y * CELL_SIZE + CELL_SIZE,
                            fill='#54b346', stipple='gray50', tag='hint_highlight'
                        )

    def __draw_checkers(self):
        '''Отрисовка шашек'''
        for y in range(self.__field.y_size):
            for x in range(self.__field.x_size):
                # Не отрисовывать пустые ячейки и анимируемую шашку
                if (self.__field.type_at(x, y) != CheckerType.NONE and not (x == self.__animated_cell.x and y == self.__animated_cell.y)):
                    self.__canvas.create_image(x * CELL_SIZE, y * CELL_SIZE, image=self.__images.get(self.__field.type_at(x, y)), anchor='nw', tag='checkers')

    def mouse_move(self, event: Event):
        '''Событие перемещения мышки'''
        x, y = (event.x) // CELL_SIZE, (event.y) // CELL_SIZE
        if (x != self.__hovered_cell.x or y != self.__hovered_cell.y):
            self.__hovered_cell = Point(x, y)

            # Если ход игрока, то перерисовать
            if (self.__player_turn):
                self.__draw()

    def __get_hovered_cell_moves(self) -> list[Move]:
        '''Получить ходы для шашки под курсором'''
        if (PLAYER_SIDE == SideType.WHITE):
            player_checkers = WHITE_CHECKERS
        elif (PLAYER_SIDE == SideType.BLACK):
            player_checkers = BLACK_CHECKERS
        else:
            return []

        # Если под курсором шашка игрока
        if (self.__field.type_at(self.__hovered_cell.x, self.__hovered_cell.y) in player_checkers):
            all_moves = self.__get_moves_list(PLAYER_SIDE)
            return [m for m in all_moves if m.from_x == self.__hovered_cell.x and m.from_y == self.__hovered_cell.y]
        return []

    def mouse_down(self, event: Event):
        '''Событие нажатия мышки'''
        if not (self.__player_turn): return

        x, y = (event.x) // CELL_SIZE, (event.y) // CELL_SIZE

        # Если точка не внутри поля
        if not (self.__field.is_within(x, y)): return

        # Скрыть подсказку при любом действии
        if (self.__hint_move):
            self.hide_hint()

        if (PLAYER_SIDE == SideType.WHITE):
            player_checkers = WHITE_CHECKERS
        elif (PLAYER_SIDE == SideType.BLACK):
            player_checkers = BLACK_CHECKERS
        else: return

        # Если нажатие по шашке игрока, то выбрать её
        if (self.__field.type_at(x, y) in player_checkers):
            self.__selected_cell = Point(x, y)
            self.__last_move = None  # Сброс выделения последнего хода
            self.__draw()
        elif (self.__player_turn):
            move = Move(self.__selected_cell.x, self.__selected_cell.y, x, y)

            # Если нажатие по ячейке, на которую можно походить
            if (move in self.__get_moves_list(PLAYER_SIDE)):
                self.__handle_player_turn(move)

                # Если не ход игрока, то ход противника
                if not (self.__player_turn):
                    self.__handle_enemy_turn()

    def __handle_move(self, move: Move, draw: bool = True) -> bool:
        '''Совершение хода'''
        if (draw): self.__animate_move(move)

        # Определение типа движения для звука
        is_queen_promotion = False
        if (move.to_y == 0 and self.__field.type_at(move.from_x, move.from_y) == CheckerType.WHITE_REGULAR):
            is_queen_promotion = True
        elif (move.to_y == self.__field.y_size - 1 and self.__field.type_at(move.from_x, move.from_y) == CheckerType.BLACK_REGULAR):
            is_queen_promotion = True

        # Изменение типа шашки, если она дошла до края
        if (move.to_y == 0 and self.__field.type_at(move.from_x, move.from_y) == CheckerType.WHITE_REGULAR):
            self.__field.at(move.from_x, move.from_y).change_type(CheckerType.WHITE_QUEEN)
        elif (move.to_y == self.__field.y_size - 1 and self.__field.type_at(move.from_x, move.from_y) == CheckerType.BLACK_REGULAR):
            self.__field.at(move.from_x, move.from_y).change_type(CheckerType.BLACK_QUEEN)

        # Изменение позиции шашки
        self.__field.at(move.to_x, move.to_y).change_type(self.__field.type_at(move.from_x, move.from_y))
        self.__field.at(move.from_x, move.from_y).change_type(CheckerType.NONE)

        # Вектора движения
        dx = -1 if move.from_x < move.to_x else 1
        dy = -1 if move.from_y < move.to_y else 1

        # Удаление съеденных шашек
        has_killed_checker = False
        x, y = move.to_x, move.to_y
        while (x != move.from_x or y != move.from_y):
            x += dx
            y += dy
            if (self.__field.type_at(x, y) != CheckerType.NONE):
                self.__field.at(x, y).change_type(CheckerType.NONE)
                has_killed_checker = True

        # Воспроизведение звука
        if (draw):
            if (is_queen_promotion):
                self.__sound_manager.play('queen')
            elif (has_killed_checker):
                self.__sound_manager.play('capture')
            else:
                self.__sound_manager.play('move')
            
            # Сохранение последнего хода
            self.__last_move = move
            self.__draw()

        return has_killed_checker

    def __handle_player_turn(self, move: Move):
        '''Обработка хода игрока'''
        self.__player_turn = False

        # Была ли убита шашка
        has_killed_checker = self.__handle_move(move)

        required_moves_list = list(filter(lambda required_move: move.to_x == required_move.from_x and move.to_y == required_move.from_y, self.__get_required_moves_list(PLAYER_SIDE)))
        
        # Если есть ещё ход этой же шашкой
        if (has_killed_checker and required_moves_list):
            self.__player_turn = True

        self.__selected_cell = Point()

    def __handle_enemy_turn(self):
        '''Обработка хода противника (компьютера)'''
        self.__player_turn = False

        optimal_moves_list = self.__predict_optimal_moves(SideType.opposite(PLAYER_SIDE))

        for move in optimal_moves_list:
            self.__handle_move(move)
            
        self.__player_turn = True
        
        self.__check_for_game_over()

    def __check_for_game_over(self):
        '''Проверка на конец игры'''
        game_over = False

        white_moves_list = self.__get_moves_list(SideType.WHITE)
        if not (white_moves_list):
            # Белые проиграли
            messagebox.showinfo('Конец игры', 'Чёрные выиграли')
            game_over = True

        black_moves_list = self.__get_moves_list(SideType.BLACK)
        if not (black_moves_list):
            # Чёрные проиграли
            messagebox.showinfo('Конец игры', 'Белые выиграли')
            game_over = True

        if (game_over):
            # Новая игра с сохранением уровня сложности
            self.__field = Field(self.__field.x_size, self.__field.y_size)
            self.__player_turn = True
            self.__hovered_cell = Point()
            self.__selected_cell = Point()
            self.__animated_cell = Point()
            self.__draw()

            # Если игрок играет за чёрных, то совершить ход противника
            if (PLAYER_SIDE == SideType.BLACK):
                self.__handle_enemy_turn()

    def __predict_optimal_moves(self, side: SideType) -> list[Move]:
        '''Предсказать оптимальный ход с помощью минимакса с альфа-бета отсечением'''
        max_depth = self.__difficulty.depth
        field_copy = Field.copy(self.__field)

        # Получаем все возможные ходы
        moves_list = self.__get_moves_list(side)
        if not (moves_list):
            return []

        best_score = -inf
        best_moves = []

        for move in moves_list:
            # Совершаем ход
            self.__handle_move(move, draw=False)

            # Запускаем минимакс с альфа-бета отсечением
            score = self.__minimax(side, max_depth - 1, -inf, inf, False)

            # Восстанавливаем поле
            self.__field = Field.copy(field_copy)

            if (score > best_score):
                best_score = score
                best_moves = [[move]]
            elif (score == best_score):
                best_moves.append([move])

        # Обработка результатов с учётом случайности для низких уровней
        optimal_move = []
        if (best_moves):
            selected_moves = choice(best_moves)
            for move in selected_moves:
                # Добавление случайности для лёгких уровней
                if (self.__difficulty == DifficultyType.EASY and random() < 0.3):
                    continue
                elif (self.__difficulty == DifficultyType.MEDIUM and random() < 0.1):
                    continue
                optimal_move.append(move)

            if not (optimal_move) and best_moves:
                optimal_move = [choice(best_moves)[0]]

        return optimal_move

    def __minimax(self, side: SideType, depth: int, alpha: float, beta: float, is_maximizing: bool) -> float:
        '''Минимакс с альфа-бета отсечением'''
        if (depth == 0):
            return self.__evaluate_field(side)

        current_side = side if is_maximizing else SideType.opposite(side)
        moves_list = self.__get_moves_list(current_side)

        if not (moves_list):
            # Нет ходов - конец игры
            return -inf if is_maximizing else inf

        field_copy = Field.copy(self.__field)

        if (is_maximizing):
            max_eval = -inf
            for move in moves_list:
                self.__handle_move(move, draw=False)
                eval_score = self.__minimax(side, depth - 1, alpha, beta, False)
                self.__field = Field.copy(field_copy)
                max_eval = max(max_eval, eval_score)
                alpha = max(alpha, eval_score)
                if (beta <= alpha):
                    break
            return max_eval
        else:
            min_eval = inf
            for move in moves_list:
                self.__handle_move(move, draw=False)
                eval_score = self.__minimax(side, depth - 1, alpha, beta, True)
                self.__field = Field.copy(field_copy)
                min_eval = min(min_eval, eval_score)
                beta = min(beta, eval_score)
                if (beta <= alpha):
                    break
            return min_eval

    def __evaluate_field(self, side: SideType) -> float:
        '''Оценка позиции на поле'''
        if (side == SideType.WHITE):
            enemy_side = SideType.BLACK
        else:
            enemy_side = SideType.WHITE

        # Базовая оценка по материалу
        my_score = self.__field.get_score(side)
        enemy_score = self.__field.get_score(enemy_side)

        if (enemy_score == 0):
            return inf
        if (my_score == 0):
            return -inf

        # Позиционная оценка
        positional_bonus = 0
        center_x, center_y = self.__field.x_size / 2, self.__field.y_size / 2

        for y in range(self.__field.y_size):
            for x in range(self.__field.x_size):
                checker_type = self.__field.type_at(x, y)
                if (checker_type == CheckerType.NONE):
                    continue

                # Расстояние до центра
                distance_to_center = abs(x - center_x) + abs(y - center_y)
                center_bonus = (4 - distance_to_center) * 0.1

                # Защита шашек (бонус за соседние союзные шашки)
                defense_bonus = 0
                for offset in MOVE_OFFSETS:
                    if (self.__field.is_within(x + offset.x, y + offset.y)):
                        if (self.__field.type_at(x + offset.x, y + offset.y) in 
                            (WHITE_CHECKERS if side == SideType.WHITE else BLACK_CHECKERS)):
                            defense_bonus += 0.2

                # Бонус за продвижение вперёд
                advance_bonus = 0
                if (side == SideType.WHITE):
                    advance_bonus = (self.__field.y_size - 1 - y) * 0.05
                else:
                    advance_bonus = y * 0.05

                # Суммируем бонусы
                if (checker_type in (WHITE_CHECKERS if side == SideType.WHITE else BLACK_CHECKERS)):
                    positional_bonus += center_bonus + defense_bonus + advance_bonus
                else:
                    positional_bonus -= center_bonus + defense_bonus + advance_bonus

        return (my_score / enemy_score) + positional_bonus

    def __get_moves_list(self, side: SideType) -> list[Move]:
        '''Получение списка ходов'''
        moves_list = self.__get_required_moves_list(side)
        if not (moves_list):
            moves_list = self.__get_optional_moves_list(side)
        return moves_list

    def __get_required_moves_list(self, side: SideType) -> list[Move]:
        '''Получение списка обязательных ходов'''
        moves_list = []

        # Определение типов шашек
        if (side == SideType.WHITE):
            friendly_checkers = WHITE_CHECKERS
            enemy_checkers = BLACK_CHECKERS
        elif (side == SideType.BLACK):
            friendly_checkers = BLACK_CHECKERS
            enemy_checkers = WHITE_CHECKERS
        else: return moves_list

        for y in range(self.__field.y_size):
            for x in range(self.__field.x_size):

                # Для обычной шашки
                if (self.__field.type_at(x, y) == friendly_checkers[0]):
                    for offset in MOVE_OFFSETS:
                        if not (self.__field.is_within(x + offset.x * 2, y + offset.y * 2)): continue

                        if self.__field.type_at(x + offset.x, y + offset.y) in enemy_checkers and self.__field.type_at(x + offset.x * 2, y + offset.y * 2) == CheckerType.NONE:
                            moves_list.append(Move(x, y, x + offset.x * 2, y + offset.y * 2))

                # Для дамки
                elif (self.__field.type_at(x, y) == friendly_checkers[1]):
                    for offset in MOVE_OFFSETS:
                        if not (self.__field.is_within(x + offset.x * 2, y + offset.y * 2)): continue

                        has_enemy_checker_on_way = False

                        for shift in range(1, self.__field.size):
                            if not (self.__field.is_within(x + offset.x * shift, y + offset.y * shift)): continue

                            # Если на пути не было вражеской шашки
                            if (not has_enemy_checker_on_way):
                                if (self.__field.type_at(x + offset.x * shift, y + offset.y * shift) in enemy_checkers):
                                    has_enemy_checker_on_way = True
                                    continue
                                # Если на пути союзная шашка - то закончить цикл
                                elif (self.__field.type_at(x + offset.x * shift, y + offset.y * shift) in friendly_checkers):
                                    break
                            
                            # Если на пути была вражеская шашка
                            if (has_enemy_checker_on_way):
                                if (self.__field.type_at(x + offset.x * shift, y + offset.y * shift) == CheckerType.NONE):
                                    moves_list.append(Move(x, y, x + offset.x * shift, y + offset.y * shift))
                                else:
                                    break
                            
        return moves_list

    def __get_optional_moves_list(self, side: SideType) -> list[Move]:
        '''Получение списка необязательных ходов'''
        moves_list = []

        # Определение типов шашек
        if (side == SideType.WHITE):
            friendly_checkers = WHITE_CHECKERS
        elif (side == SideType.BLACK):
            friendly_checkers = BLACK_CHECKERS
        else: return moves_list

        for y in range(self.__field.y_size):
            for x in range(self.__field.x_size):
                # Для обычной шашки
                if (self.__field.type_at(x, y) == friendly_checkers[0]):
                    for offset in MOVE_OFFSETS[:2] if side == SideType.WHITE else MOVE_OFFSETS[2:]:
                        if not (self.__field.is_within(x + offset.x, y + offset.y)): continue

                        if (self.__field.type_at(x + offset.x, y + offset.y) == CheckerType.NONE):
                            moves_list.append(Move(x, y, x + offset.x, y + offset.y))

                # Для дамки
                elif (self.__field.type_at(x, y) == friendly_checkers[1]):
                    for offset in MOVE_OFFSETS:
                        if not (self.__field.is_within(x + offset.x, y + offset.y)): continue

                        for shift in range(1, self.__field.size):
                            if not (self.__field.is_within(x + offset.x * shift, y + offset.y * shift)): continue

                            if (self.__field.type_at(x + offset.x * shift, y + offset.y * shift) == CheckerType.NONE):
                                moves_list.append(Move(x, y, x + offset.x * shift, y + offset.y * shift))
                            else:
                                break
        return moves_list

    @property
    def is_player_turn(self) -> bool:
        '''Ход игрока'''
        return self.__player_turn

    @property
    def white_checkers_count(self) -> int:
        '''Количество белых шашек'''
        return self.__field.white_checkers_count

    @property
    def black_checkers_count(self) -> int:
        '''Количество чёрных шашек'''
        return self.__field.black_checkers_count

    def __notify_update(self):
        '''Уведомить об обновлении'''
        if self.__update_callback:
            self.__update_callback()

    def toggle_sounds(self):
        '''Переключить звуки'''
        self.__sound_manager.toggle()

    @property
    def sounds_enabled(self) -> bool:
        return self.__sound_manager.enabled

    def get_hint(self) -> Move:
        '''Получить подсказку - лучший ход для игрока'''
        if (PLAYER_SIDE == SideType.WHITE):
            side = SideType.WHITE
        else:
            side = SideType.BLACK

        moves_list = self.__get_moves_list(side)
        if not (moves_list):
            return None

        best_score = -inf
        best_move = None
        field_copy = Field.copy(self.__field)

        for move in moves_list:
            self.__handle_move(move, draw=False)
            score = self.__minimax(side, 2, -inf, inf, True)
            self.__field = Field.copy(field_copy)

            if (score > best_score):
                best_score = score
                best_move = move

        return best_move

    def show_hint(self):
        '''Показать подсказку'''
        if (self.__player_turn):
            self.__hint_move = self.get_hint()
            self.__draw()

    def hide_hint(self):
        '''Скрыть подсказку'''
        self.__hint_move = None
        self.__draw()

    @property
    def hint_move(self):
        '''Ход-подсказка'''
        return self.__hint_move