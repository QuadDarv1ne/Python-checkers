"""Синтез и воспроизведение звука: эффекты и фоновая музыка.

Готовых аудиофайлов в репозитории нет: эффекты и музыкальная тема
синтезируются при первом обращении и кэшируются во временном каталоге.
Громкость применяется к самой волне, поэтому не зависит от системного
микшера и одинаково работает для эффектов и музыки.

На Windows эффекты играет winsound, а музыка идёт через MCI (winmm) в
отдельном потоке: эти два механизма не прерывают друг друга. На других
платформах эффекты воспроизводятся через playsound, если он установлен,
а музыка недоступна.
"""
from __future__ import annotations

import array
import math
import os
import random
import sys
import tempfile
import threading
import wave
from pathlib import Path

from checkers.paths import asset_path

# Частота дискретизации: эффекты в полном качестве, музыка легче
SAMPLE_RATE = 44100
MUSIC_SAMPLE_RATE = 16000

# Версия синтеза: при изменении алгоритмов старый кэш игнорируется
SYNTH_VERSION = 2

# Каталог кэша во временной папке системы
CACHE_DIR = Path(tempfile.gettempdir()) / 'python-checkers-audio'

# Длительность музыкального лупа в секундах
MUSIC_LOOP_SECONDS = 12.0

DEFAULT_VOLUME = 70
MIN_VOLUME = 10
MAX_VOLUME = 100

# Имена эффектов, которые умеет синтезировать модуль
EFFECT_NAMES = ('move', 'capture', 'queen', 'win', 'lose')


# --- Синтез волн -----------------------------------------------------------

def _normalize(samples: list[float], peak: float) -> list[float]:
    '''Привести максимум сигнала к заданной амплитуде'''
    maximum = max((abs(value) for value in samples), default=0.0)
    if maximum == 0.0:
        return samples
    scale = peak / maximum
    return [value * scale for value in samples]


def _fade(samples: list[float], edge: int) -> list[float]:
    '''Плавно погасить края сигнала, чтобы не было щелчков'''
    if edge <= 0:
        return samples
    count = len(samples)
    edge = min(edge, count // 2)
    for i in range(edge):
        factor = i / edge
        samples[i] *= factor
        samples[count - 1 - i] *= factor
    return samples


def _tone(frequency: float, duration: float, amplitude: float = 0.3,
          attack: float = 0.01, decay: float = 3.2,
          harmonics: tuple[float, ...] = (1.0, 0.3),
          rate: int = SAMPLE_RATE, tail: float = 0.05) -> list[float]:
    '''Затухающий тон с гармониками и мягкой атакой'''
    count = int(rate * duration)
    attack_samples = max(1, int(rate * attack))
    tail_samples = max(1, int(rate * tail))
    steps = [2 * math.pi * frequency * index / rate for index in range(1, len(harmonics) + 1)]

    samples = [0.0] * count
    for i in range(count):
        t = i / rate
        rise = min(1.0, i / attack_samples)
        fall = min(1.0, (count - i) / tail_samples)
        value = 0.0
        for step, weight in zip(steps, harmonics):
            value += weight * math.sin(step * i)
        samples[i] = value * rise * fall * math.exp(-t * decay) * amplitude
    return samples


def _pad(frequency: float, duration: float, amplitude: float,
         rate: int = MUSIC_SAMPLE_RATE) -> list[float]:
    '''Мягкая «подушка» аккорда с плавным появлением и уходом'''
    count = int(rate * duration)
    attack = max(1, int(rate * 0.35))
    release = max(1, int(rate * 0.6))
    steps = [2 * math.pi * frequency * index / rate for index in (1, 2, 3)]

    samples = [0.0] * count
    for i in range(count):
        rise = min(1.0, i / attack)
        fall = min(1.0, (count - i) / release)
        value = (math.sin(steps[0] * i) * 1.0 +
                 math.sin(steps[1] * i) * 0.22 +
                 math.sin(steps[2] * i) * 0.08)
        samples[i] = value * rise * fall * amplitude
    return samples


def _click(duration: float, pitch: float, noise: float, seed: int) -> list[float]:
    '''Короткий деревянный стук шашки о доску'''
    rnd = random.Random(seed)
    count = int(SAMPLE_RATE * duration)
    step = 2 * math.pi * pitch / SAMPLE_RATE
    step_high = 2 * math.pi * pitch * 2.7 / SAMPLE_RATE

    samples = [0.0] * count
    for i in range(count):
        t = i / SAMPLE_RATE
        envelope = math.exp(-t * 38)
        body = math.sin(step * i) * 0.7 + math.sin(step_high * i) * 0.25
        grain = (rnd.random() * 2 - 1) * noise
        samples[i] = (body + grain) * envelope
    return samples


def _shift(samples: list[float], seconds: float, rate: int = SAMPLE_RATE) -> list[float]:
    '''Сдвинуть сигнал во времени'''
    return [0.0] * int(rate * seconds) + samples


def _mix(*tracks: list[float]) -> list[float]:
    '''Сложить сигналы'''
    length = max((len(track) for track in tracks), default=0)
    result = [0.0] * length
    for track in tracks:
        for i, value in enumerate(track):
            result[i] += value
    return result


# --- Готовые эффекты -------------------------------------------------------

def _effect_move() -> list[float]:
    return _normalize(_click(0.14, 235.0, 0.45, seed=1), 0.85)


def _effect_capture() -> list[float]:
    first = _click(0.13, 250.0, 0.5, seed=2)
    second = _shift(_click(0.17, 165.0, 0.55, seed=3), 0.07)
    return _normalize(_mix(first, second), 0.9)


def _effect_queen() -> list[float]:
    notes = (523.25, 659.25, 783.99, 1046.50)
    tracks = [_shift(_tone(freq, 0.55, 0.32, decay=2.4), index * 0.07)
              for index, freq in enumerate(notes)]
    return _normalize(_mix(*tracks), 0.85)


def _effect_win() -> list[float]:
    notes = (523.25, 659.25, 783.99, 1046.50, 1318.51)
    tracks = [_shift(_tone(freq, 0.6, 0.3, decay=1.9), index * 0.11)
              for index, freq in enumerate(notes)]
    return _normalize(_mix(*tracks), 0.85)


def _effect_lose() -> list[float]:
    notes = (523.25, 466.16, 415.30, 349.23)
    tracks = [_shift(_tone(freq, 0.65, 0.3, decay=1.8), index * 0.14)
              for index, freq in enumerate(notes)]
    return _normalize(_mix(*tracks), 0.8)


def _music_loop() -> list[float]:
    '''Спокойная фоновая тема: аккорды и пентатоническая мелодия'''
    rate = MUSIC_SAMPLE_RATE
    total = int(rate * MUSIC_LOOP_SECONDS)
    buffer = [0.0] * total

    def add(samples: list[float], start_seconds: float):
        offset = int(rate * start_seconds)
        limit = min(len(samples), total - offset)
        for i in range(limit):
            buffer[offset + i] += samples[i]

    # Аккорды: C - Dm - F - G - Am - F
    chords = (
        (0.0, (130.81, 196.00, 261.63)),
        (2.0, (146.83, 220.00, 293.66)),
        (4.0, (174.61, 261.63, 349.23)),
        (6.0, (196.00, 293.66, 392.00)),
        (8.0, (220.00, 329.63, 440.00)),
        (10.0, (174.61, 261.63, 349.23)),
    )
    for start, frequencies in chords:
        for frequency in frequencies:
            add(_pad(frequency, 2.0, 0.16), start)

    melody = (
        (0.0, 523.25), (0.5, 587.33), (1.0, 659.25), (1.5, 587.33),
        (2.0, 440.00), (2.5, 523.25), (3.0, 587.33), (3.5, 523.25),
        (4.0, 349.23), (4.5, 440.00), (5.0, 523.25), (5.5, 440.00),
        (6.0, 392.00), (6.5, 440.00), (7.0, 493.88), (7.5, 440.00),
        (8.0, 440.00), (8.5, 523.25), (9.0, 659.25), (9.5, 587.33),
        (10.0, 523.25), (10.5, 440.00), (11.0, 392.00), (11.5, 349.23),
    )
    for start, frequency in melody:
        add(_tone(frequency, 0.5, 0.11, attack=0.02, decay=2.2,
                  harmonics=(1.0, 0.18), rate=rate), start)

    return _normalize(buffer, 0.6)


_GENERATORS = {
    'move': _effect_move,
    'capture': _effect_capture,
    'queen': _effect_queen,
    'win': _effect_win,
    'lose': _effect_lose,
    'music': _music_loop,
}


# --- Кэш готовых файлов ----------------------------------------------------

def _write_wav(path: Path, samples: list[float], gain: float,
               rate: int = SAMPLE_RATE, fade_ms: float = 1.5):
    '''Записать сигнал в WAV с учётом громкости, не оставляя недописанных файлов'''
    edge = int(rate * fade_ms / 1000) if fade_ms else 0
    samples = _fade(list(samples), edge)

    data = array.array('h', (
        int(max(-1.0, min(1.0, value * gain)) * 32767) for value in samples
    ))
    if sys.byteorder == 'big':
        data.byteswap()

    tmp_path = path.with_name(path.name + '.tmp')
    with wave.open(str(tmp_path), 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(data.tobytes())
    os.replace(tmp_path, path)


def cached_wav(name: str, volume: int) -> Path | None:
    '''Путь к готовому WAV нужной громкости (синтез при первом обращении)'''
    generator = _GENERATORS.get(name)
    if generator is None:
        return None

    rate = MUSIC_SAMPLE_RATE if name == 'music' else SAMPLE_RATE
    target = CACHE_DIR / f'{name}-v{SYNTH_VERSION}-g{int(volume)}.wav'
    if target.exists():
        return target

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _write_wav(target, generator(), int(volume) / 100, rate=rate,
                   fade_ms=0.0 if name == 'music' else 1.5)
    except (OSError, ValueError, wave.Error):
        return None
    return target


def cleanup_cache():
    '''Удалить файлы прошлых версий синтеза, не мешая текущим'''
    try:
        if not CACHE_DIR.exists():
            return
        current = f'-v{SYNTH_VERSION}-'
        for path in CACHE_DIR.glob('*.wav'):
            if current not in path.name:
                try:
                    path.unlink()
                except OSError:
                    pass
    except OSError:
        pass


# --- Бэкенды воспроизведения ----------------------------------------------

class _WindowsBackend:
    '''winsound для эффектов и MCI для музыки: механизмы не конфликтуют'''

    supports_music = True

    def __init__(self):
        import ctypes
        import winsound

        self.__winsound = winsound
        self.__winmm = ctypes.windll.winmm
        self.__buffer = ctypes.create_unicode_buffer(256)
        self.__lock = threading.Lock()

    def play_effect(self, path: str):
        try:
            self.__winsound.PlaySound(
                path,
                self.__winsound.SND_FILENAME | self.__winsound.SND_ASYNC | self.__winsound.SND_NODEFAULT,
            )
        except RuntimeError:
            # Файл повреждён или устройство занято — звук не критичен
            pass

    def mci(self, command: str) -> tuple[int, str]:
        '''Выполнить команду MCI. Алиас доступен только из создавшего его потока'''
        with self.__lock:
            code = self.__winmm.mciSendStringW(command, self.__buffer, 256, None)
            return code, self.__buffer.value


class _PlaysoundBackend:
    '''Запасной бэкенд для не-Windows: только эффекты'''

    supports_music = False

    def __init__(self):
        from playsound import playsound
        self.__playsound = playsound

    def play_effect(self, path: str):
        try:
            threading.Thread(target=self.__playsound, args=(path,), daemon=True).start()
        except Exception:
            pass


def _create_backend():
    try:
        return _WindowsBackend()
    except (ImportError, AttributeError):
        pass
    try:
        return _PlaysoundBackend()
    except ImportError:
        return None


# --- Менеджер звука --------------------------------------------------------

class SoundManager:
    '''Единый на процесс менеджер эффектов и фоновой музыки.

    Один экземпляр на приложение: новая партия не перезапускает музыку,
    а состояние (включено/выключено, громкость) общее для всех игр.
    '''

    SOUND_FILES = EFFECT_NAMES

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.__backend = _create_backend()
        self.__enabled = True
        self.__music_enabled = False
        self.__volume = DEFAULT_VOLUME
        self.__effect_cache: dict[tuple[str, int], Path] = {}

        self.__music_thread = None
        self.__music_stop = None

        cleanup_cache()

    # -- Эффекты --

    @property
    def available(self) -> bool:
        '''Есть ли бэкенд и чем воспроизводить эффекты'''
        if self.__backend is None:
            return False
        return bool(self.__effect_path('move'))

    def __effect_path(self, name: str) -> Path | None:
        '''Путь к эффекту нужной громкости с откатом на файл из assets'''
        if name not in EFFECT_NAMES:
            return None

        key = (name, self.__volume)
        cached = self.__effect_cache.get(key)
        if cached is not None and cached.exists():
            return cached

        path = cached_wav(name, self.__volume)
        if path is None:
            # Синтез недоступен — используем готовый ассет, если он есть
            fallback = asset_path(f'{name}.wav')
            path = fallback if fallback.exists() else None

        if path is not None:
            self.__effect_cache[key] = path
        return path

    def play(self, sound_name: str):
        '''Воспроизвести эффект, не блокируя игровой цикл'''
        if not self.__enabled or self.__backend is None:
            return

        path = self.__effect_path(sound_name)
        if path is not None:
            self.__backend.play_effect(str(path))

    def toggle(self):
        '''Переключить эффекты'''
        if not self.available:
            return
        self.__enabled = not self.__enabled

    def set_enabled(self, enabled: bool):
        '''Явно включить или выключить эффекты'''
        self.__enabled = bool(enabled) and self.available

    @property
    def enabled(self) -> bool:
        return self.__enabled

    @property
    def enabled_str(self) -> str:
        if not self.available:
            return "Недоступен"
        return "Вкл" if self.__enabled else "Выкл"

    # -- Громкость --

    @property
    def volume(self) -> int:
        '''Громкость в процентах'''
        return self.__volume

    def set_volume(self, volume: int):
        '''Задать громкость; музыка перезапускается на новом уровне'''
        try:
            volume = int(volume)
        except (TypeError, ValueError):
            return
        volume = max(MIN_VOLUME, min(MAX_VOLUME, volume))
        if volume == self.__volume:
            return

        self.__volume = volume
        self.__effect_cache.clear()
        if self.__music_enabled:
            self.__restart_music()

    # -- Музыка --

    @property
    def music_available(self) -> bool:
        '''Поддерживает ли платформа фоновую музыку'''
        return (self.__backend is not None
                and getattr(self.__backend, 'supports_music', False)
                and 'music' in _GENERATORS)

    @property
    def music_enabled(self) -> bool:
        return self.__music_enabled

    @property
    def music_enabled_str(self) -> str:
        if not self.music_available:
            return "Недоступна"
        return "Вкл" if self.__music_enabled else "Выкл"

    def set_music_enabled(self, enabled: bool):
        '''Включить или выключить фоновую музыку'''
        enabled = bool(enabled) and self.music_available
        if enabled == self.__music_enabled:
            return
        self.__music_enabled = enabled
        if enabled:
            self.__start_music()
        else:
            self.__stop_music()

    def toggle_music(self):
        '''Переключить музыку'''
        self.set_music_enabled(not self.__music_enabled)

    def __start_music(self):
        if self.__music_thread is not None:
            return
        self.__music_stop = threading.Event()
        self.__music_thread = threading.Thread(
            target=self.__music_worker,
            args=(self.__music_stop, self.__volume),
            daemon=True,
            name='checkers-music',
        )
        self.__music_thread.start()

    def __stop_music(self):
        stop = self.__music_stop
        self.__music_stop = None
        self.__music_thread = None
        if stop is not None:
            # Поток музыки сам останавливает и закрывает свой MCI-алиас
            stop.set()

    def __restart_music(self):
        self.__stop_music()
        if self.__music_enabled:
            self.__start_music()

    def __music_worker(self, stop: threading.Event, volume: int):
        '''Синтез и зацикленное воспроизведение музыки в отдельном потоке.

        Все команды MCI выполняются только здесь: алиас принадлежит потоку,
        который его открыл, и из других потоков недоступен.
        '''
        path = cached_wav('music', volume)
        if path is None:
            self.__music_enabled = False
            return

        mci = getattr(self.__backend, 'mci', None)
        if mci is None:
            self.__music_enabled = False
            return

        alias = f'checkers_music_{os.getpid()}'
        mci(f'close {alias}')
        code, _ = mci(f'open "{path}" type waveaudio alias {alias}')
        if code != 0:
            self.__music_enabled = False
            return

        if mci(f'play {alias} from 0')[0] != 0:
            mci(f'close {alias}')
            self.__music_enabled = False
            return

        # MCI для waveaudio не умеет repeat, поэтому луп держим сами
        while not stop.wait(0.35):
            code, mode = mci(f'status {alias} mode')
            if code != 0 or mode.strip() == 'stopped':
                if mci(f'play {alias} from 0')[0] != 0:
                    break

        mci(f'stop {alias}')
        mci(f'close {alias}')
