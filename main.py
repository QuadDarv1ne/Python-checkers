"""Точка входа игры «Шашки».

Окно: меню, панель статуса, доска с координатами и панель истории ходов.
Доска масштабируется вместе с окном, тема и вариант правил переключаются
из меню, все уведомления выводятся тостами, а не модальными диалогами.
"""
import sys
from tkinter import BooleanVar, Canvas, Frame, IntVar, Label, Menu, PhotoImage, StringVar, Tk
from tkinter import messagebox

from checkers import cursor_packs
from checkers import rules as R
from checkers.constants import X_SIZE, Y_SIZE
from checkers.cursor import (
    ARROW,
    CURSOR_COLORS,
    HAND,
    WAIT,
    CanvasCursor,
    cursor_color,
)
from checkers.enums import DifficultyType, SideType
from checkers.game import Game
from checkers.paths import ICON_ICO_PATH, ICON_PATH
from checkers.settings import Settings
from checkers.theme import THEMES, theme_by_key
from checkers.toast import ToastManager

APP_TITLE = 'Шашки'

# Минимальный размер окна и доля, отводимая панели истории
MIN_WIDTH = 560
MIN_HEIGHT = 640
HISTORY_WIDTH = 176

# Соответствие горячих клавиш и действий (показывается в меню)
SHORTCUTS = {
    'new': 'Ctrl+N',
    'restart': 'Ctrl+R',
    'undo': 'Ctrl+Z',
    'hint': 'Ctrl+H',
    'sound': 'Ctrl+S',
    'music': 'Ctrl+M',
    'flip': 'Ctrl+F',
    'back': 'Ctrl+Left',
    'forward': 'Ctrl+Right',
    'exit': 'Ctrl+Q',
}


def _enable_dpi_awareness():
    '''Отключить растягивание окна системным масштабом Windows.

    Без этого при масштабе 125% окно растягивается, а холст с доской
    остаётся в исходных пикселях — справа и снизу появляются пустые поля.
    '''
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        # 1 — PROCESS_SYSTEM_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _set_icon(window: Tk):
    '''Установить иконку окна, если файл доступен'''
    for path in (ICON_PATH, ICON_ICO_PATH):
        try:
            if not path.exists():
                continue
            icon = PhotoImage(file=str(path))
            window.iconphoto(False, icon)
            # Сохранить ссылку, чтобы сборщик мусора не удалил изображение
            window._icon_image = icon
            return
        except Exception:
            continue


def _difficulty_by_index(index: int) -> DifficultyType:
    '''Уровень сложности по индексу с защитой от некорректного значения'''
    difficulties = list(DifficultyType)
    if not isinstance(index, int) or not (0 <= index < len(difficulties)):
        index = 0
    return difficulties[index]


def _side_name(side: SideType) -> str:
    '''Название стороны на русском'''
    return 'Белые' if side == SideType.WHITE else 'Чёрные'


class CheckersApp:
    '''Приложение целиком: окно, меню, панели и игровая сессия'''

    def __init__(self):
        _enable_dpi_awareness()
        self.settings = Settings()
        self.theme = theme_by_key(self.settings.theme)
        self.rules = R.rules_by_key(self.settings.rules)

        self.window = Tk()
        self.window.title(APP_TITLE)
        self.window.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.window.geometry(f'{MAX_WORK_WIDTH}x{MAX_WORK_HEIGHT}')
        _set_icon(self.window)

        self.game = None
        self.__history_rows: list[Label] = []
        self.__toasts = ToastManager(self.window)

        self.difficulty_var = IntVar(value=self.settings.difficulty)
        self.side_var = IntVar(value=list(SideType).index(self.settings.player_side))
        self.rules_var = IntVar(value=list(R.RULE_SETS).index(self.rules.key))
        self.theme_var = IntVar(value=list(THEMES).index(self.theme.key))
        self.hover_var = BooleanVar(value=True)
        self.coords_var = BooleanVar(value=True)
        self.sounds_var = BooleanVar(value=self.settings.sounds_enabled)
        self.music_var = BooleanVar(value=self.settings.music_enabled)
        self.volume_var = IntVar(value=self.settings.volume)
        self.custom_cursor_var = BooleanVar(value=self.settings.custom_cursor)
        self.cursor_color_var = IntVar(value=list(CURSOR_COLORS).index(self.settings.cursor_color)
                                       if self.settings.cursor_color in CURSOR_COLORS else 0)
        self.cursor_pack_var = StringVar(value=self.settings.cursor_pack)

        self.__build_layout()
        self.__build_menu()
        self.__bind_hotkeys()
        self.__cursor = CanvasCursor(self.canvas)
        self.__apply_theme()
        self.__apply_cursor_settings()

        self.new_game(_difficulty_by_index(self.settings.difficulty), self.settings.player_side)
        self.__apply_saved_audio()
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.after(120, self.__fit_board)

    # --- Компоновка ----------------------------------------------------------

    def __build_layout(self):
        '''Панель статуса сверху, доска слева, история справа'''
        self.status_frame = Frame(self.window)
        self.status_frame.pack(fill='x')

        inner = Frame(self.status_frame)
        inner.pack(fill='x', padx=12, pady=6)

        self.turn_label = Label(inner, font=('Segoe UI', 12, 'bold'))
        self.turn_label.pack(side='left')

        self.difficulty_label = Label(inner, font=('Segoe UI', 9))
        self.difficulty_label.pack(side='left', padx=(8, 0))

        self.audio_label = Label(inner, font=('Segoe UI', 9))
        self.audio_label.pack(side='right')

        self.score_label = Label(inner, font=('Segoe UI', 10))
        self.score_label.pack(side='right', padx=(0, 12))

        self.separator = Frame(self.window, height=1)
        self.separator.pack(fill='x')

        body = Frame(self.window)
        body.pack(fill='both', expand=True)
        self.body = body

        self.canvas = Canvas(body, highlightthickness=0, bd=0, borderwidth=0)
        self.canvas.pack(side='left', fill='both', expand=True, padx=(8, 0), pady=8)

        self.history_frame = Frame(body, width=HISTORY_WIDTH, bd=0, highlightthickness=0)
        self.history_frame.pack(side='right', fill='y', padx=(8, 10), pady=8)
        self.history_frame.pack_propagate(False)

        self.history_title = Label(self.history_frame, text='История ходов',
                                   font=('Segoe UI', 10, 'bold'), anchor='w')
        self.history_title.pack(fill='x', pady=(0, 6))

        self.history_list = Frame(self.history_frame)
        self.history_list.pack(fill='both', expand=True)

        self.history_hint = Label(self.history_frame, text='Ctrl+← / Ctrl+→ — листать',
                                  font=('Segoe UI', 8), anchor='w', justify='left')
        self.history_hint.pack(fill='x', pady=(6, 0))

        self.canvas.bind('<Configure>', self.__on_canvas_configure)
        self.canvas.bind('<Motion>', self.__on_motion)
        self.canvas.bind('<Button-1>', lambda event: self.game.mouse_down(event) if self.game else None)
        self.canvas.bind('<Leave>', self.__on_canvas_leave)

    # --- Тема ----------------------------------------------------------------

    def __apply_theme(self):
        '''Применить цвета темы ко всем элементам окна'''
        theme = self.theme
        self.window.configure(bg=theme.panel_bg)
        for frame in (self.status_frame, self.body, self.history_frame, self.history_list):
            frame.configure(bg=theme.panel_bg)

        for child in self.status_frame.winfo_children():
            child.configure(bg=theme.panel_bg)
        for child in self.status_frame.winfo_children()[0].winfo_children():
            child.configure(bg=theme.panel_bg)

        self.turn_label.configure(fg=theme.panel_fg)
        self.score_label.configure(fg=theme.panel_fg)
        self.difficulty_label.configure(fg=theme.panel_muted)
        self.audio_label.configure(fg=theme.panel_muted)
        self.separator.configure(bg=theme.separator)
        self.history_title.configure(bg=theme.panel_bg, fg=theme.panel_fg)
        self.history_hint.configure(bg=theme.panel_bg, fg=theme.panel_muted)
        self.canvas.configure(bg=theme.canvas_bg)

        for row in self.__history_rows:
            row.configure(bg=theme.panel_bg)

        if self.game is not None:
            self.game.set_theme(theme)
        self.__render_history()

    def set_theme(self, key: str):
        '''Сменить тему оформления'''
        self.theme = theme_by_key(key)
        self.theme_var.set(list(THEMES).index(self.theme.key))
        self.settings.theme = self.theme.key
        self.__apply_theme()
        if self.__cursor is not None:
            # Акцентный курсор должен перекраситься вместе с темой
            self.__apply_cursor_settings()
        self.__toast(f'Тема: {self.theme.name_ru}', 'ok')

    # --- Масштабирование -----------------------------------------------------

    def __on_canvas_configure(self, event=None):
        '''Подогнать доску под размер холста'''
        if self.game is None:
            return
        width = event.width if event is not None else self.canvas.winfo_width()
        height = event.height if event is not None else self.canvas.winfo_height()
        # Запас под координаты уже учтён внутри Game
        self.game.resize(width - 4, height - 4)

    def __fit_board(self):
        '''Первичная подгонка доски после отрисовки окна'''
        self.window.update_idletasks()
        self.__on_canvas_configure()

    # --- Меню ----------------------------------------------------------------

    def __build_menu(self):
        '''Главное меню: игра, сложность, сторона, правила, звук, вид, справка'''
        menu = Menu(self.window)
        self.window.config(menu=menu)

        game_menu = Menu(menu, tearoff=0)
        menu.add_cascade(label='Игра', menu=game_menu, underline=0)
        game_menu.add_command(label='Новая игра', accelerator=SHORTCUTS['new'], command=self.restart_game)
        game_menu.add_command(label='Начать заново', accelerator=SHORTCUTS['restart'], command=self.restart_board)
        game_menu.add_separator()
        game_menu.add_command(label='Отменить ход', accelerator=SHORTCUTS['undo'], command=self.undo_move)
        game_menu.add_command(label='Подсказка', accelerator=SHORTCUTS['hint'], command=self.show_hint)
        game_menu.add_command(label='Остановить расчёт ИИ', command=self.cancel_thinking)
        game_menu.add_separator()
        game_menu.add_command(label='Предложить ничью', command=self.offer_draw)
        game_menu.add_command(label='Сдаться', command=self.resign)
        game_menu.add_separator()
        game_menu.add_command(label='Выход', accelerator=SHORTCUTS['exit'], command=self.close)

        difficulty_menu = Menu(menu, tearoff=0)
        menu.add_cascade(label='Сложность', menu=difficulty_menu, underline=0)
        for diff in DifficultyType:
            difficulty_menu.add_radiobutton(
                label=f'{diff.name_ru} (до {diff.depth} полуходов, {diff.time_limit:g} с)',
                value=list(DifficultyType).index(diff),
                variable=self.difficulty_var,
                command=lambda d=diff: self.set_difficulty(d),
            )

        side_menu = Menu(menu, tearoff=0)
        menu.add_cascade(label='Сторона', menu=side_menu, underline=0)
        for side in (SideType.WHITE, SideType.BLACK):
            side_menu.add_radiobutton(
                label=f'Играть за {_side_name(side).lower()}',
                value=list(SideType).index(side),
                variable=self.side_var,
                command=lambda s=side: self.set_side(s),
            )

        rules_menu = Menu(menu, tearoff=0)
        menu.add_cascade(label='Правила', menu=rules_menu, underline=0)
        for rules in R.RULE_SETS.values():
            rules_menu.add_radiobutton(
                label=rules.name_ru,
                value=list(R.RULE_SETS).index(rules.key),
                variable=self.rules_var,
                command=lambda r=rules: self.set_rules(r),
            )

        sound_menu = Menu(menu, tearoff=0)
        menu.add_cascade(label='Звук', menu=sound_menu, underline=0)
        sound_menu.add_checkbutton(label='Звуковые эффекты', accelerator=SHORTCUTS['sound'],
                                   variable=self.sounds_var, command=self.toggle_sounds)
        sound_menu.add_checkbutton(label='Фоновая музыка', accelerator=SHORTCUTS['music'],
                                   variable=self.music_var, command=self.toggle_music)
        sound_menu.add_separator()
        volume_menu = Menu(sound_menu, tearoff=0)
        sound_menu.add_cascade(label='Громкость', menu=volume_menu)
        for volume in (100, 80, 60, 40, 20):
            volume_menu.add_radiobutton(label=f'{volume}%', value=volume,
                                        variable=self.volume_var,
                                        command=lambda v=volume: self.set_volume(v))

        view_menu = Menu(menu, tearoff=0)
        menu.add_cascade(label='Вид', menu=view_menu, underline=0)
        view_menu.add_command(label='Перевернуть доску', accelerator=SHORTCUTS['flip'],
                              command=self.flip_board)
        view_menu.add_checkbutton(label='Координаты a–h / 1–8', variable=self.coords_var,
                                  command=self.__apply_coordinates)
        view_menu.add_checkbutton(label='Подсвечивать ходы под курсором',
                                  variable=self.hover_var, command=self.__apply_hover_hint)
        view_menu.add_separator()
        theme_menu = Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label='Тема', menu=theme_menu)
        for index, theme in enumerate(THEMES.values()):
            theme_menu.add_radiobutton(label=theme.name_ru, value=index,
                                       variable=self.theme_var,
                                       command=lambda k=theme.key: self.set_theme(k))

        cursor_menu = Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label='Курсор', menu=cursor_menu)
        cursor_menu.add_checkbutton(label='Свой курсор над доской',
                                    variable=self.custom_cursor_var,
                                    command=self.__apply_cursor_toggle)
        cursor_menu.add_separator()
        self.__build_cursor_pack_menu(cursor_menu)
        cursor_menu.add_separator()
        for index, (key, (name, _)) in enumerate(CURSOR_COLORS.items()):
            cursor_menu.add_radiobutton(label=name, value=index,
                                        variable=self.cursor_color_var,
                                        command=lambda k=key: self.set_cursor_color(k))

        history_menu = Menu(menu, tearoff=0)
        menu.add_cascade(label='История', menu=history_menu, underline=0)
        history_menu.add_command(label='Начальная позиция', command=self.goto_first)
        history_menu.add_command(label='Предыдущая позиция', accelerator=SHORTCUTS['back'],
                                 command=self.step_back)
        history_menu.add_command(label='Следующая позиция', accelerator=SHORTCUTS['forward'],
                                 command=self.step_forward)
        history_menu.add_command(label='Текущая позиция', command=self.goto_last)

        help_menu = Menu(menu, tearoff=0)
        menu.add_cascade(label='Справка', menu=help_menu, underline=0)
        help_menu.add_command(label='Горячие клавиши', accelerator='F1', command=self.show_hotkeys)
        help_menu.add_command(label='О программе', command=self.show_about)

    def __apply_cursor_toggle(self):
        '''Переключатель своего курсора из меню'''
        self.set_cursor_enabled(self.custom_cursor_var.get())

    def __bind_hotkeys(self):
        '''Горячие клавиши окна'''
        bindings = {
            '<Control-n>': self.restart_game,
            '<Control-r>': self.restart_board,
            '<Control-z>': self.undo_move,
            '<Control-h>': self.show_hint,
            '<Control-f>': self.flip_board,
            '<Control-Left>': self.step_back,
            '<Control-Right>': self.step_forward,
            '<Control-s>': self.__hotkey_sound,
            '<Control-m>': self.__hotkey_music,
            '<Control-q>': self.close,
            '<F1>': self.show_hotkeys,
            '<Escape>': self.hide_hint,
        }
        for sequence, handler in bindings.items():
            self.window.bind(sequence, lambda event, h=handler: h())

    def __hotkey_sound(self):
        '''Ctrl+S: переключить эффекты'''
        self.sounds_var.set(not self.sounds_var.get())
        self.toggle_sounds()

    def __hotkey_music(self):
        '''Ctrl+M: переключить музыку'''
        self.music_var.set(not self.music_var.get())
        self.toggle_music()

    def __on_canvas_leave(self, event=None):
        '''Курсор ушёл с доски — снять наведение'''
        if self.game is not None:
            self.game.mouse_move(type('Event', (), {'x': -1000, 'y': -1000})())
        if self.__cursor is not None:
            self.__cursor.hide()

    # --- Свой курсор ---------------------------------------------------------

    def __on_motion(self, event):
        '''Движение мыши: игровая логика и вид курсора'''
        if self.game is None:
            return
        self.game.mouse_move(event)
        if self.__cursor is None or not self.__cursor.enabled:
            return

        self.__cursor.set_size(max(20.0, self.game.cell_size * 0.425))
        self.__cursor.move(event.x, event.y, self.__cursor_kind(event))

    def __cursor_kind(self, event) -> str:
        '''Подобрать вид курсора под клетку под мышью'''
        if self.game is None:
            return ARROW
        if self.game.is_thinking:
            return WAIT
        cell = self.game._Game__cell_from_pixel(event.x, event.y)
        if not cell:
            return ARROW

        moves = self.game._Game__get_available_moves(self.game.player_side)
        if any(move.from_x == cell.x and move.from_y == cell.y for move in moves):
            return HAND
        return ARROW

    def __apply_cursor_settings(self):
        '''Применить настройки курсора к холсту'''
        key = list(CURSOR_COLORS)[self.cursor_color_var.get()]
        self.__cursor.set_color(cursor_color(key, self.theme))
        self.__cursor.set_pack(self.cursor_pack_var.get())
        self.__cursor.set_enabled(self.custom_cursor_var.get())
        if not self.custom_cursor_var.get():
            # Возвращаем обычную «руку» над доской как системный курсор
            try:
                self.canvas.config(cursor='arrow')
            except Exception:
                pass

    def set_cursor_enabled(self, enabled: bool):
        '''Включить или выключить свой курсор'''
        self.custom_cursor_var.set(bool(enabled))
        self.settings.custom_cursor = self.custom_cursor_var.get()
        self.__apply_cursor_settings()
        self.__toast('Свой курсор включён' if enabled else 'Системный курсор', 'ok')

    def set_cursor_color(self, key: str):
        '''Перекрасить курсор'''
        if key not in CURSOR_COLORS:
            return
        self.cursor_color_var.set(list(CURSOR_COLORS).index(key))
        self.settings.cursor_color = key
        self.__cursor.set_color(cursor_color(key, self.theme))
        self.__toast(f'Цвет курсора: {CURSOR_COLORS[key][0].lower()}', 'ok')

    def set_cursor_pack(self, key: str):
        '''Выбрать набор курсоров ('' — векторная форма)'''
        pack = cursor_packs.pack_by_key(key)
        self.cursor_pack_var.set(key if pack is not None else '')
        self.settings.cursor_pack = self.cursor_pack_var.get()
        self.__cursor.set_pack(self.cursor_pack_var.get())
        self.__toast(f'Курсор: {pack.name.lower() if pack else "векторный"}', 'ok')

    def __build_cursor_pack_menu(self, parent):
        '''Подменю «Набор»: семейства курсоров и векторный вариант'''
        packs = cursor_packs.list_packs()
        if not packs:
            return

        pack_menu = Menu(parent, tearoff=0)
        parent.add_cascade(label='Набор', menu=pack_menu)
        families = {}
        for key, pack in packs.items():
            families.setdefault(pack.family, []).append(pack)

        for family, items in families.items():
            if len(items) == 1:
                pack = items[0]
                pack_menu.add_radiobutton(label=pack.name, value=pack.key,
                                          variable=self.cursor_pack_var,
                                          command=lambda k=pack.key: self.set_cursor_pack(k))
                continue
            family_menu = Menu(pack_menu, tearoff=0)
            title = family.capitalize()
            pack_menu.add_cascade(label=title, menu=family_menu)
            for pack in items:
                family_menu.add_radiobutton(label=pack.name, value=pack.key,
                                            variable=self.cursor_pack_var,
                                            command=lambda k=pack.key: self.set_cursor_pack(k))

        pack_menu.add_separator()
        pack_menu.add_radiobutton(label='Векторный (без набора)', value='',
                                  variable=self.cursor_pack_var,
                                  command=lambda: self.set_cursor_pack(''))

    # --- Игровая сессия ------------------------------------------------------

    def new_game(self, difficulty: DifficultyType, side: SideType):
        '''Создать новую игру'''
        self.game = Game(
            self.canvas, X_SIZE, Y_SIZE, difficulty,
            update_callback=self.update_status,
            sounds_enabled=self.settings.sounds_enabled,
            player_side=side,
            auto_restart=False,
            game_over_callback=self.on_game_over,
            theme=self.theme,
            rules=self.rules,
            toast_callback=self.__toast,
            animate=True,
        )
        self.game.show_hover_hints = self.hover_var.get()
        self.game.set_show_coordinates(self.coords_var.get())
        self.difficulty_var.set(list(DifficultyType).index(difficulty))
        self.side_var.set(list(SideType).index(side))
        self.__fit_board()
        self.update_status()

    def restart_game(self):
        '''Новая игра с текущими настройками'''
        difficulty = _difficulty_by_index(self.difficulty_var.get())
        side = list(SideType)[self.side_var.get()]
        self.new_game(difficulty, side)
        self.__toast('Новая партия', 'ok')

    def restart_board(self):
        '''Перезапустить партию без смены настроек'''
        if self.game is not None:
            self.game.restart()
            self.__toast('Партия начата заново', 'ok')

    def set_difficulty(self, difficulty: DifficultyType):
        '''Сменить уровень сложности'''
        index = list(DifficultyType).index(difficulty)
        self.settings.difficulty = index
        if self.game is not None:
            self.game.set_difficulty(difficulty)
        self.update_status()
        self.__toast(f'Сложность: {difficulty.name_ru}', 'ok')

    def set_side(self, side: SideType):
        '''Сменить сторону игрока (партия перезапускается)'''
        self.settings.player_side = side
        self.new_game(_difficulty_by_index(self.difficulty_var.get()), side)
        self.__toast(f'Вы играете за {_side_name(side).lower()}', 'ok')

    def set_rules(self, rules: R.RuleSet):
        '''Сменить вариант правил (партия перезапускается)'''
        self.rules = rules
        self.rules_var.set(list(R.RULE_SETS).index(rules.key))
        self.settings.rules = rules.key
        if self.game is not None:
            self.game.set_rules(rules)
        self.__toast(f'Правила: {rules.name_ru}', 'ok')

    def undo_move(self):
        '''Отменить ход'''
        if self.game is None:
            return
        if self.game.undo():
            self.__toast('Ход отменён', 'info')
        else:
            self.__toast('Отменять пока нечего', 'warn')

    def show_hint(self):
        '''Показать подсказку'''
        if self.game is not None:
            self.game.show_hint()

    def hide_hint(self):
        '''Скрыть подсказку'''
        if self.game is not None:
            self.game.hide_hint()

    def cancel_thinking(self):
        '''Прервать расчёт ИИ'''
        if self.game is not None and self.game.is_thinking:
            self.game.cancel_thinking()
            self.__toast('Расчёт остановлен: ИИ сыграет найденный ход', 'warn')

    def offer_draw(self):
        '''Предложить ничью'''
        if self.game is None:
            return
        if self.game.offer_draw():
            self.__toast('Ничья по согласию', 'ok')
        else:
            self.__toast('ИИ отклонил ничью', 'warn')

    def resign(self):
        '''Сдаться'''
        if self.game is None or self.game.is_game_over:
            return
        self.game.resign()

    def on_game_over(self, winner_side, winner_name: str, reason: str):
        '''Показать итог партии тостом и подсветить статус'''
        if winner_side is None:
            self.__toast(f'Ничья. {reason}', 'info')
        else:
            player_won = winner_side == self.game.player_side
            kind = 'ok' if player_won else 'error'
            self.__toast(f'{winner_name} выиграли. {reason}'.strip(), kind)
        self.update_status()

    # --- Звук ----------------------------------------------------------------

    def __apply_saved_audio(self):
        '''Восстановить громкость и музыку из настроек'''
        manager = self.game.sound_manager
        manager.set_volume(self.settings.volume)
        if self.settings.music_enabled:
            manager.set_music_enabled(True)
        self.update_status()

    def toggle_sounds(self):
        '''Включить/выключить эффекты'''
        if self.game is None:
            return
        manager = self.game.sound_manager
        if not manager.available:
            self.__toast('Звук недоступен', 'warn')
            self.sounds_var.set(False)
            return
        manager.set_enabled(self.sounds_var.get())
        self.settings.sounds_enabled = manager.enabled
        self.sounds_var.set(manager.enabled)
        self.update_status()

    def toggle_music(self):
        '''Включить/выключить музыку'''
        if self.game is None:
            return
        manager = self.game.sound_manager
        if not manager.music_available:
            self.__toast('Музыка недоступна на этой платформе', 'warn')
            self.music_var.set(False)
            return
        manager.set_music_enabled(self.music_var.get())
        self.settings.music_enabled = manager.music_enabled
        self.music_var.set(manager.music_enabled)
        self.update_status()

    def set_volume(self, volume: int):
        '''Задать громкость эффектов и музыки'''
        if self.game is None:
            return
        manager = self.game.sound_manager
        manager.set_volume(volume)
        self.settings.volume = manager.volume
        self.volume_var.set(manager.volume)
        self.__toast(f'Громкость: {manager.volume}%', 'info')

    # --- Вид -----------------------------------------------------------------

    def flip_board(self):
        '''Перевернуть доску'''
        if self.game is not None:
            self.game.toggle_view()
            side = _side_name(self.game.view_side).lower()
            self.__toast(f'Доска со стороны {side}x', 'info')

    def __apply_hover_hint(self):
        '''Применить настройку подсветки ходов'''
        if self.game is not None:
            self.game.show_hover_hints = self.hover_var.get()

    def __apply_coordinates(self):
        '''Применить настройку координат'''
        if self.game is not None:
            self.game.set_show_coordinates(self.coords_var.get())

    # --- История -------------------------------------------------------------

    def goto_first(self):
        if self.game is not None:
            self.game.goto_first()

    def goto_last(self):
        if self.game is not None:
            self.game.goto_last()

    def step_back(self):
        if self.game is not None:
            self.game.step_back()

    def step_forward(self):
        if self.game is not None:
            self.game.step_forward()

    def __render_history(self):
        '''Перерисовать список ходов и отметить текущую позицию'''
        if self.game is None:
            return

        for row in self.__history_rows:
            row.destroy()
        self.__history_rows.clear()

        entries = self.game.history_entries[-40:]
        current = self.game.current_index
        theme = self.theme

        if not entries:
            label = Label(self.history_list, text='Ходов пока нет',
                          font=('Segoe UI', 9), anchor='w', bg=theme.panel_bg,
                          fg=theme.panel_muted)
            label.pack(fill='x')
            self.__history_rows.append(label)
            return

        for entry in entries:
            index = entry['index']
            marker = '▸ ' if index == current else '  '
            notation = entry['notation']
            label = Label(
                self.history_list,
                text=f'{marker}{index}. {notation}',
                font=('Segoe UI', 9, 'bold' if index == current else 'normal'),
                anchor='w', bg=theme.panel_bg,
                fg=theme.accent if index == current else theme.panel_fg,
                cursor='hand2',
            )
            label.pack(fill='x')
            label.bind('<Button-1>', lambda event, i=index: self.game.goto(i))
            self.__history_rows.append(label)

    # --- Статус --------------------------------------------------------------

    def update_status(self):
        '''Обновить панель статуса и историю'''
        if self.game is None:
            return

        if self.game.is_game_over:
            turn_text = 'Партия завершена'
        elif self.game.is_thinking:
            turn_text = 'ИИ думает…'
        elif self.game.is_player_turn:
            turn_text = 'Ваш ход'
        else:
            turn_text = 'Ход ИИ…'
        if self.game.is_browsing:
            turn_text = f'Просмотр ({self.game.current_index}/{self.game.positions_count - 1})'
        self.turn_label.config(text=turn_text)

        difficulty = _difficulty_by_index(self.difficulty_var.get())
        details = [difficulty.name_ru, self.rules.name_ru.lower()]
        if self.game.is_thinking:
            progress = self.game.search_progress
            if progress:
                depth, max_depth, _, score = progress
                details.append(f'глубина {depth}/{max_depth}')
            else:
                details.append('расчёт…')
        self.difficulty_label.config(text=' · '.join(details))

        self.score_label.config(
            text=f'⚪ {self.game.white_checkers_count}  ⚫ {self.game.black_checkers_count}'
        )

        manager = self.game.sound_manager
        sound = 'вкл' if manager.enabled else 'выкл'
        if not manager.music_available:
            music = 'нет'
        else:
            music = 'вкл' if manager.music_enabled else 'выкл'
        self.audio_label.config(text=f'♪ {sound}/{music} · {manager.volume}%')

        self.sounds_var.set(manager.enabled)
        self.music_var.set(manager.music_enabled)
        self.volume_var.set(manager.volume)

        self.__render_history()

    def __toast(self, text: str, kind: str = 'info'):
        '''Показать всплывающее сообщение'''
        self.__toasts.show(text, kind)

    # --- Справка -------------------------------------------------------------

    def show_hotkeys(self):
        '''Окно со списком горячих клавиш'''
        text = (
            f'{SHORTCUTS["new"]:<12} новая игра\n'
            f'{SHORTCUTS["restart"]:<12} начать заново\n'
            f'{SHORTCUTS["undo"]:<12} отменить ход\n'
            f'{SHORTCUTS["hint"]:<12} подсказка\n'
            f'{SHORTCUTS["flip"]:<12} перевернуть доску\n'
            f'{SHORTCUTS["back"]:<12} предыдущая позиция\n'
            f'{SHORTCUTS["forward"]:<12} следующая позиция\n'
            f'{SHORTCUTS["sound"]:<12} звуковые эффекты\n'
            f'{SHORTCUTS["music"]:<12} музыка\n'
            f'Esc{"":<9} скрыть подсказку\n'
            f'{SHORTCUTS["exit"]:<12} выход'
        )
        messagebox.showinfo('Горячие клавиши', text, parent=self.window)

    def show_about(self):
        '''Окно «О программе»'''
        messagebox.showinfo(
            'О программе',
            'Шашки на Python (Tkinter)\n\n'
            'ИИ: минимакс с альфа-бета отсечением,\n'
            'таблица транспозиций и итеративное углубление.\n\n'
            'Звук и музыка синтезируются на лету.',
            parent=self.window,
        )

    # --- Жизненный цикл ------------------------------------------------------

    def run(self):
        '''Запустить цикл событий'''
        self.window.mainloop()

    def close(self):
        '''Закрыть приложение, остановив музыку'''
        if self.game is not None:
            manager = self.game.sound_manager
            if manager.music_enabled:
                manager.set_music_enabled(False)
        self.window.destroy()


# Размер окна при старте: доля рабочего стола
MAX_WORK_WIDTH = 1040
MAX_WORK_HEIGHT = 900


def main():
    CheckersApp().run()


if __name__ == '__main__':
    main()
