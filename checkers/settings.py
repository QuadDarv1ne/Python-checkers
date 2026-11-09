import json
import os
import tempfile
from pathlib import Path

from checkers.enums import DifficultyType
from checkers.paths import CONFIG_PATH

DEFAULT_DIFFICULTY_INDEX = list(DifficultyType).index(DifficultyType.MEDIUM)


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
                json.dump(self.__settings, f, indent=2, ensure_ascii=False)
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
