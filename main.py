from tkinter import Tk, Canvas, PhotoImage, Menu, messagebox, IntVar, Frame, Label

from checkers.game import Game
from checkers.constants import X_SIZE, Y_SIZE, CELL_SIZE, PLAYER_SIDE
from checkers.enums import DifficultyType, SideType
from checkers.settings import Settings
from checkers.paths import ICON_PATH


def _set_icon(window: Tk):
    '''Установить иконку окна, если файл доступен'''
    try:
        if ICON_PATH.exists():
            icon = PhotoImage(file=str(ICON_PATH))
            window.iconphoto(False, icon)
            # Сохранить ссылку, чтобы сборщик мусора не удалил изображение
            window._icon_image = icon
    except Exception:
        # Иконка не критична для работы приложения
        pass


def _difficulty_by_index(index: int) -> DifficultyType:
    '''Получить уровень сложности по индексу с защитой от некорректного значения'''
    difficulties = list(DifficultyType)
    if not isinstance(index, int) or not (0 <= index < len(difficulties)):
        index = 0
    return difficulties[index]


def main():
    # Загрузка настроек
    settings = Settings()

    # Создание окна
    main_window = Tk()
    main_window.title('Шашки')
    main_window.resizable(0, 0)
    _set_icon(main_window)

    # Создание фрейма для статуса
    status_frame = Frame(main_window, bg='#f0f0f0')
    status_frame.pack(fill='x')

    # Метки статуса
    status_label = Label(status_frame, text='Ход: Белые', font=('Arial', 12, 'bold'), bg='#f0f0f0')
    status_label.pack(side='left', padx=10, pady=5)

    saved_difficulty = _difficulty_by_index(settings.difficulty)
    difficulty_label = Label(status_frame, text=f'Сложность: {saved_difficulty.name_ru}', font=('Arial', 10), bg='#f0f0f0')
    difficulty_label.pack(side='left', padx=10, pady=5)

    white_checkers_label = Label(status_frame, text='⚪ Белые: 12', font=('Arial', 10), bg='#f0f0f0')
    white_checkers_label.pack(side='left', padx=20, pady=5)

    black_checkers_label = Label(status_frame, text='⚫ Чёрные: 12', font=('Arial', 10), bg='#f0f0f0')
    black_checkers_label.pack(side='left', padx=10, pady=5)

    sounds_text = "Вкл" if settings.sounds_enabled else "Выкл"
    sound_label = Label(status_frame, text=f'🔊 Звук: {sounds_text}', font=('Arial', 10), bg='#f0f0f0')
    sound_label.pack(side='left', padx=20, pady=5)

    # Создание меню
    main_menu = Menu(main_window)
    main_window.config(menu=main_menu)

    # Меню "Игра"
    game_menu = Menu(main_menu, tearoff=0)
    main_menu.add_cascade(label="Игра", menu=game_menu)

    # Меню "Сложность"
    difficulty_menu = Menu(game_menu, tearoff=0)
    game_menu.add_cascade(label="Сложность", menu=difficulty_menu)

    # Переменная для хранения текущего уровня сложности
    difficulty_var = IntVar(value=settings.difficulty)

    # Создание холста
    main_canvas = Canvas(main_window, width=CELL_SIZE * X_SIZE, height=CELL_SIZE * Y_SIZE)
    main_canvas.pack()

    # Изменяемый контейнер для текущей игры
    game = [None]

    def update_status():
        '''Обновление статуса игры'''
        current_game = game[0]
        if current_game is None:
            return

        white_count = current_game.white_checkers_count
        black_count = current_game.black_checkers_count
        white_checkers_label.config(text=f'⚪ Белые: {white_count}')
        black_checkers_label.config(text=f'⚫ Чёрные: {black_count}')

        if current_game.is_player_turn:
            player_name = "Белые" if PLAYER_SIDE == SideType.WHITE else "Чёрные"
        else:
            player_name = "Чёрные" if PLAYER_SIDE == SideType.WHITE else "Белые"
        status_label.config(text=f'Ход: {player_name}')

    def on_update():
        update_status()

    def new_game(difficulty: DifficultyType):
        '''Создать новую игру с указанным уровнем сложности'''
        game[0] = Game(main_canvas, X_SIZE, Y_SIZE, difficulty, update_callback=on_update, sounds_enabled=settings.sounds_enabled)
        difficulty_label.config(text=f'Сложность: {difficulty.name_ru}')
        update_status()

    def set_difficulty(difficulty: DifficultyType):
        result = messagebox.askyesno("Новая игра",
            f"Изменить уровень сложности на {difficulty.name_ru}?\nТекущая игра будет перезапущена.")
        if result:
            difficulty_index = list(DifficultyType).index(difficulty)
            difficulty_var.set(difficulty_index)
            settings.difficulty = difficulty_index
            new_game(difficulty)

    # Добавление уровней сложности
    for diff in DifficultyType:
        difficulty_menu.add_radiobutton(
            label=diff.name_ru,
            value=list(DifficultyType).index(diff),
            variable=difficulty_var,
            command=lambda d=diff: set_difficulty(d)
        )

    game_menu.add_separator()

    def toggle_sounds():
        game[0].toggle_sounds()
        settings.sounds_enabled = game[0].sounds_enabled
        sounds_text = "Вкл" if game[0].sounds_enabled else "Выкл"
        sound_label.config(text=f'🔊 Звук: {sounds_text}')

    def show_hint():
        game[0].show_hint()

    def undo_move():
        game[0].undo()

    def restart_game():
        result = messagebox.askyesno("Новая игра", "Начать новую игру?")
        if result:
            difficulty = _difficulty_by_index(difficulty_var.get())
            new_game(difficulty)

    game_menu.add_command(label="↩ Отменить ход", command=undo_move)
    game_menu.add_command(label="💡 Подсказка", command=show_hint)
    game_menu.add_command(label="🔊 Звук", command=toggle_sounds)
    game_menu.add_command(label="Новая игра", command=restart_game)
    game_menu.add_separator()
    game_menu.add_command(label="Выход", command=main_window.quit)

    # Привязки обращаются к текущей игре через контейнер, поэтому перезапуск их не ломает
    main_canvas.bind("<Motion>", lambda event: game[0].mouse_move(event))
    main_canvas.bind("<Button-1>", lambda event: game[0].mouse_down(event))

    # Горячие клавиши
    main_window.bind("<Control-z>", lambda e: game[0].undo())        # Отменить ход
    main_window.bind("<Control-h>", lambda e: game[0].show_hint())   # Подсказка
    main_window.bind("<Control-n>", lambda e: restart_game())        # Новая игра
    main_window.bind("<Control-s>", lambda e: toggle_sounds())       # Звук
    main_window.bind("<Escape>", lambda e: game[0].hide_hint())      # Скрыть подсказку

    # Первая игра
    new_game(saved_difficulty)

    main_window.mainloop()

if __name__ == '__main__':
    main()
