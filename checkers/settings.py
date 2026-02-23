import json
from pathlib import Path

class Settings:
    """Управление настройками игры"""
    
    def __init__(self):
        self.__config_path = Path('config.json')
        self.__settings = self.__load()
    
    def __load(self) -> dict:
        '''Загрузить настройки из файла'''
        if self.__config_path.exists():
            try:
                with open(self.__config_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}
    
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
        self.set('difficulty', value)
        self.save()
    
    @property
    def sounds_enabled(self) -> bool:
        return self.get('sounds_enabled', True)
    
    @sounds_enabled.setter
    def sounds_enabled(self, value: bool):
        self.set('sounds_enabled', value)
        self.save()
