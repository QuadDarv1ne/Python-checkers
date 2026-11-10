import json
import os
import tempfile
from pathlib import Path

from checkers.enums import DifficultyType, SideType
from checkers.cursor import CURSOR_COLORS, DEFAULT_CURSOR_COLOR
from checkers.cursor_packs import list_packs
from checkers.paths import CONFIG_PATH
from checkers.rules import DEFAULT_RULES, RULE_SETS
from checkers.theme import DEFAULT_THEME, THEMES

DEFAULT_DIFFICULTY_INDEX = list(DifficultyType).index(DifficultyType.MEDIUM)
DEFAULT_PLAYER_SIDE = SideType.WHITE
DEFAULT_VOLUME = 70
DEFAULT_CURSOR_PACK = 'minimalistic/koromiko'


def _clamp_difficulty(value) -> int:
    '''Привести значение сложности к допустимому индексу DifficultyType'''
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DIFFICULTY_INDEX
    last_index = len(DifficultyType) - 1
    return max(0, min(last_index, value))


def _coerce_bool(value, default: bool = False) -> bool:
    '''Привести значение к bool, корректно понимая строки "true"/"false"'''
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', '1', 'yes', 'on'):
            return True
        if lowered in ('false', '0', 'no', 'off', ''):
            return False
        return default
    if value is None:
        return default
    return bool(value)


def _clamp_volume(value) -> int:
    '''Привести громкость к диапазону 10..100'''
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_VOLUME
    return max(10, min(100, value))


def _coerce_key(value, options: dict, default: str) -> str:
    '''Проверить, что ключ есть в наборе допустимых значений'''
    if isinstance(value, str) and value in options:
        return value
    return default


def _coerce_cursor_pack(value) -> str:
    '''Проверить, что набор курсоров существует ('' — векторная форма)'''
    if value == '':
        return ''
    if isinstance(value, str) and value in list_packs():
        return value
    return DEFAULT_CURSOR_PACK


def _coerce_side(value) -> SideType:
    '''Привести значение стороны к SideType'''
    if isinstance(value, SideType):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('black', 'чёрные', 'черные'):
            return SideType.BLACK
        if lowered in ('white', 'белые'):
            return SideType.WHITE
    return DEFAULT_PLAYER_SIDE


class Settings:
    """Управление настройками игры"""

    def __init__(self):
        self.__config_path = CONFIG_PATH
        self.__settings = self.__load()

    def __load(self) -> dict:
        '''Загрузить настройки из файла'''
        settings = {}
        if self.__config_path.exists():
            try:
                with open(self.__config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, OSError, ValueError):
                settings = {}

        # Приводим загруженные значения к допустимым
        if not isinstance(settings, dict):
            settings = {}
        try:
            settings['difficulty'] = _clamp_difficulty(settings.get('difficulty', DEFAULT_DIFFICULTY_INDEX))
        except (TypeError, ValueError):
            settings['difficulty'] = DEFAULT_DIFFICULTY_INDEX
        settings['sounds_enabled'] = _coerce_bool(settings.get('sounds_enabled', True), default=True)
        settings['music_enabled'] = _coerce_bool(settings.get('music_enabled', True), default=True)
        settings['volume'] = _clamp_volume(settings.get('volume', DEFAULT_VOLUME))
        settings['player_side'] = _coerce_side(settings.get('player_side', DEFAULT_PLAYER_SIDE))
        settings['theme'] = _coerce_key(settings.get('theme'), THEMES, DEFAULT_THEME.key)
        settings['rules'] = _coerce_key(settings.get('rules'), RULE_SETS, DEFAULT_RULES.key)
        settings['custom_cursor'] = _coerce_bool(settings.get('custom_cursor', True), default=True)
        settings['cursor_color'] = _coerce_key(settings.get('cursor_color'), CURSOR_COLORS,
                                               DEFAULT_CURSOR_COLOR)
        settings['cursor_pack'] = _coerce_cursor_pack(settings.get('cursor_pack'))
        return settings

    def save(self):
        '''Атомарно сохранить настройки в файл.

        Запись идёт во временный файл в том же каталоге, затем он заменяет
        целевой файл. Это исключает повреждение config.json при сбое.
        '''
        tmp_path = None
        try:
            self.__config_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self.__config_path.parent), prefix='.config-', suffix='.tmp'
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.__settings, f, indent=2, ensure_ascii=False, default=self.__encode)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.__config_path)
            tmp_path = None
        except OSError:
            pass
        finally:
            # Удалить временный файл, если замена не удалась
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def __encode(value):
        '''Сериализовать значения, не поддерживаемые json напрямую'''
        if isinstance(value, SideType):
            return value.name.lower()
        raise TypeError(f'Неподдерживаемый тип настройки: {type(value).__name__}')

    def get(self, key: str, default=None):
        '''Получить значение настройки'''
        return self.__settings.get(key, default)

    def set(self, key: str, value):
        '''Установить значение настройки'''
        self.__settings[key] = value

    @property
    def difficulty(self) -> int:
        return self.get('difficulty', DEFAULT_DIFFICULTY_INDEX)

    @difficulty.setter
    def difficulty(self, value: int):
        self.set('difficulty', _clamp_difficulty(value))
        self.save()

    @property
    def sounds_enabled(self) -> bool:
        return self.get('sounds_enabled', True)

    @sounds_enabled.setter
    def sounds_enabled(self, value: bool):
        self.set('sounds_enabled', bool(value))
        self.save()

    @property
    def music_enabled(self) -> bool:
        return self.get('music_enabled', True)

    @music_enabled.setter
    def music_enabled(self, value: bool):
        self.set('music_enabled', bool(value))
        self.save()

    @property
    def volume(self) -> int:
        return self.get('volume', DEFAULT_VOLUME)

    @volume.setter
    def volume(self, value: int):
        self.set('volume', _clamp_volume(value))
        self.save()

    @property
    def player_side(self) -> SideType:
        return self.get('player_side', DEFAULT_PLAYER_SIDE)

    @player_side.setter
    def player_side(self, value: SideType):
        self.set('player_side', _coerce_side(value))
        self.save()

    @property
    def theme(self) -> str:
        return self.get('theme', DEFAULT_THEME.key)

    @theme.setter
    def theme(self, value: str):
        self.set('theme', _coerce_key(value, THEMES, DEFAULT_THEME.key))
        self.save()

    @property
    def rules(self) -> str:
        return self.get('rules', DEFAULT_RULES.key)

    @rules.setter
    def rules(self, value: str):
        self.set('rules', _coerce_key(value, RULE_SETS, DEFAULT_RULES.key))
        self.save()

    @property
    def custom_cursor(self) -> bool:
        return self.get('custom_cursor', True)

    @custom_cursor.setter
    def custom_cursor(self, value: bool):
        self.set('custom_cursor', bool(value))
        self.save()

    @property
    def cursor_color(self) -> str:
        return self.get('cursor_color', DEFAULT_CURSOR_COLOR)

    @cursor_color.setter
    def cursor_color(self, value: str):
        self.set('cursor_color', _coerce_key(value, CURSOR_COLORS, DEFAULT_CURSOR_COLOR))
        self.save()

    @property
    def cursor_pack(self) -> str:
        return self.get('cursor_pack', DEFAULT_CURSOR_PACK)

    @cursor_pack.setter
    def cursor_pack(self, value: str):
        self.set('cursor_pack', _coerce_cursor_pack(value))
        self.save()
