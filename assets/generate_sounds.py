"""Генерация звуковых эффектов для игры"""
import wave
import struct
import math

def generate_tone(filename, frequency, duration, volume=0.5, fade_out=True):
    """Генерирует WAV файл с тоном заданной частоты"""
    sample_rate = 44100
    num_samples = int(sample_rate * duration)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        for i in range(num_samples):
            t = i / sample_rate
            value = volume * math.sin(2 * math.pi * frequency * t)
            
            # Fade out
            if fade_out:
                envelope = 1 - (i / num_samples) * 0.7
                value *= envelope
            
            # Pack as 16-bit signed integer
            packed = struct.pack('<h', int(value * 32767))
            wav_file.writeframes(packed)

# Звук обычного хода (короткий тихий тон)
generate_tone('move.wav', frequency=400, duration=0.1, volume=0.3)

# Звук взятия (более длинный с понижением частоты)
generate_tone('capture.wav', frequency=600, duration=0.15, volume=0.4)

# Звук превращения в дамку (приятный аккорд)
generate_tone('queen.wav', frequency=800, duration=0.2, volume=0.35)

print("Звуковые файлы сгенерированы!")
