"""Offline generator for the music bed: high-energy hybrid trap with orchestral hits.

Pure numpy synthesis, no samples, no network. Deterministic (fixed seed).
    animative music <slug>      # writes assets/sound/music/bed.wav

Shape: 140 BPM (half-time feel), D minor, 112 bars = 192 s, 44.1 kHz stereo 16-bit.
Sections (bars): intro 8 | A 16 | B 16 | break 8 | A 16 | B 16 | break 8 | A 16 | outro 8.
Layers: 808 sub kick with pitch glide, clap/snare on 3, hi-hats with 1/16 and triplet rolls,
orchestral hits (brass-like saw stack + timpani + low string) on phrase downbeats,
string ostinato (band-limited saws), low pad, noise risers into each B section.
Ends on a 4-bar fade. Any A or B section (16 bars, bar = 1.714 s) can be cut and looped on bar lines.
No normalisation beyond a fixed master gain chosen to avoid clipping.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 140
BEAT = 60.0 / BPM
BAR = 4 * BEAT
NBARS = 112
rng = np.random.default_rng(20261018)
N = round(NBARS * BAR * SR)
L = np.zeros(N)
R = np.zeros(N)


def t_(dur):
    return np.arange(int(dur * SR)) / SR


def place(sig, start_s, gl=1.0, gr=1.0):
    i = round(start_s * SR)
    if i >= N:
        return
    j = min(N, i + len(sig))
    L[i:j] += sig[:j - i] * gl
    R[i:j] += sig[:j - i] * gr


def saw(freq, dur, nh=None, phase=0.0):
    t = t_(dur)
    nh = nh or max(1, int(min(40, 9000 / freq)))
    out = np.zeros_like(t)
    for k in range(1, nh + 1):
        out += np.sin(2 * np.pi * k * freq * t + phase * k) / k * (0.92 ** k)
    return out * 0.55


def lp_simple(x, a):
    # one-pole low-pass via FFT of its impulse response (fast, no scipy)
    n = len(x)
    h = (1 - a) * a ** np.arange(min(n, 4096))
    m = 1 << int(np.ceil(np.log2(n + len(h))))
    y = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(h, m), m)[:n]
    return y


def hp_noise(dur):
    n = rng.standard_normal(int(dur * SR))
    return n - lp_simple(n, 0.6)


def env_ad(n, a, d):
    e = np.ones(n)
    na = max(1, int(a * SR))
    e[:na] = np.linspace(0, 1, na)
    e[na:] = np.exp(-np.arange(n - na) / (d * SR))
    return e


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# ---- one-shots
def kick808(note=38, dur=1.2):
    t = t_(dur)
    f0 = midi(note)
    f = f0 + (f0 * 3) * np.exp(-t / 0.025)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * env_ad(len(t), 0.002, 0.45)
    s = np.tanh(2.2 * s) * 0.9
    click = hp_noise(0.01) * 0.3
    s[:len(click)] += click
    return s


def clap():
    n = hp_noise(0.35)
    e = np.zeros(len(n))
    for k, off in enumerate([0, 0.011, 0.022]):
        i = int(off * SR)
        e[i:] += np.exp(-np.arange(len(n) - i) / (0.012 * SR if k < 2 else 0.11 * SR))
    body = np.sin(2 * np.pi * 190 * t_(0.35)) * env_ad(len(n), 0.001, 0.04) * 0.5
    return (n * e * 0.55 + body) * 0.8


def hat(open_=False):
    d = 0.25 if open_ else 0.05
    n = hp_noise(d)
    n = n - lp_simple(n, 0.3)
    return n * env_ad(len(n), 0.0005, 0.08 if open_ else 0.012) * 0.35


def orch_hit(root=50):
    dur = 2.4
    t = t_(dur)
    s = np.zeros(len(t))
    for m in [root, root + 7, root + 12, root + 15, root + 19, root + 24]:
        for det in (-0.1, 0.0, 0.1):
            s += saw(midi(m + det), dur, phase=rng.uniform(0, 6))
    s = lp_simple(s, 0.55) * env_ad(len(t), 0.004, 0.45) * 0.11
    tim = np.sin(2 * np.pi * np.cumsum(midi(root - 12) * (1 + 0.4 * np.exp(-t / 0.05))) / SR)
    tim = tim * env_ad(len(t), 0.002, 0.7) * 0.7
    boom = lp_simple(rng.standard_normal(len(t)), 0.97) * env_ad(len(t), 0.001, 0.25) * 3.0
    return np.tanh((s + tim + boom) * 1.2) * 0.8


def string_note(m, dur):
    s = saw(midi(m), dur, phase=rng.uniform(0, 6)) + saw(midi(m + 0.08), dur, phase=rng.uniform(0, 6))
    s = lp_simple(s, 0.75)
    return s * env_ad(len(s), 0.01, dur * 0.6) * 0.22


def pad(chord, dur):
    t = t_(dur)
    s = np.zeros(len(t))
    for m in chord:
        s += np.sin(2 * np.pi * midi(m) * t) + 0.3 * np.sin(2 * np.pi * midi(m) * 2.003 * t)
    e = np.minimum(1, t / 0.4) * np.minimum(1, (dur - t) / 0.4)
    return s * e * 0.05


def riser(dur):
    t = t_(dur)
    n = rng.standard_normal(len(t))
    lo = lp_simple(n, 0.95)
    mix = lo + (n - lo) * (t / dur) ** 2
    sweep = np.sin(2 * np.pi * np.cumsum(200 + 1800 * (t / dur) ** 2) / SR) * 0.15
    return (mix * 0.25 + sweep) * (t / dur) ** 1.5


def write(dest: Path) -> Path:
    """Synthesise the whole bed into ``dest``. Same bytes every run."""
    global L, R, rng
    L = np.zeros(N)
    R = np.zeros(N)
    rng = np.random.default_rng(20261018)
    CLAP = clap()
    HAT = hat()
    OHAT = hat(True)
    HITS = {r: orch_hit(r) for r in (50, 46, 48, 45)}
    # progression in D minor: Dm Bb C A (roots, MIDI)
    PROG = [(38, [62, 65, 69], 50), (34, [58, 62, 65], 46), (36, [60, 64, 67], 48), (33, [57, 61, 64], 45)]

    sections = [('intro', 8), ('A', 16), ('B', 16), ('break', 8), ('A', 16), ('B', 16), ('break', 8), ('A', 16),
                ('outro', 8)]
    bar = 0
    for name, nb in sections:
        for b in range(nb):
            t0 = (bar + b) * BAR
            root, chord, hroot = PROG[(b // 2) % 4]
            full = name in ('A', 'B')
            # pad everywhere
            place(pad(chord, BAR), t0, 0.9, 1.0)
            # string ostinato (1/8 notes) except intro first half
            if not (name == 'intro' and b < 4):
                pat = [0, 12, 7, 12, 3, 12, 7, 15] if name != 'B' else [12, 15, 19, 15, 12, 19, 15, 24]
                for k, iv in enumerate(pat):
                    place(string_note(root + 24 + iv, BEAT * 0.5), t0 + k * BEAT * 0.5, 0.8, 0.55)
            if full or (name == 'outro' and b < 4):
                # 808: half-time pattern with syncopation and pitch from progression
                for pos in ([0, 1.75, 2.5] if b % 2 == 0 else [0, 0.75, 2.5, 3.25]):
                    k = kick808(root, 1.0 if pos < 3 else 0.6)
                    place(k, t0 + pos * BEAT, 1, 1)
                place(CLAP, t0 + 2 * BEAT, 0.9, 1.0)
                # hats: 1/8 base, 1/16 in B, triplet roll at end of every 4th bar
                step = 0.25 if name == 'B' else 0.5
                pos = 0.0
                while pos < 4 - 1e-9:
                    if b % 4 == 3 and pos >= 3:
                        for r in range(6):
                            place(HAT * 0.8, t0 + (3 + r / 6) * BEAT, 0.6, 1.0)
                        break
                    place(HAT, t0 + pos * BEAT, 0.7 + 0.3 * ((pos * 4) % 2), 1.0 - 0.3 * ((pos * 4) % 2))
                    pos += step
                if b % 2 == 1:
                    place(OHAT, t0 + 3.5 * BEAT, 1.0, 0.8)
            if name == 'break':
                place(kick808(root, 1.6) * 0.8, t0, 1, 1)
            # orchestral hits on phrase downbeats
            if (full and b % 4 == 0) or (name in ('intro', 'break') and b == 0) or (name == 'B' and b % 2 == 0):
                place(HITS[hroot], t0, 1, 1)
            if name == 'B' and b % 4 == 2:
                place(HITS[hroot] * 0.7, t0 + 2.5 * BEAT, 0.8, 1)
        # riser into the section that follows intro/break/A when next is B or A after break
        nxt = sections[sections.index((name, nb)) + 1][0] if (name, nb) != sections[-1] else None
        if nxt in ('A', 'B'):
            rl = 2 * BAR if name in ('intro', 'break') else BAR
            place(riser(rl), (bar + nb) * BAR - rl, 1, 1)
        bar += nb

    # outro fade over last 4 bars, but leave tails that wrap: fold the overflow-free end to start
    tail = int(4 * BAR * SR)
    fade = np.linspace(1, 0, tail) ** 1.5
    L[-tail:] *= fade
    R[-tail:] *= fade
    st = np.stack([L, R], 1)
    st = np.tanh(st * 0.7) * 0.8  # gentle fixed master saturation, no loudness normalisation
    pcm = (np.clip(st, -1, 1) * 32767).astype('<i2')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print('wrote', dest, '%.2f s' % (N / SR))
    return dest
