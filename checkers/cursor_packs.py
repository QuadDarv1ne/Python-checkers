"""Наборы курсоров из assets/cursors.

Каждый набор — папка с PNG (arrow/hand/wait) и meta.json, где записаны
hotspot и исходный размер. Файлы готовит tools/build_cursor_packs.py из
архивов .cur/.ani, поэтому игра не парсит бинарные форматы Windows.

Изображения кэшируются по (набор, вид, цвет, высота): при движении мыши
курсор перерисовывается часто, а ресайз — самая дорогая операция.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from checkers.paths import ASSETS_DIR

CURSOR_PACKS_DIR = ASSETS_DIR / 'cursors'

# Цвет «как в наборе» — не перекрашивать
NATIVE_COLOR = 'native'

_IMAGE_CACHE = {}
# Размер меняется при масштабировании окна, поэтому кэш ограничиваем
MAX_CACHE_ENTRIES = 96


@dataclass(frozen=True)
class CursorPack:
    '''Набор курсоров: ключ, название, источник и файлы по видам'''

    key: str
    name: str
    source: str
    folder: Path
    kinds: dict

    @property
    def family(self) -> str:
        '''Семейство набора (первая часть ключа)'''
        return self.key.split('/')[0]


def _read_pack(folder: Path) -> CursorPack:
    meta = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
    key = folder.parent.name + '/' + folder.name
    return CursorPack(key=key, name=meta.get('name', key),
                      source=meta.get('source', ''), folder=folder,
                      kinds=meta.get('kinds', {}))


def list_packs() -> dict:
    '''Все доступные наборы: ключ -> CursorPack'''
    packs = {}
    if not CURSOR_PACKS_DIR.exists():
        return packs
    for meta in sorted(CURSOR_PACKS_DIR.rglob('meta.json')):
        try:
            pack = _read_pack(meta.parent)
        except (OSError, ValueError):
            continue
        packs[pack.key] = pack
    return packs


def pack_by_key(key: str):
    '''Набор по ключу или None'''
    if not key:
        return None
    return list_packs().get(key)


def _solid_levels(image: Image.Image) -> list:
    '''Яркости непрозрачных пикселей'''
    alpha = image.getchannel('A')
    gray = image.convert('L')
    solid = alpha.point(lambda level: 255 if level > 200 else 0)
    histogram = gray.histogram(mask=solid)
    return [level for level, count in enumerate(histogram) for _ in range(count)]


def _tint(image: Image.Image, color: str) -> Image.Image:
    '''Перекрасить курсор в заданный цвет, сохранив блики и сглаживание.

    Заливка и контур перекрашиваются по-разному: у наливных наборов
    (Oreo) цветом становится тело курсора, у контурных (Minimalistic,
    Glib) — обводка, а тёмная заливка остаётся тёмной. Иначе цветной
    контурный набор темнел и не совпадал с названием цвета в меню.
    '''
    value = color.lstrip('#')
    r, g, b = (int(value[index:index + 2], 16) for index in (0, 2, 4))
    alpha = image.getchannel('A')
    gray = image.convert('L')

    levels = _solid_levels(image)
    if not levels:
        return image.copy()

    # Опорная яркость заливки — медиана, а не самый светлый блик
    fill_level = levels[len(levels) // 2]
    outline_only = fill_level < 60

    def convert(level: int, channel: int) -> int:
        if outline_only:
            # Контурный набор: светлый контур красим, заливку сохраняем
            strength = min(255, int(level * 255 / max(1, levels[int(len(levels) * 0.9)])))
            return min(255, (channel * strength + level * (255 - strength)) // 255)
        return min(255, level * channel // max(1, fill_level))

    channels = [gray.point(lambda level, c=c: convert(level, c)) for c in (r, g, b)]
    tinted = Image.merge('RGB', channels).convert('RGBA')
    tinted.putalpha(alpha)
    return tinted


def load_image(pack: CursorPack, kind: str, color: str = NATIVE_COLOR):
    '''Исходное изображение вида (без масштаба)'''
    cache_key = (pack.key, kind, color)
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]

    entry = pack.kinds.get(kind)
    if entry is None:
        return None
    path = pack.folder / entry['file']
    try:
        image = Image.open(path).convert('RGBA')
    except (OSError, ValueError):
        return None
    if color and color != NATIVE_COLOR:
        image = _tint(image, color)
    _IMAGE_CACHE[cache_key] = image
    return image


def render(pack: CursorPack, kind: str, height: float, color: str = NATIVE_COLOR):
    '''Изображение под размер курсора: PIL-картинка и hotspot'''
    entry = pack.kinds.get(kind)
    if entry is None:
        return None, (0, 0)
    image = load_image(pack, kind, color)
    if image is None:
        return None, (0, 0)

    target = max(8, int(round(height)))
    factor = target / image.height
    width = max(1, int(round(image.width * factor)))
    cache_key = (pack.key, kind, color, width, target)
    scaled = _IMAGE_CACHE.get(cache_key)
    if scaled is None:
        scaled = image.resize((width, target), Image.LANCZOS)
        if len(_IMAGE_CACHE) >= MAX_CACHE_ENTRIES:
            _IMAGE_CACHE.clear()
        _IMAGE_CACHE[cache_key] = scaled

    hotspot = entry.get('hotspot', [0, 0])
    return scaled, (hotspot[0] * factor, hotspot[1] * factor)
