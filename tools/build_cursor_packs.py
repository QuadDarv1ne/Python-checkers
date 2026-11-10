"""Собрать PNG-курсоры из архивов наборов в assets/cursors.

Скрипт нужен один раз (и при обновлении наборов): читает архивы из папки
`cursors/`, вырезает стрелку, лапку и ожидание, обрезает прозрачные поля и
сохраняет компактные PNG вместе с hotspot в meta.json.

Запуск: python tools/build_cursor_packs.py
"""
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image

ARCHIVES = ROOT / 'cursors'
OUTPUT = ROOT / 'assets' / 'cursors'

# Отступ вокруг содержимого, чтобы сглаженный край не обрезался
PADDING = 1


def ani_first_frame(data: bytes) -> bytes:
    '''Первый кадр .ani: внутри RIFF ACON лежат ICO-блоки'''
    if data[:4] != b'RIFF' or data[8:12] != b'ACON':
        raise ValueError('не ANI')
    position = 12
    while position + 8 <= len(data):
        chunk_id = data[position:position + 4]
        size = struct.unpack_from('<I', data, position + 4)[0]
        body = data[position + 8:position + 8 + size]
        if chunk_id == b'LIST' and body[:4] == b'fram':
            offset = 4
            while offset + 8 <= len(body):
                icon_id = body[offset:offset + 4]
                icon_size = struct.unpack_from('<I', body, offset + 4)[0]
                if icon_id == b'icon':
                    return body[offset + 8:offset + 8 + icon_size]
                offset += 8 + icon_size + (icon_size & 1)
        position += 8 + size + (size & 1)
    raise ValueError('в ANI нет кадров')


def decode_icon(data: bytes) -> tuple:
    '''Разобрать .ico/.cur вручную: Pillow теряет альфу у 32-битных курсоров'''
    if len(data) < 6:
        raise ValueError('слишком короткий файл')
    icon_type, count = struct.unpack_from('<HH', data, 2)
    if count == 0:
        raise ValueError('нет кадров')

    best = None
    for index in range(count):
        entry = 6 + 16 * index
        width, height, _, _, hot_x, hot_y, size, offset = struct.unpack_from(
            '<BBBBHHII', data, entry)
        width = width or 256
        height = height or 256
        if best is None or width * height > best[0] * best[1]:
            best = (width, height, hot_x, hot_y, size, offset)

    width, height, hot_x, hot_y, size, offset = best
    header = struct.unpack_from('<IiiHHIIiiII', data, offset)
    header_size, _, _, _, bits, compression = header[0], header[1], header[2], header[3], header[4], header[5]
    image_size = header[8]

    if bits != 32 or compression != 0:
        raise ValueError(f'неподдерживаемый формат: {bits} бит, сжатие {compression}')

    pixel_offset = offset + header_size
    stride = width * 4
    raw = data[pixel_offset:pixel_offset + stride * height]
    if len(raw) < stride * height:
        raise ValueError('недостаточно данных изображения')

    image = Image.frombytes('RGBA', (width, height), raw, 'raw', 'BGRA')
    image = image.transpose(Image.FLIP_TOP_BOTTOM)

    # У старых курсоров альфа может быть нулевой — тогда берём AND-маску
    if image.getchannel('A').getextrema()[1] == 0:
        mask_offset = pixel_offset + max(image_size, stride * height)
        mask = data[mask_offset:mask_offset + ((width + 7) // 8) * height]
        if len(mask) == ((width + 7) // 8) * height:
            alpha = Image.new('L', (width, height), 255)
            mask_stride = (width + 7) // 8
            for row in range(height):
                source_row = height - 1 - row
                bits_row = mask[source_row * mask_stride:(source_row + 1) * mask_stride]
                for column in range(width):
                    byte = bits_row[column // 8]
                    if byte & (0x80 >> (column % 8)):
                        alpha.putpixel((column, row), 0)
            image.putalpha(alpha)

    if icon_type == 1:
        hot_x = hot_y = 0
    return image, (hot_x, hot_y)


def read_cursor(path: Path) -> tuple:
    '''Прочитать .cur/.ani: вернуть изображение и hotspot'''
    data = path.read_bytes()
    if path.suffix.lower() == '.ani':
        return decode_icon(ani_first_frame(data))
    return decode_icon(data)


def prepare(path: Path) -> tuple:
    '''Обрезать прозрачные поля и пересчитать hotspot'''
    image, hotspot = read_cursor(path)
    alpha = image.getchannel('A')
    box = alpha.point(lambda value: 255 if value > 8 else 0).getbbox()
    if box is None:
        box = (0, 0, image.width, image.height)
    left = max(0, box[0] - PADDING)
    top = max(0, box[1] - PADDING)
    right = min(image.width, box[2] + PADDING)
    bottom = min(image.height, box[3] + PADDING)
    cropped = image.crop((left, top, right, bottom))
    return cropped, (hotspot[0] - left, hotspot[1] - top)


def save_pack(folder: Path, name: str, source: str, files: dict):
    '''Сохранить набор: PNG по видам и meta.json'''
    folder.mkdir(parents=True, exist_ok=True)
    kinds = {}
    for kind, path in files.items():
        if path is None or not path.exists():
            continue
        image, hotspot = prepare(path)
        file_name = f'{kind}.png'
        image.save(folder / file_name)
        kinds[kind] = {
            'file': file_name,
            'hotspot': [hotspot[0], hotspot[1]],
            'size': [image.width, image.height],
        }
    if not kinds:
        return False
    meta = {'name': name, 'source': source, 'kinds': kinds}
    (folder / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                      encoding='utf-8')
    print(f'  {folder.name}: {", ".join(kinds)}')
    return True


def unpack_zip(archive: Path, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target)
    return target


def unpack_rar(archive: Path, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    for exe in (r'C:\Program Files\WinRAR\UnRAR.exe',
                r'C:\Program Files (x86)\WinRAR\UnRAR.exe'):
        if Path(exe).exists():
            subprocess.run([exe, 'x', '-o+', str(archive), str(target)],
                           check=True, capture_output=True)
            return target
    raise SystemExit('Не найден UnRAR.exe — распакуйте архив вручную')


def build_minimalistic(base: Path):
    '''Minimalistic V5: четыре цвета, стрелка и лапка'''
    source = 'https://vsthemes.org/cursors/neon/76118-minimalistic-v5.html'
    for folder in sorted(base.iterdir()):
        if not folder.is_dir():
            continue
        key = folder.name.lower().replace(' ', '-')
        save_pack(
            OUTPUT / 'minimalistic' / key,
            f'Minimal V5 · {folder.name}',
            source,
            {
                'arrow': folder / 'Arrow.cur',
                'hand': folder / 'Hand.cur',
                'wait': folder / 'Wait.ani',
            },
        )


def build_oreo(base: Path):
    '''Oreo: указатель-капля в 13 цветах'''
    source = 'https://vsthemes.org/cursors/static/18096-oreo.html'
    for folder in sorted(base.iterdir()):
        if not folder.is_dir():
            continue
        key = folder.name.lower().replace(' ', '-')
        save_pack(
            OUTPUT / 'oreo' / key,
            f'Oreo · {folder.name.replace("oreo", "").strip(" _-") or "black"}',
            source,
            {
                'arrow': folder / 'normal-select.cur',
                'hand': folder / 'link-select.cur',
                'wait': folder / 'busy.ani',
            },
        )


def build_glib(base: Path):
    '''Glib Cur v3 (Rounded)'''
    source = 'https://vsthemes.org/cursors/'
    save_pack(
        OUTPUT / 'glib' / 'rounded',
        'Glib v3 · Rounded',
        source,
        {
            'arrow': base / 'Normal Select.cur',
            'hand': base / 'link.cur',
            'wait': base / 'busy.ani',
        },
    )


def main():
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    temp = Path(tempfile.mkdtemp(prefix='cursor-packs-'))
    print(f'временный каталог: {temp}')

    minimalistic = unpack_zip(ARCHIVES / 'minimalistic.zip', temp / 'minimalistic')
    oreo = unpack_zip(ARCHIVES / 'oreo.zip', temp / 'oreo')
    glib = unpack_rar(ARCHIVES / 'glib.rar', temp / 'glib')

    print('Minimalistic V5:')
    build_minimalistic(minimalistic)
    print('Oreo:')
    build_oreo(oreo / 'Windows')
    print('Glib:')
    build_glib(glib / 'Glib Cur v3 (Rounded)')

    total = sum(1 for _ in OUTPUT.rglob('*.png'))
    size = sum(path.stat().st_size for path in OUTPUT.rglob('*') if path.is_file())
    print(f'готово: {total} PNG, {size / 1024:.0f} КБ в {OUTPUT}')
    shutil.rmtree(temp, ignore_errors=True)


if __name__ == '__main__':
    main()
