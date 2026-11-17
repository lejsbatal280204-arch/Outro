"""SPHINIX Car Detailing – Reels outro (1080x1920, 30 fps).

Renders frames with numpy/PIL, synthesizes a sound design track and
muxes everything with ffmpeg.

    python3 outro.py            -> output/sphinix_outro.mp4 (+ _no_sound.mp4)
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageFilter

W, H = 1080, 1920
FPS = 30
DUR = 5.0
N = int(FPS * DUR)
SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
FRAMES = os.path.join(OUT, "frames")
rng = np.random.default_rng(7)


# ---------------------------------------------------------------- helpers
def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def smooth(a, b, x):
    t = clamp01((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def ease_out_expo(t):
    t = min(max(t, 0.0), 1.0)
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def ease_out_cubic(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def blur(arr, r):
    """Gaussian blur of a float [0,1] 2-D array via PIL."""
    k = int(r * 3)
    g = np.exp(-(np.arange(-k, k + 1) ** 2) / (2 * r * r)).astype(np.float32)
    g /= g.sum()
    a = np.asarray(arr, np.float32)
    a = np.apply_along_axis(lambda m: np.convolve(m, g, "same"), 0, a)
    return np.apply_along_axis(lambda m: np.convolve(m, g, "same"), 1, a).astype(np.float32)


# ---------------------------------------------------------------- logo prep
src = np.asarray(Image.open(os.path.join(HERE, "assets", "logo.png")).convert("RGB"))
# crop to the logo content (found by analysing the PNG)
x0, x1, y0, y1 = 20, 476, 200, 346
crop = src[y0:y1, x0:x1]
SPLIT = 298 - y0  # row between wordmark and "CAR DETAILING"

SCALE = 2.05
UP = 4
big = Image.fromarray(crop).resize((crop.shape[1] * UP, crop.shape[0] * UP), Image.LANCZOS)
big = np.asarray(big, dtype=np.float32) / 255.0
a_big = big.max(axis=2)
# re-sharpen the edges after upscaling (logo is only 500px)
a_big = smooth(0.28, 0.72, a_big)
col_big = np.where(a_big[..., None] > 1e-3, clamp01(big / np.maximum(big.max(2, keepdims=True), 1e-3)), 1.0)

lw, lh = int(crop.shape[1] * SCALE), int(crop.shape[0] * SCALE)


def down(arr):
    if arr.ndim == 2:
        return blur_free_resize(arr, (lw, lh))
    return np.stack([blur_free_resize(arr[..., c], (lw, lh)) for c in range(arr.shape[2])], -1)


def blur_free_resize(a, size):
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize(size, Image.LANCZOS), dtype=np.float32)


L_A = clamp01(down(a_big))
L_C = clamp01(down(col_big))
split = int(SPLIT * SCALE)
red_mask = clamp01((L_C[..., 0] - L_C[..., 1]) * 3) * L_A

word_A = L_A.copy(); word_A[split:] = 0
sub_A = L_A.copy(); sub_A[:split] = 0

# logo placement on canvas
LX = (W - lw) // 2
LY = int(H * 0.44) - lh // 2


def place(a, fill=0.0):
    out = np.full((H, W) + a.shape[2:], fill, np.float32)
    out[LY:LY + lh, LX:LX + lw] = a
    return out


WORD = place(word_A)
SUB = place(sub_A)
RED = place(red_mask)
COL = place(L_C, 1.0)

# letters of "CAR DETAILING" -> column segments for a staggered reveal
cols = (sub_A > 0.1).any(0)
letters, s = [], None
for x, v in enumerate(cols):
    if v and s is None:
        s = x
    if not v and s is not None:
        letters.append((s + LX, x + LX)); s = None
if s is not None:
    letters.append((s + LX, lw + LX))

word_rows = np.where(word_A.max(1) > 0.1)[0]
WORD_TOP, WORD_BOT = word_rows.min() + LY, word_rows.max() + LY
WORD_CY = (WORD_TOP + WORD_BOT) / 2
sub_rows = np.where(sub_A.max(1) > 0.1)[0]
SUB_BOT = sub_rows.max() + LY
xs_word = np.where(word_A.max(0) > 0.1)[0]
WORD_L, WORD_R = xs_word.min() + LX, xs_word.max() + LX

# chrome-ish vertical tint on the wordmark (lets the shine read on white text)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
v = clamp01((yy - WORD_TOP) / max(WORD_BOT - WORD_TOP, 1))
CHROME = 1.0 - 0.20 * np.exp(-((v - 0.58) / 0.18) ** 2) - 0.06 * v

# precomputed glows
WORD_GLOW_S = blur(WORD, 6)
WORD_GLOW_L = blur(WORD, 28)
RED_GLOW = blur(RED * 1.0, 22)
RED_GLOW_XL = blur(RED * 1.0, 70)
SUB_GLOW = blur(SUB, 10)

# background: deep charcoal radial gradient + vignette
cx, cy = W / 2, LY + lh / 2
r = np.sqrt(((xx - cx) / W) ** 2 + ((yy - cy) / (H * 0.62)) ** 2)
BG = (0.075 * np.exp(-(r / 0.55) ** 2) + 0.012)[..., None] * np.array([1.0, 1.0, 1.03], np.float32)
# faint floor line / horizon under the logo
FLOOR_Y = SUB_BOT + 70

# particles (dust in a light beam)
P = 70
px = rng.uniform(0, W, P)
py = rng.uniform(H * 0.15, H * 0.85, P)
pv = rng.uniform(8, 30, P)          # upward px / s
pdx = rng.uniform(-6, 6, P)
ps = rng.uniform(1.0, 3.6, P)       # size
pa = rng.uniform(0.15, 0.6, P)
pph = rng.uniform(0, 2 * math.pi, P)
pred = rng.random(P) < 0.18          # a few red embers


def sprite(sz):
    k = int(sz * 4) | 1
    g = np.arange(k) - k // 2
    G = np.exp(-(g[:, None] ** 2 + g[None, :] ** 2) / (2 * sz * sz))
    return G.astype(np.float32)


SPRITES = {i: sprite(s) for i, s in enumerate(ps)}

RED_C = np.array([0.95, 0.12, 0.14], np.float32)

# ---------------------------------------------------------------- timeline (s)
T_STREAK0, T_STREAK1 = 0.25, 1.15     # light streak / wordmark reveal
T_POP = 1.15                          # red accent pop
T_SUB0 = 1.35                         # letters of CAR DETAILING
T_LINE0, T_LINE1 = 1.55, 2.35         # thin lines grow
T_SHINE0, T_SHINE1 = 2.45, 3.25       # gloss sweep
T_SPARK = 3.15                        # sparkle on the X


def render(i):
    t = i / FPS
    img = BG.copy()
    bg_in = smooth(0.0, 0.6, t)
    img *= bg_in

    # ---- light streak + reveal edge
    p = ease_out_cubic((t - T_STREAK0) / (T_STREAK1 - T_STREAK0))
    edge = WORD_L - 60 + p * (WORD_R - WORD_L + 160)
    reveal = clamp01((edge - xx) / 45.0)
    streak_on = smooth(T_STREAK0, T_STREAK0 + 0.08, t) * (1 - smooth(T_STREAK1 - 0.05, T_STREAK1 + 0.45, t))
    if streak_on > 0:
        dy = yy - WORD_CY
        tail = np.exp(-np.maximum(edge - xx, 0) / 380.0) * (xx < edge + 4)
        head = np.exp(-((xx - edge) / 30.0) ** 2)
        line = np.exp(-(dy / 2.2) ** 2) + 0.35 * np.exp(-(dy / 14) ** 2)
        streak = (line * (0.55 * tail + 1.2 * head) + 0.5 * head * np.exp(-(dy / 90) ** 2)) * streak_on
        img += streak[..., None] * np.array([0.95, 0.97, 1.0])
        # glowing reveal edge on the letters
        edge_glow = np.exp(-((xx - edge) / 22.0) ** 2) * WORD_GLOW_S * 2.2 * streak_on
        img += edge_glow[..., None]

    word_a = WORD * reveal
    # ---- gloss sweep
    shine = 0.0
    if T_SHINE0 - 0.2 < t < T_SHINE1 + 0.2:
        sp = (t - T_SHINE0) / (T_SHINE1 - T_SHINE0)
        u = xx + 0.45 * (yy - WORD_CY)
        c = WORD_L - 200 + sp * (WORD_R - WORD_L + 400)
        shine = np.exp(-((u - c) / 55.0) ** 2) * 0.9 + np.exp(-((u - c - 90) / 14.0) ** 2) * 0.6

    word_col = COL * (CHROME + shine)[..., None]
    img = img * (1 - word_a[..., None]) + word_col * word_a[..., None]

    # word bloom (settles after reveal) + shine bloom
    settle = smooth(T_STREAK0, T_STREAK1, t)
    bloom = WORD_GLOW_L * (0.10 * settle + 0.35 * np.exp(-((t - T_STREAK1) / 0.35) ** 2)) * reveal
    img += bloom[..., None] * np.array([0.9, 0.93, 1.0])
    if not np.isscalar(shine):
        img += (WORD_GLOW_S * shine * 0.6)[..., None]

    # ---- red accent pop
    if t > T_POP - 0.1:
        k = t - T_POP
        pulse = math.exp(-((k) / 0.12) ** 2) if k < 0 else math.exp(-k / 0.35)
        breathe = 0.12 + 0.05 * math.sin(t * 3.0)
        img += (RED_GLOW * (1.6 * pulse + breathe))[..., None] * RED_C
        img += (RED_GLOW_XL * (1.2 * pulse + 0.15))[..., None] * RED_C * 0.8
        # tiny anamorphic flare through the red tab
        if k > -0.1:
            ry, rx = np.argwhere(RED > 0.5).mean(0)
            fl = np.exp(-((yy - ry) / 3.0) ** 2) * np.exp(-np.abs(xx - rx) / 260.0) * pulse * 0.9
            img += fl[..., None] * np.array([1.0, 0.35, 0.35])

    # ---- CAR DETAILING letters, staggered rise + fade
    sub_layer = np.zeros((H, W), np.float32)
    sub_shift = np.zeros(1)
    for j, (a, b) in enumerate(letters):
        lt = (t - T_SUB0 - j * 0.045) / 0.45
        if lt <= 0:
            continue
        e = ease_out_expo(lt)
        dy = int(round((1 - e) * 26))
        piece = SUB[:, a:b] * e
        if dy:
            piece = np.roll(piece, dy, axis=0)
        sub_layer[:, a:b] = np.maximum(sub_layer[:, a:b], piece)
    img = img * (1 - sub_layer[..., None]) + sub_layer[..., None] * 0.93
    sub_lit = smooth(T_SUB0, T_SUB0 + 1.0, t)
    img += (SUB_GLOW * 0.12 * sub_lit)[..., None]

    # ---- thin lines left/right of the subtitle row, growing outward
    lp = ease_out_expo((t - T_LINE0) / (T_LINE1 - T_LINE0))
    if lp > 0:
        ly = FLOOR_Y
        half = lp * W * 0.36
        d = np.abs(xx - W / 2)
        ln = np.exp(-((yy - ly) / 1.1) ** 2) * clamp01((half - d) / 40) * (1 - d / (W * 0.55)) * 0.55
        img += ln[..., None]
        # red centre dot
        dot = np.exp(-(((xx - W / 2) ** 2 + (yy - ly) ** 2) / (2 * 3.2 ** 2))) * lp
        img += (dot * 1.4)[..., None] * RED_C

    # ---- reflection on the "floor"
    refl_src = (word_a * CHROME * 0.9 + sub_layer * 0.9)
    top, bot = LY, SUB_BOT + 4
    seg = refl_src[top:bot][::-1]
    ry0 = FLOOR_Y + 14
    ry1 = min(ry0 + seg.shape[0], H)
    seg = seg[: ry1 - ry0]
    fade = np.exp(-np.arange(seg.shape[0]) / 70.0)[:, None] * 0.16
    img[ry0:ry1] += (seg * fade)[..., None]

    # ---- sparkle star on the X
    sk = t - T_SPARK
    if -0.05 < sk < 0.7:
        s_amp = math.sin(min(max(sk / 0.7, 0), 1) * math.pi)
        sx, sy = WORD_R - 30, WORD_TOP + 14
        dx, dy = xx - sx, yy - sy
        rot = sk * 1.2
        ca, sa = math.cos(rot), math.sin(rot)
        u, w = dx * ca - dy * sa, dx * sa + dy * ca
        star = (np.exp(-(np.abs(u) / 90.0)) * np.exp(-(w / 1.6) ** 2)
                + np.exp(-(np.abs(w) / 90.0)) * np.exp(-(u / 1.6) ** 2)
                + 1.5 * np.exp(-(dx ** 2 + dy ** 2) / (2 * 6 ** 2))
                + 0.25 * np.exp(-(dx ** 2 + dy ** 2) / (2 * 30 ** 2)))
        img += (star * s_amp * 1.1)[..., None]

    # ---- particles (additive)
    part = np.zeros((H, W, 3), np.float32)
    pin = smooth(0.1, 1.2, t)
    for k in range(P):
        x = px[k] + pdx[k] * t
        y = (py[k] - pv[k] * t)
        a = pa[k] * pin * (0.6 + 0.4 * math.sin(t * 2.2 + pph[k]))
        spr = SPRITES[k]
        h2 = spr.shape[0] // 2
        xi, yi = int(x), int(y)
        if xi - h2 < 0 or yi - h2 < 0 or xi + h2 + 1 > W or yi + h2 + 1 > H:
            continue
        c = RED_C if pred[k] else np.array([0.85, 0.88, 1.0], np.float32)
        part[yi - h2:yi + h2 + 1, xi - h2:xi + h2 + 1] += spr[..., None] * a * c
    img += part

    # ---- global camera: slow push-in
    z = 1.0 + 0.045 * ease_out_cubic(t / DUR) + 0.0
    out = Image.fromarray((clamp01(img) ** (1 / 1.0) * 255 + rng.uniform(-1.2, 1.2, (H, W, 1))).clip(0, 255).astype(np.uint8))
    if z != 1.0:
        cw, ch = W / z, H / z
        ox, oy = (W - cw) / 2, (H - ch) / 2 + (cy - H / 2) * (1 - 1 / z)
        out = out.transform((W, H), Image.EXTENT, (ox, oy, ox + cw, oy + ch), Image.BICUBIC)
    return out


# ---------------------------------------------------------------- audio
def synth_audio(path):
    n = int(SR * DUR)
    t = np.arange(n) / SR
    out = np.zeros(n)

    def env(t0, a, d):
        x = t - t0
        e = np.where(x < 0, 0, np.where(x < a, x / a, np.exp(-(x - a) / d)))
        return e

    # whoosh: noise through a moving one-pole lowpass, swelling into the reveal
    noise = rng.standard_normal(n)
    cut = 300 + 5500 * smooth(T_STREAK0 - 0.2, T_STREAK1, t) * (1 - smooth(T_STREAK1, T_STREAK1 + 0.6, t)) + 200
    alpha = 1 - np.exp(-2 * np.pi * cut / SR)
    y = np.zeros(n); acc = 0.0
    for k in range(n):
        acc += alpha[k] * (noise[k] - acc)
        y[k] = acc
    wh_env = smooth(T_STREAK0 - 0.25, T_STREAK1 - 0.05, t) * np.exp(-np.maximum(t - (T_STREAK1 - 0.05), 0) / 0.18)
    out += y * wh_env * 0.55

    # impact on red pop: sub thump + click
    k = t - T_POP
    thump = np.sin(2 * np.pi * (48 * k + 30 * (1 - np.exp(-k / 0.05)) * 0.05)) * np.exp(-np.maximum(k, 0) / 0.45) * (k > 0)
    out += thump * 0.9
    out += rng.standard_normal(n) * np.exp(-np.maximum(k, 0) / 0.012) * (k > 0) * 0.35

    # soft ticks for the letters
    for j in range(len(letters)):
        tk = T_SUB0 + j * 0.045 + 0.05
        x = t - tk
        out += np.sin(2 * np.pi * 2400 * x) * np.exp(-np.maximum(x, 0) / 0.01) * (x > 0) * 0.05

    # shimmer on the gloss sweep + sparkle
    for f, d0 in [(2093, 0.0), (2637, 0.06), (3136, 0.12), (4186, 0.2), (3520, 0.7)]:
        x = t - (T_SHINE0 + d0)
        out += np.sin(2 * np.pi * f * x) * env(T_SHINE0 + d0, 0.005, 0.5) * 0.06
    # low pad
    pad = (np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 82.5 * t) + 0.3 * np.sin(2 * np.pi * 110.3 * t))
    out += pad * smooth(T_POP, T_POP + 1.0, t) * (1 - smooth(DUR - 1.0, DUR, t)) * 0.08

    out *= 1 - smooth(DUR - 0.3, DUR, t)
    out = np.tanh(out * 1.2) / np.tanh(1.2)
    out = out / np.max(np.abs(out)) * 0.89
    st = np.stack([out, out], 1)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((st * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    import sys
    os.makedirs(FRAMES, exist_ok=True)
    only = [int(a) for a in sys.argv[1:]]
    idx = only or range(N)
    for i in idx:
        render(i).save(os.path.join(FRAMES, f"f{i:04d}.png"), compress_level=1)
        if i % 15 == 0:
            print("frame", i, flush=True)
    if only:
        sys.exit()
    wav = os.path.join(OUT, "sfx.wav")
    synth_audio(wav)
    common = ["-framerate", str(FPS), "-i", os.path.join(FRAMES, "f%04d.png")]
    venc = ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    subprocess.run(["ffmpeg", "-y", *common, *venc, os.path.join(OUT, "sphinix_outro_no_sound.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", *common, "-i", wav, *venc, "-c:a", "aac", "-b:a", "192k", "-shortest",
                    os.path.join(OUT, "sphinix_outro.mp4")], check=True)
    print("done")
