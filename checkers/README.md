>Дальнейшая информация предназначена для разработки или для лучшего понимания кода

## Описание констант в файле constants.py
- PLAYER_SIDE - Определяет сторону, за которую играет игрок
- DEFAULT_DIFFICULTY - Уровень сложности, используемый по умолчанию
- X_SIZE и Y_SIZE - Определяют ширину и высоту поля в ячейках
- CELL_SIZE - Размер одной ячейки по умолчанию (при запуске окно подгоняет его под себя)
- ANIMATION_SPEED - Определяет скорость анимации перемещения шашек (больше = быстрее)
- MAX_HISTORY - Максимальное количество сохранённых позиций для отмены хода
- BORDER_WIDTH - Определяет ширину рамки обвода ячейки при наведении или выделении (должно быть чётным числом)
- MOVE_OFFSETS - Допустимые смещения (векторы) ходов шашек по диагонали
- WHITE_CHECKERS и BLACK_CHECKERS - Массивы типов шашек каждой стороны [обычная, дамка]
- <details><summary>Цвета</summary>

  - FIELD_COLORS - Определяет два цвета для ячеек сетки игрового поля
  - HOVER_BORDER_COLOR - Определяет цвет обводки ячейки при наведении на неё
  - SELECT_BORDER_COLOR - Определяет цвет обводки ячейки при выделении стоящей на ней шашки
  - POSIBLE_MOVE_CIRCLE_COLOR - Определяет цвет кружков, которые появляются на месте возможных ходов выбранной шашки

  > Цвета интерфейса живут в `theme.py`: `constants.py` хранит только значения, нужные на этапе инициализации поля.

</details>

## Описание перечислений (enums) в файле enums.py
- <details><summary>SideType - Тип стороны игры</summary>

  - WHITE - Сторона белых
  - BLACK - Сторона чёрных
  - opposite - Статический метод, возвращающий противоположную сторону

</details>

- <details><summary>CheckerType - Тип шашки</summary>

  - NONE - Отсутствие типа (ячейка без шашки)
  - WHITE_REGULAR - Белая шашка
  - WHITE_QUEEN - Белая дамка
  - BLACK_REGULAR - Чёрная шашка
  - BLACK_QUEEN - Чёрная дамка

</details>

- <details><summary>DifficultyType - Уровень сложности</summary>

  - EASY, MEDIUM, HARD, GRANDMASTER - Уровни сложности («Лёгкий», «Средний», «Сложный», «Гроссмейстер»)
  - depth - Предельная глубина просчёта (1, 3, 5, 8)
  - time_limit - Лимит времени на ход в секундах (0.35 / 1.2 / 3.0 / 6.0); поиск идёт итеративно и прерывается по времени
  - noise_scale - Гауссов шум к оценке позиции: чем больше, тем сильнее ИИ «ошибается» (0.5 / 0.15 / 0.03 / 0). На «Гроссмейстере» игра детерминирована
  - name_ru - Название уровня на русском

</details>

## Пути (paths.py)
- PROJECT_ROOT - Корень проекта (рядом с исполняемым файлом в собранной версии, иначе — родитель пакета checkers)
- ASSETS_DIR, CONFIG_PATH, ICON_PATH, ICON_ICO_PATH - Каталоги и файлы ресурсов
- asset_path(name) - Путь к файлу в каталоге assets
- Все пути абсолютны и не зависят от текущей рабочей директории

## Правила (rules.py)
- <details><summary>RuleSet - Набор правил игры</summary>

  - key, name_ru - Идентификатор и название варианта
  - queen_flying - Дамка-«летун»: ходит и бьёт по всей диагонали
  - men_capture_backward - Простая шашка может бить назад
  - turkish_strike - Турецкий удар: побитые шашки снимаются только после завершения серии
  - queen_must_capture - Дамка обязана бить, если взятие возможно
  - promote_ends_chain - Превращение в дамку завершает серию взятий
  - draw_quiet_halfmoves - Ничья после N полуходов без взятий и ходов дамкой (0 — не применять)
  - repetition_limit - Ничья при N-кратном повторении позиции

</details>
- RUSSIAN, INTERNATIONAL, ENGLISH - Готовые наборы; RULE_SETS - словарь по ключу, DEFAULT_RULES - набор по умолчанию, rules_by_key(key)
- required_moves(field, side, rules) - Обязательные взятия (с учётом `queen_must_capture`)
- optional_moves(field, side, rules) - Тихие ходы
- moves_for_side(field, side, rules) - Все ходы стороны
- capture_points(field, move) - Какие шашки снимает конкретный шаг
- position_key(field) - Ключ позиции для подсчёта повторов и таблицы транспозиций
- friendly_checkers / enemy_checkers / forward_offsets / is_queen / queen_type / promotes - Вспомогательные функции направления и типов

## Поиск хода (engine.py)
- Turn - Полный ход: кортеж шагов одной шашки, серия взятий считается одним ходом
- generate_turns(field, side, rules) - Все полные ходы, включая рекурсивные серии и турецкий удар
- apply_turn / undo_turn / apply_move - Применение и откат хода на копии поля
- turn_captures(field, turn) - Сколько шашек снимает ход (для порядка ходов)
- evaluate_field(field, side) - Эвристика: материал (шашка 1, дамка 3), центр, защита соседями, продвижение, эндшпиль ≤ 4 шашек, подвижность дамок
- <details><summary>Engine - Поиск лучшего хода</summary>

  - Поля: rules, max_depth, time_limit, noise_scale, cancel (threading.Event), progress (callback)
  - search(field, side, root_moves=None) -> SearchResult
  - Негамакс с альфа-бета отсечением и итеративным углублением от 1 до max_depth
  - Порядок ходов: взятия с большим числом побитых, превращения, затем «убийцы» (killers)
  - Таблица транспозиций ограничена MAX_TRANSPOSITION_ENTRIES (200 000), чтобы память не росла
  - SearchResult: move, turn, score, depth, nodes, elapsed, cancelled

</details>

## Тема и нотация
- <details><summary>theme.py</summary>

  - Theme - Неизменяемый набор цветов: доска, подсветки, панель, акцент, заглушки шашек
  - CLASSIC, DARK - Готовые темы, THEMES - словарь по ключу, DEFAULT_THEME, theme_by_key(key)

</details>
- <details><summary>notation.py</summary>

  - FILES = 'abcdefgh'
  - square_name(x, y, x_size, y_size, side) - Имя клетки с учётом переворота доски
  - move_notation / chain_notation - Запись хода и серии взятий (`a3-b4`, `c3:e5:g7`)

</details>
- <details><summary>toast.py</summary>

  - ToastManager(parent) - Плашки в правом нижнем углу окна вместо модальных диалогов
  - show(text, kind) с типами info / ok / warn / error; TOAST_MS - время жизни, MAX_TOASTS - сколько плашек держать
  - Плашки не перехватывают мышь: события проходят к доске

</details>

## Курсор (cursor.py и cursor_packs.py)
- <details><summary>cursor_packs.py - Готовые наборы из assets/cursors</summary>

  - CURSOR_PACKS_DIR - Каталог наборов, NATIVE_COLOR = 'native' (не перекрашивать)
  - list_packs() / pack_by_key(key) - Наборы по ключу вида `oreo/oreo_green`
  - CursorPack: key, name, source, folder, kinds (arrow / hand / wait), family
  - render(pack, kind, height, color) - Масштабированная картинка и hotspot
  - Наборы готовит tools/build_cursor_packs.py: он разбирает .cur/.ani из архивов, обрезает прозрачные поля и пишет PNG + meta.json

</details>
- <details><summary>cursor.py - Курсор на холсте</summary>

  - Tk на Windows не грузит курсоры из файла, поэтому системный курсор скрывается (`cursor='none'`), а свой рисуется элементами холста
  - CURSOR_COLORS - Палитра перекраски (native, accent, green, blue, cyan, purple, orange, pink, yellow, white)
  - ARROW / HAND / WAIT - Виды: обычная стрелка, «можно взять шашку», ожидание расчёта ИИ
  - CanvasCursor(canvas, style, tag) - move(x, y, kind), hide, set_color, set_size, set_pack, set_enabled
  - Перекраска идёт по яркости, поэтому светлые блики наборов сохраняются
  - Без наборов используется векторная форма (ARROW_SHAPE / HAND_SHAPE) со сглаживанием сплайном

</details>

## Описание полей и методов классов

- <details><summary>Field (field.py) - Класс поля</summary>

  - Поля
    - x_size - Ширина поля
    - y_size - Высота поля
    - size - Наибольшая из сторон поля
    - white_checkers_count и black_checkers_count - Количество белых и чёрных шашек на поле соответственно
    - white_score и black_score - Набранный счёт белых и чёрных соответственно (счёт = количество обычных шашек + количество дамок × 3)
  - Статические методы
    - copy - Создать независимую копию поля из экземпляра (используется минимаксом на каждом шаге, поэтому оптимизировано)
  - Методы
    - at - Получение шашки, стоящей по переданным координатам
    - type_at - Получение типа шашки, стоящей по переданным координатам
    - is_within - Определяет, находятся ли переданные координаты в пределах поля
    - get_score - Получение счёта для указанной стороны

</details>

- <details><summary>Checker (checker.py) - Класс шашки</summary>

  - Поля
    - type - Тип шашки
  - Методы
    - change_type - Изменить тип шашки

</details>

- <details><summary>Move (move.py) - Класс перемещения</summary>

  - Поля
    - from_x - Координата начальной точки перемещения по оси X
    - from_y - Координата начальной точки перемещения по оси Y
    - to_x - Координата конечной точки перемещения по оси X
    - to_y - Координата конечной перемещения по оси Y
  - Реализованы сравнение на равенство, хеширование и неравенство, поэтому ходы можно использовать в списках, множествах и словарях

</details>

- <details><summary>Point (point.py) - Класс точки на поле</summary>

  - Поля
    - x - Положение на поле по оси X
    - y - Положение на поле по оси Y
  - Ложь для «пустой» точки (-1, -1), поэтому проверка `if (point)` означает «точка задана»
  - Реализованы сравнение на равенство, хеширование и неравенство

</details>

- <details><summary>SoundManager (audio.py) - Звуковые эффекты и музыка</summary>

  - Один экземпляр на процесс: состояние общее для всех партий, новая игра не перезапускает музыку
  - Все звуки синтезируются программно при первом обращении и кэшируются во временном каталоге (`python-checkers-audio`); готовые WAV в репозитории не нужны
  - Эффекты: `move` (стук шашки), `capture` (двойной стук), `queen` (восходящее арпеджио), `win`, `lose`
  - Музыка: спокойный 12-секундный луп (аккорды + пентатоническая мелодия), зацикливается вручную
  - Громкость (10..100%) применяется к самой волне, поэтому не зависит от системного микшера; разная громкость — разные файлы кэша
  - Windows: эффекты через winsound, музыка через MCI (winmm). Алиас MCI доступен только из создавшего его потока, поэтому вся музыка живёт в отдельном потоке
  - Другие платформы: эффекты через playsound, если установлен; музыка недоступна
  - `available` / `music_available` — есть ли бэкенд; `enabled` / `music_enabled` — текущее состояние
  - `play(name)`, `set_enabled`, `toggle`, `set_music_enabled`, `toggle_music`, `set_volume`, `volume`

</details>

- <details><summary>Settings (settings.py) - Настройки в config.json</summary>

  - difficulty - Индекс уровня сложности (ограничен диапазоном DifficultyType)
  - player_side - Сторона игрока (`"white"` / `"black"`)
  - sounds_enabled, music_enabled - Флаги эффектов и музыки
  - volume - Громкость 10..100
  - theme, rules - Ключи темы и набора правил
  - custom_cursor - Свой курсор над доской вместо системного
  - cursor_color - Ключ палитры перекраски (`native` — цвет набора)
  - cursor_pack - Набор курсоров (`oreo/oreo_green`); пустая строка — векторная форма
  - save - Атомарная запись (через временный файл), повреждённый JSON не роняет игру
  - Значения из файла нормализуются: мусор заменяется значениями по умолчанию, числа ограничиваются диапазоном, несуществующий набор курсоров сбрасывается на набор по умолчанию

</details>

- <details><summary>Game (game.py) - Игровой процесс</summary>

  - Game не знает о конкретном окне: обновление статуса, тосты и конец партии приходят через колбэки, поэтому класс проверяется в selfcheck без показа окна
  - Ходы считаются полными (Turn): серия обязательных взятий — один ход; при незавершённой серии доступные ходы ограничиваются (__masked_moves)
  - resize(width, height) - Пересчитывает размер клетки (MIN_CELL..MAX_CELL) и отступы; координаты a–h / 1–8 рисуются вокруг доски
  - toggle_view / set_view_side - Переворот доски; при взгляде за чёрных нумерация клеток тоже переворачивается
  - __schedule_enemy_turn → __start_thinking (поток) → __poll_thinking (canvas.after) - ИИ считает в фоне, статус показывает прогресс, cancel_thinking останавливает расчёт
  - __check_draw - Ничья по N полуходам без взятий/ходов дамкой и по повторению позиции
  - resign / offer_draw - Сдача и предложение ничьей (ИИ соглашается при |оценка| ≤ 0.4)
  - История: Snapshot на каждую позицию, history_entries, current_index, is_browsing, goto / goto_first / goto_last / step_back / step_forward, undo
  - Анимация: __animate_move двигает шашку по шагам, __animate_captures плавно убирает побитые
  - get_hint / show_hint / hide_hint - Подсказка лучшего хода игрока
  - restart - Новая партия с теми же настройками; при auto_restart=False конец партии не перезапускает поле, а вызывает game_over_callback
  - set_theme / set_rules / set_difficulty / set_show_coordinates - Смена настроек на ходу
  - player_side, view_side, cell_size, padding, board_width/height, is_thinking, search_progress, is_player_turn, is_game_over, game_over_reason, move_count - Свойства для интерфейса
  - mouse_move / mouse_down - Обработка мыши: подсветка наведения, выбранной шашки, последнего хода и подсказки

</details>
