"""Централизованные пути проекта.

Позволяют запускать игру из любой рабочей директории:
все ресурсы ищутся относительно корня проекта (или каталога исполняемого
файла в собранном PyInstaller-приложении), а не текущего каталога.
"""
import sys
from pathlib import Path


def _project_root() -> Path:
    '''Определить корень проекта для обычного и собранного запуска'''
    if getattr(sys, 'frozen', False):
        # Собранный PyInstaller: ресурсы лежат рядом с исполняемым файлом
        return Path(sys.executable).resolve().parent
    # Обычный запуск: корень — директория, содержащая пакет checkers/
    return Path(__file__).resolve().parent.parent


# Корень проекта
PROJECT_ROOT = _project_root()

# Каталоги и файлы ресурсов
ASSETS_DIR = PROJECT_ROOT / 'assets'
CONFIG_PATH = PROJECT_ROOT / 'config.json'
ICON_PATH = PROJECT_ROOT / 'icon.png'
ICON_ICO_PATH = PROJECT_ROOT / 'icon.ico'


def asset_path(name: str) -> Path:
    '''Путь к файлу в каталоге assets'''
    return ASSETS_DIR / name

