import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS_DIR = ROOT / 'assets'
DIST_DIR = ROOT / 'dist'


def run(command: list):
    '''Запустить команду и остановиться при ошибке'''
    print('>', ' '.join(command))
    subprocess.run(command, check=True, cwd=str(ROOT))


def main():
    system = platform.system()

    if system == 'Windows':
        icon = ROOT / 'icon.ico'
    elif system == 'Linux':
        icon = ROOT / 'icon.png'
    else:
        print(f'Неподдерживаемая система: {system}')
        return 1

    if not icon.exists():
        print(f'Не найден файл иконки: {icon}')
        return 1

    # Сборка
    command = [
        sys.executable, '-m', 'PyInstaller',
        '-F', '-w',
        '-i', str(icon),
        '--hidden-import=PIL._tkinter_finder',
        '--distpath', str(DIST_DIR),
        '--workpath', str(ROOT / 'build'),
        '--specpath', str(ROOT),
        str(ROOT / 'main.py'),
    ]
    # playsound нужен только вне Windows (там используется winsound)
    if system != 'Windows':
        command.insert(command.index('--distpath'), '--hidden-import=playsound')
    run(command)

    # Копирование ресурсов рядом с исполняемым файлом
    if ASSETS_DIR.exists():
        shutil.copytree(ASSETS_DIR, DIST_DIR / 'assets', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'icon.png', DIST_DIR / 'icon.png')

    print('Сборка завершена:', DIST_DIR)
    return 0


if __name__ == '__main__':
    sys.exit(main())

