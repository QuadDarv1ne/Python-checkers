from tkinter import Tk, Canvas, PhotoImage, Menu, messagebox, IntVar, Frame, Label
from checkers.game import Game
from checkers.constants import X_SIZE, Y_SIZE, CELL_SIZE, DEFAULT_DIFFICULTY
from checkers.enums import DifficultyType

def main():
    # Создание окна
    main_window = Tk()
    main_window.title('Шашки')
    main_window.resizable(0, 0)
    main_window.iconphoto(False, PhotoImage(file='icon.png'))

    # Создание фрейма для статуса
    status_frame = Frame(main_window, bg='#f0f0f0')
    status_frame.pack(fill='x')

    # Метки статуса
    status_label = Label(status_frame, text='Ход: Белые', font=('Arial', 12, 'bold'), bg='#f0f0f0')
    status_label.pack(side='left', padx=10, pady=5)

    difficulty_label = Label(status_frame, text=f'Сложность: {DEFAULT_DIFFICULTY.name_ru}', font=('Arial', 10), bg='#f0f0f0')
    difficulty_label.pack(side='left', padx=10, pady=5)

    white_checkers_label = Label(status_frame, text='⚪ Белые: 12', font=('Arial', 10), bg='#f0f0f0')
    white_checkers_label.pack(side='left', padx=20, pady=5)

    black_checkers_label = Label(status_frame, text='⚫ Чёрные: 12', font=('Arial', 10), bg='#f0f0f0')
    black_checkers_label.pack(side='left', padx=10, pady=5)

    sound_label = Label(status_frame, text='🔊 Звук: Вкл', font=('Arial', 10), bg='#f0f0f0')
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
    difficulty_var = IntVar(value=list(DifficultyType).index(DEFAULT_DIFFICULTY))

    def update_status(game_instance):
        '''Обновление статуса игры'''
        white_count = game_instance.white_checkers_count
        black_count = game_instance.black_checkers_count
        white_checkers_label.config(text=f'⚪ Белые: {white_count}')
        black_checkers_label.config(text=f'⚫ Чёрные: {black_count}')
        
        if game_instance.is_player_turn:
            player_name = "Белые" if PLAYER_SIDE == SideType.WHITE else "Чёрные"
        else:
            player_name = "Чёрные" if PLAYER_SIDE == SideType.WHITE else "Белые"
        status_label.config(text=f'Ход: {player_name}')

    def set_difficulty(difficulty: DifficultyType):
        nonlocal game
        result = messagebox.askyesno("Новая игра", 
            f"Изменить уровень сложности на {difficulty.name_ru}?\nТекущая игра будет перезапущена.")
        if result:
            difficulty_var.set(list(DifficultyType).index(difficulty))
            game = Game(main_canvas, X_SIZE, Y_SIZE, difficulty, update_callback=lambda: update_status(game))
            difficulty_label.config(text=f'Сложность: {difficulty.name_ru}')
            update_status(game)

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
        nonlocal game
        game.toggle_sounds()
        sounds_text = "Вкл" if game.sounds_enabled else "Выкл"
        sound_label.config(text=f'🔊 Звук: {sounds_text}')

    def restart_game():
        nonlocal game
        result = messagebox.askyesno("Новая игра", "Начать новую игру?")
        if result:
            difficulty = list(DifficultyType)[difficulty_var.get()]
            game = Game(main_canvas, X_SIZE, Y_SIZE, difficulty, update_callback=lambda: update_status(game))
            update_status(game)

    game_menu.add_command(label="🔊 Звук", command=toggle_sounds)
    game_menu.add_command(label="Новая игра", command=restart_game)
    game_menu.add_separator()
    game_menu.add_command(label="Выход", command=main_window.quit)

    # Создание холста
    main_canvas = Canvas(main_window, width=CELL_SIZE * X_SIZE, height=CELL_SIZE * Y_SIZE)
    main_canvas.pack()

    from checkers.enums import SideType
    from checkers.constants import PLAYER_SIDE
    game = Game(main_canvas, X_SIZE, Y_SIZE, DEFAULT_DIFFICULTY, update_callback=lambda: update_status(game))

    main_canvas.bind("<Motion>", game.mouse_move)
    main_canvas.bind("<Button-1>", game.mouse_down)

    update_status(game)

    main_window.mainloop()

if __name__ == '__main__':
    main()
