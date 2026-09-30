"""Original 21s score for the brag video: 120 BPM, A minor, SFX tuned to the key."""
import numpy as np, wave

SR = 48000
DUR = 21.0
N = int(SR * DUR)
BEAT = 0.5
rng = np.random.default_rng(7)

def t_(d): return np.arange(int(SR * d)) / SR
def midi(n): return 440.0 * 2 ** ((n - 69) / 12)

def add(buf, sig, at, gain=1.0):
    i = int(at * SR)
    if i >= len(buf): return
    sig = sig[: len(buf) - i]
    buf[i:i + len(sig)] += sig * gain

def adsr(n, a=0.005, d=0.1, s=0.6, r=0.1, sus=None):
    a_, d_, r_ = int(a * SR), int(d * SR), int(r * SR)
    s_ = max(0, n - a_ - d_ - r_)
    env = np.concatenate([np.linspace(0, 1, a_, False), np.linspace(1, s, d_, False),
                          np.full(s_, s), np.linspace(s, 0, r_)])
    return env[:n] if len(env) >= n else np.pad(env, (0, n - len(env)))

def lp(x, cutoff):
    # one-pole lowpass (cutoff may be array)
    cutoff = np.broadcast_to(cutoff, x.shape)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x); z = 0.0
    for i in range(len(x)):
        z = (1 - a[i]) * x[i] + a[i] * z; y[i] = z
    return y

def hp(x, cutoff): return x - lp(x, cutoff)

def saw(f, d):
    t = t_(d); ph = (f * t) % 1.0
    return 2 * ph - 1

def conv(x, ir):
    n = len(x) + len(ir) - 1; L = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, L) * np.fft.rfft(ir, L), L)[:len(x)]

ir_t = t_(2.2)
IR = rng.standard_normal(len(ir_t)) * np.exp(-ir_t * 3.2)
IR = lp(IR, 5000); IR /= np.abs(IR).sum() ** 0.5 * 6

music = np.zeros(N); sfx = np.zeros(N); verb_send = np.zeros(N)

# --- chords: Am F C G per bar (2s) ---
prog = [[57, 60, 64], [53, 57, 60], [48, 55, 60, 64], [55, 59, 62]]
bass_roots = [45, 41, 48, 43]

# pad (soft detuned saws, lowpassed), from 0 quietly, fuller after drop
for bar in range(11):
    start = bar * 2.0
    if start >= DUR: break
    ch = prog[bar % 4]; d = 2.05
    sig = np.zeros(int(SR * d))
    for n in ch:
        for det in (-0.08, 0.08):
            sig += saw(midi(n + 12) * (1 + det / 100 * 6), d)
    sig = lp(sig, 900 if start < 3 else 1600)
    g = 0.035 if start < 3 else 0.05
    if start >= 18: g = 0.0
    sig *= adsr(len(sig), 0.3, 0.2, 0.9, 0.4)
    add(music, sig, start, g); add(verb_send, sig, start, g * 0.8)

# bass: 8th-note pulse
for i in range(int(18.0 / 0.25)):
    at = i * 0.25; bar = int(at // 2.0); root = bass_roots[bar % 4]
    d = 0.22; tt = t_(d)
    s = np.sin(2 * np.pi * midi(root) * tt) + 0.35 * np.sin(2 * np.pi * midi(root + 12) * tt)
    s *= adsr(len(s), 0.004, 0.08, 0.5, 0.06)
    g = 0.16 if at < 3 else 0.24
    if at < 3: g *= 0.4 + 0.6 * at / 3  # build
    add(music, s, at, g)

# drums from the drop (3.0) to 18.0
def kick():
    tt = t_(0.35); f = 45 + 110 * np.exp(-tt * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9)
def hat():
    s = hp(rng.standard_normal(int(SR * 0.05)), 7000); return s * np.exp(-t_(0.05) * 70)
def clap():
    s = lp(hp(rng.standard_normal(int(SR * 0.18)), 900), 5000)
    env = np.exp(-t_(0.18) * 22); return s * env
K, H, C = kick(), hat(), clap()
for b in range(int(3.0 / BEAT), int(18.0 / BEAT)):
    at = b * BEAT
    add(music, K, at, 0.55)
    add(music, H, at + 0.25, 0.05)
    if b % 2 == 1: add(music, C, at, 0.10); add(verb_send, C, at, 0.08)
# intro heartbeat kick (soft) under the hook
for at in (0.0, 1.0, 2.0, 2.5):
    add(music, K, at, 0.28)

# final chord at 18.0, rings out
d = 3.0; sig = np.zeros(int(SR * d))
for n in [45, 57, 60, 64, 69]:
    sig += np.sin(2 * np.pi * midi(n) * t_(d)) * (0.6 if n < 50 else 0.25)
    sig += 0.3 * saw(midi(n), d) * (n >= 57)
sig = lp(sig, 2200) * adsr(len(sig), 0.005, 0.4, 0.45, 1.6)
add(music, sig, 18.0, 0.22); add(verb_send, sig, 18.0, 0.18); add(music, K, 18.0, 0.6)

# --- SFX, tuned to A minor, sitting under the music ---
# referee-style whistle at the open (A6 with trill)
tt = t_(0.55); f = midi(93) * (1 + 0.012 * np.sin(2 * np.pi * 28 * tt))
wh = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.15 * rng.standard_normal(len(tt)) * 0.3
wh = lp(wh, 4000) * adsr(len(wh), 0.01, 0.05, 0.8, 0.12)
add(sfx, wh, 0.08, 0.05); add(verb_send, wh, 0.08, 0.05)

# ticks as the fitness number drops (27 steps between 0.35 and 1.85, eased)
def eio(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
prev = 60
for i in range(301):
    t = 0.35 + 1.5 * i / 300; v = round(60 - 27 * eio(i / 300))
    if v != prev:
        prev = v; tk = np.sin(2 * np.pi * midi(88) * t_(0.03)) * np.exp(-t_(0.03) * 160)
        add(sfx, tk, t, 0.035)

# whooshes into each cut (rising filtered noise)
def whoosh(d=0.4, lo=300, hi=3500):
    n = int(SR * d); x = rng.standard_normal(n)
    cut = lo * (hi / lo) ** (np.linspace(0, 1, n) ** 1.5)
    s = lp(hp(x, 200), cut); env = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return s * env
for at, g in ((2.62, 0.09), (5.7, 0.06), (9.7, 0.06), (13.7, 0.06), (17.65, 0.07)):
    w = whoosh(); add(sfx, w, at, g); add(verb_send, w, at, g * 0.6)
w = whoosh(0.8, 200, 2500); add(sfx, w, 11.6, 0.045)

# sub boom at the drop
tt = t_(1.0); boom = np.sin(2 * np.pi * np.cumsum(38 + 40 * np.exp(-tt * 10)) / SR) * np.exp(-tt * 3.5)
add(sfx, boom, 3.0, 0.35)

# plucks for highlights: A5, C6 then E6 for the chip
def pluck(n, d=0.5):
    tt = t_(d); s = np.sin(2 * np.pi * midi(n) * tt) + 0.3 * np.sin(4 * np.pi * midi(n) * tt)
    return s * np.exp(-tt * 9)
for at, n in ((15.0, 81), (15.6, 84), (16.2, 88)):
    p = pluck(n); add(sfx, p, at, 0.06); add(verb_send, p, at, 0.07)
# typing ticks for the outro command
for i in range(32):
    at = 18.5 + 0.9 * i / 32
    tk = lp(rng.standard_normal(int(SR * 0.012)), 3000) * np.exp(-t_(0.012) * 300)
    add(sfx, tk, at, 0.03)

# stadium crowd bed: bandpassed noise, swells at hook and outro
crowd = lp(hp(rng.standard_normal(N), 250), 1800)
tt = np.arange(N) / SR
cenv = 0.35 + 0.65 * np.exp(-((tt - 1.5) / 1.6) ** 2) + 0.5 * np.exp(-((tt - 19) / 1.4) ** 2)
crowd *= cenv * (0.9 + 0.1 * np.sin(2 * np.pi * 0.7 * tt))
music += crowd * 0.022

# sidechain-ish duck for sfx: slight dip of music around sfx energy
mix = music + sfx + conv(verb_send, IR) * 0.9
mix = hp(mix, 30)
fade = np.ones(N); fl = int(SR * 0.6); fade[-fl:] = np.linspace(1, 0, fl) ** 2
fade[:int(SR * 0.01)] = np.linspace(0, 1, int(SR * 0.01))
mix *= fade
mix = np.tanh(mix * 1.3) / np.tanh(1.3)
mix *= 0.89 / np.abs(mix).max()
st = np.stack([mix, mix], 1)
# tiny stereo widening via delayed verb-only difference is skipped; mono-compatible master
with wave.open('audio.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype('<i2').tobytes())
print('ok', np.abs(mix).max(), np.sqrt((mix ** 2).mean()))
