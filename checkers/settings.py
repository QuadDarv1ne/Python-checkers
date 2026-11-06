import json
from pathlib import Path

class Settings:
    """Управление настройками игры"""
    
    def __init__(self):
        self.__config_path = Path('config.json')
        self.__settings = self.__load()
    
    def __load(self) -> dict:
        '''Загрузить настройки из файла'''
        settings = {}
        if self.__config_path.exists():
            try:
                with open(self.__config_path, 'r') as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, IOError):
                settings = {}

        # Приводим загруженные значения к допустимым
        if not isinstance(settings, dict):
            settings = {}
        try:
            settings['difficulty'] = max(0, min(3, int(settings.get('difficulty', 1))))
        except (TypeError, ValueError):
            settings['difficulty'] = 1
        settings['sounds_enabled'] = bool(settings.get('sounds_enabled', True))
        return settings
    
    def save(self):
        '''Сохранить настройки в файл'''
        try:
            with open(self.__config_path, 'w') as f:
                json.dump(self.__settings, f, indent=2)
        except IOError:
            pass
    
    def get(self, key: str, default=None):
        '''Получить значение настройки'''
        return self.__settings.get(key, default)
    
    def set(self, key: str, value):
        '''Установить значение настройки'''
        self.__settings[key] = value
    
    @property
    def difficulty(self) -> int:
        return self.get('difficulty', 1)  # Medium по умолчанию
    
    @difficulty.setter
    def difficulty(self, value: int):
        self.set('difficulty', max(0, min(3, value)))
        self.save()
    
    @property
    def sounds_enabled(self) -> bool:
        return self.get('sounds_enabled', True)
    
    @sounds_enabled.setter
    def sounds_enabled(self, value: bool):
        self.set('sounds_enabled', value)
        self.save()
