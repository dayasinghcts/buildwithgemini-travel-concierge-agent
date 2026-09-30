import math
import struct
import wave
from pathlib import Path

# Audio settings
SAMPLE_RATE = 44100
DURATION = 25  # seconds
BPM = 85
BEAT_DUR = 60.0 / BPM
BAR_DUR = BEAT_DUR * 4

# Chord progression (frequencies in Hz for 7th chords):
# Cmaj7 (C4, E4, G4, B4): [261.63, 329.63, 392.00, 493.88]
# Am7 (A3, C4, E4, G4):   [220.00, 261.63, 329.63, 392.00]
# Fmaj7 (F3, A3, C4, E4): [174.61, 220.00, 261.63, 329.63]
# G7 (G3, B3, D4, F4):     [196.00, 246.94, 293.66, 349.23]

CHORDS = [
    ([261.63, 329.63, 392.00, 493.88], 130.81),  # Cmaj7, Bass C3
    ([220.00, 261.63, 329.63, 392.00], 110.00),  # Am7, Bass A2
    ([174.61, 220.00, 261.63, 329.63], 87.31),   # Fmaj7, Bass F2
    ([196.00, 246.94, 293.66, 349.23], 98.00),   # G7, Bass G2
]

def synth_sample(t, bar_time, beat_time):
    # Determine chord for current bar
    chord_idx = int((t / BAR_DUR) % len(CHORDS))
    freqs, bass_freq = CHORDS[chord_idx]

    # Warm E-Piano Chord (Triangle + Sine with subtle chorus)
    chord_val = 0.0
    for f in freqs:
        # Subtle vibrato
        vib = 1.0 + 0.003 * math.sin(2 * math.pi * 5.0 * t)
        phase = 2 * math.pi * f * vib * t
        # Triangle wave approximation
        tri = (4.0 / math.pi) * (math.sin(phase) - (1.0/9.0)*math.sin(3*phase) + (1.0/25.0)*math.sin(5*phase))
        # Soft envelope at beat start
        env = math.exp(-3.0 * (beat_time % BEAT_DUR))
        chord_val += tri * (0.15 + 0.85 * env)

    chord_val /= len(freqs)

    # Sub Bass
    bass_phase = 2 * math.pi * bass_freq * t
    bass_val = math.sin(bass_phase) * 0.4

    # Lo-Fi Beat
    beat_in_bar = (t % BAR_DUR) / BEAT_DUR  # 0.0 to 4.0
    drum_val = 0.0

    # Kick on beat 0 and 2.5
    kick_time1 = (beat_in_bar - 0.0) * BEAT_DUR
    kick_time2 = (beat_in_bar - 2.5) * BEAT_DUR
    for kt in [kick_time1, kick_time2]:
        if 0 <= kt < 0.15:
            kick_freq = 120.0 * math.exp(-25.0 * kt)
            kick_env = math.exp(-15.0 * kt)
            drum_val += math.sin(2 * math.pi * kick_freq * kt) * kick_env * 0.6

    # Snare / Rimshot on beat 1 and 3
    snare_time1 = (beat_in_bar - 1.0) * BEAT_DUR
    snare_time2 = (beat_in_bar - 3.0) * BEAT_DUR
    for st in [snare_time1, snare_time2]:
        if 0 <= st < 0.12:
            # White noise approximation
            noise = (math.sin(12345.67 * st) * 43758.5453) % 1.0 - 0.5
            snare_env = math.exp(-20.0 * st)
            drum_val += noise * snare_env * 0.3

    # Hi-Hat on 8th notes
    hat_time = (beat_in_bar % 0.5) * BEAT_DUR
    if 0 <= hat_time < 0.04:
        noise = (math.sin(98765.43 * hat_time) * 12345.67) % 1.0 - 0.5
        hat_env = math.exp(-60.0 * hat_time)
        drum_val += noise * hat_env * 0.12

    # Mix total
    total = (chord_val * 0.35) + (bass_val * 0.25) + (drum_val * 0.4)

    # Master gain & soft limiter
    total = math.tanh(total * 1.2) * 0.8
    return total

def generate_lofi_wav(output_path: str):
    num_samples = int(SAMPLE_RATE * DURATION)
    with wave.open(output_path, "w") as wav_file:
        wav_file.setnchannels(2)  # Stereo
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(SAMPLE_RATE)

        frames = bytearray()
        for i in range(num_samples):
            t = i / SAMPLE_RATE
            bar_time = t % BAR_DUR
            beat_time = t % BEAT_DUR

            # Fade in / fade out
            fade = 1.0
            if t < 1.0:
                fade = t
            elif t > DURATION - 1.0:
                fade = DURATION - t

            s = synth_sample(t, bar_time, beat_time) * fade
            sample_int = max(-32768, min(32767, int(s * 32767)))

            # Stereo frame (left, right)
            frames.extend(struct.pack("<h", sample_int))
            frames.extend(struct.pack("<h", sample_int))

        wav_file.writeframes(frames)
    print(f"Generated upbeat lo-fi audio track at: {output_path}")

if __name__ == "__main__":
    out_wav = "/config/Desktop/Session1/travel-concierge-agent/upbeat_lofi.wav"
    generate_lofi_wav(out_wav)
