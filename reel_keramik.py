"""SPHINIX – Reel "Keramikversiegelung: 5 Fakten" (1080x1920, 30 fps).

Inputs (assets/keramik/):
  vo.mp3          ElevenLabs voice-over (take B)
  words.json      ElevenLabs Scribe word timestamps of vo.mp3
  *.png / *.jpg   scene images (ElevenLabs + Canva)
Plus output/sphinix_outro_no_sound.mp4 + output/sfx.wav (outro.py) appended at the end.

    python3 reel_keramik.py  ->  output/reel_keramik.mp4 (+ _ohne_musik.mp4)
"""
import json
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets", "keramik")
OUT = os.path.join(HERE, "output")
TMP = os.path.join(OUT, "tmp_reel")
os.makedirs(TMP, exist_ok=True)

SPEED = 1.10          # voice-over tempo (keeps the reel compact)
VO_OFF = 0.15         # voice starts a hair after the first frame
OUTRO_LEN = 3.5
XF = 0.3              # crossfade into the outro

RED = (230, 32, 40)
WHITE = (255, 255, 255)
FONT_DIR = "/usr/share/fonts/opentype/inter/"


def font(w, s):
    return ImageFont.truetype(FONT_DIR + f"InterDisplay-{w}.otf", s)


F_HOOK = font("Black", 118)
F_HOOK_SUB = font("SemiBold", 52)
F_NUM = font("Black", 64)
F_TITLE = font("ExtraBold", 84)
F_SUB = font("Medium", 44)
F_LIST = font("SemiBold", 54)
F_BIG = font("Black", 210)
F_CAP = font("ExtraBold", 66)
F_TAG = font("SemiBold", 30)


def vt(t_vo):
    """voice-over time -> video time"""
    return VO_OFF + t_vo / SPEED


# ---------------------------------------------------------------- words / captions
_raw = [w for w in json.load(open(os.path.join(A, "words.json")))["words"]
        if w["type"] == "word" and not w["text"].startswith("[")]
words = []
for w in _raw:
    if w["text"] in ("–", "-"):
        if words:
            words[-1]["brk"] = True   # break captions at dashes
        continue
    words.append(dict(w))
for w in words:
    w["s"], w["e"] = vt(w["start"]), vt(w["end"])
    w["t"] = w["text"].rstrip(",.:!?").upper()


def caption_groups():
    """Chunks of max 3 words / 16 chars, broken at punctuation."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        width = sum(F_CAP.getlength(x["t"]) for x in cur) + 18 * len(cur)
        nxt_w = width + (F_CAP.getlength(nxt["t"]) + 18 if nxt else 0)
        if w["text"][-1] in ",.:!?" or w.get("brk") or len(cur) == 3 or nxt_w > 860:
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    return groups


GROUPS = caption_groups()

# ---------------------------------------------------------------- word anchors (voice-over seconds)
def _norm(x):
    return x.lower().strip(",.:!?–-")


def at(word, after=0.0, lead=0.0):
    """Start time (VO seconds) of the first spoken `word` after `after`."""
    for w in words:
        if w["start"] >= after - 1e-3 and _norm(w["text"]) == _norm(word):
            return max(0.0, w["start"] - lead)
    raise KeyError(word)


T_EINS = at("Eins", lead=0.15)
T_VOR = at("Vorteile", lead=0.3)
T_NACH = at("Nachteile", lead=0.3)
T_WAS = at("Was", after=at("Profi-Tipp"), lead=0.1)

# ---------------------------------------------------------------- scenes (voice-over seconds)
SCENES = [
    dict(t0=0.0,   img="car.png",    kind="hook", pan=(0.05, 0.40)),
    dict(t0=T_EINS, img="apply.png",  kind="fact", n="01", title="CHEMISCHE\nBINDUNG", sub="Liegt nicht nur drauf wie Wachs", pan=(0.30, 0.55)),
    dict(t0=at("Zwei", lead=0.1), img="gloss.jpg",  kind="big",  n="02", big="1–5", title="JAHRE SCHUTZ", sub="Wachs: nur ein paar Wochen"),
    dict(t0=at("Drei", lead=0.1), img="beads.png",  kind="fact", n="03", title="WASSER\nPERLT AB", sub="Schmutz haftet kaum – schneller waschen", pan=(0.20, 0.45)),
    dict(t0=at("Vier", lead=0.1), img="autumn.jpg", kind="fact", n="04", title="SCHUTZ VOR", sub="UV · Vogelkot · Baumharz · Streusalz"),
    dict(t0=at("Fünf", after=at("Vier"), lead=0.1), img="swirl.jpg",  kind="fact", n="05", title="NICHT\nKRATZFEST", sub="Waschkratzer bleiben möglich"),
    dict(t0=T_VOR, img="car.png",    kind="list", title="VORTEILE", good=True, pan=(0.75, 0.50),
         items=[("Mega Glanz", at("Mega", T_VOR)), ("Mehr Farbtiefe", at("mehr", T_VOR)), ("Weniger Pflegeaufwand", at("viel", T_VOR))]),
    dict(t0=T_NACH, img="polish.jpg", kind="list", title="NACHTEILE", good=False,
         items=[("Aufwendige Vorbereitung", at("Vorbereitung", T_NACH)), ("Lack muss perfekt\npoliert sein", at("der", T_NACH)), ("Teurer als Wachs", at("kostet", T_NACH))]),
    dict(t0=at("Profi-Tipp", lead=0.1), img="wash.jpg",   kind="big",  n="TIPP", big="7", title="TAGE KEINE\nWASCHANLAGE", sub="Danach pH-neutrales Shampoo"),
    dict(t0=T_WAS, img="apply.png",  kind="cta",  pan=(0.70, 0.75)),
]
VO_END = words[-1]["end"]
for i, s in enumerate(SCENES):
    s["a"] = 0.0 if i == 0 else vt(s["t0"])
    s["b"] = vt(SCENES[i + 1]["t0"]) if i + 1 < len(SCENES) else vt(VO_END) + 0.6
REEL_LEN = SCENES[-1]["b"]
TOTAL = REEL_LEN - XF + OUTRO_LEN
N = int(round(REEL_LEN * FPS))


# ---------------------------------------------------------------- images
_cache = {}


def base_image(name):
    """Pre-scaled image, a bit larger than the frame for camera motion."""
    if name in _cache:
        return _cache[name]
    im = Image.open(os.path.join(A, name)).convert("RGB")
    ar = im.width / im.height
    if ar > 0.7:   # landscape (ElevenLabs 16:9): fill height, pan horizontally
        h = int(H * 1.08); w = int(h * ar)
    else:          # portrait (Canva 9:16): fill width with room for a slow zoom
        w = int(W * 1.15); h = int(w / ar)
    im = im.resize((w, h), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 60, 2))
    # grade: slightly darker, punchier
    arr = np.asarray(im, np.float32) / 255
    arr = np.clip((arr - 0.5) * 1.08 + 0.47, 0, 1) ** 1.08
    im = Image.fromarray((arr * 255).astype(np.uint8))
    _cache[name] = im
    return im


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def ease_out(t, p=3):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** p


def camera(scene, t):
    im = base_image(scene["img"])
    u = (t - scene["a"]) / max(scene["b"] - scene["a"], 1e-3)
    if im.width > im.height:  # pan
        p0, p1 = scene.get("pan", (0.3, 0.6))
        p = p0 + (p1 - p0) * ease(u)
        z = 1.0 + 0.05 * u
        cw, ch = W / z * (im.height / H / 1.0), H / z * (im.height / H)
        cw, ch = cw / 1.08, ch / 1.08
        cx = cw / 2 + p * (im.width - cw)
        cy = im.height / 2
    else:                     # slow push-in
        z = 1.0 + 0.10 * u
        cw, ch = im.width / 1.15 / z, im.width / 1.15 / z * H / W
        cx, cy = im.width / 2, im.height / 2
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    # punch-in at the start of every cut
    k = t - scene["a"]
    if k < 0.25 and scene["a"] > 0:
        s = 1 + 0.06 * (1 - ease_out(k / 0.25))
        bw, bh = (box[2] - box[0]) / s, (box[3] - box[1]) / s
        mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        box = (mx - bw / 2, my - bh / 2, mx + bw / 2, my + bh / 2)
    return im.transform((W, H), Image.EXTENT, box, Image.BILINEAR)


# legibility gradients (top for titles, bottom for captions)
yy = np.linspace(0, 1, H)[:, None]
SHADE = (0.88 * np.clip(1 - yy / 0.50, 0, 1) ** 1.3 + 0.65 * np.clip((yy - 0.55) / 0.45, 0, 1) ** 1.4 + 0.12)
SHADE = Image.fromarray((np.clip(SHADE, 0, 1) * 255).astype(np.uint8).repeat(W, 1), "L")
BLACK = Image.new("RGB", (W, H), (0, 0, 0))

# ---------------------------------------------------------------- text helpers


def text_w(f, s):
    return f.getlength(s)


def draw_text(layer, xy, s, f, fill, anchor="la", alpha=1.0, shadow=True):
    d = ImageDraw.Draw(layer)
    fill = tuple(fill) + (int(255 * alpha),)
    if shadow and alpha > 0:
        sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text(xy, s, font=f, fill=(0, 0, 0, int(170 * alpha)), anchor=anchor)
        layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def pop(t, t0, dur=0.35):
    return ease_out((t - t0) / dur)


def multiline(layer, x, y, s, f, fill, alpha, lh, anchor="la"):
    for i, line in enumerate(s.split("\n")):
        draw_text(layer, (x, y + i * lh), line, f, fill, anchor, alpha)
    return y + len(s.split("\n")) * lh


def check(d, x, y, sz, a):
    d.line([(x, y + sz * 0.55), (x + sz * 0.38, y + sz * 0.9), (x + sz, y + sz * 0.1)],
           fill=(255, 255, 255, int(255 * a)), width=9, joint="curve")


def cross(d, x, y, sz, a):
    c = (255, 255, 255, int(255 * a))
    d.line([(x + 6, y + 6), (x + sz - 6, y + sz - 6)], fill=c, width=9)
    d.line([(x + sz - 6, y + 6), (x + 6, y + sz - 6)], fill=c, width=9)


LX = 84   # left margin


def overlay(scene, t):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    k = t - scene["a"]
    kind = scene["kind"]

    if kind == "hook":
        e1, e2, e3 = pop(t, 0.15, 0.45), pop(t, 0.45, 0.45), pop(t, vt(at("Hier")), 0.4)
        draw_text(L, (LX, 360 - 40 * (1 - e1)), "KERAMIK-", F_HOOK, WHITE, alpha=e1)
        draw_text(L, (LX, 480 - 40 * (1 - e2)), "VERSIEGELUNG", F_HOOK, WHITE, alpha=e2)
        draw_text(L, (LX, 640), "Lohnt sich das?", F_HOOK_SUB, WHITE, alpha=pop(t, vt(at("lohnt"))))
        if e3 > 0:
            w = text_w(F_NUM, "5 FAKTEN") + 56
            x0 = LX
            d.rounded_rectangle([x0, 730, x0 + w * e3, 830], 14, fill=RED + (235,))
            if e3 > 0.6:
                draw_text(L, (x0 + 28, 742), "5 FAKTEN", F_NUM, WHITE, alpha=(e3 - 0.6) / 0.4, shadow=False)
        draw_text(L, (LX, 300), "SPHINIX CAR DETAILING", F_TAG, (220, 220, 220), alpha=e1 * 0.9)

    elif kind in ("fact", "big"):
        e0, e1, e2 = pop(k, 0.0, 0.3), pop(k, 0.12, 0.4), pop(k, 0.35, 0.4)
        # number badge
        num = scene["n"]
        bw = text_w(F_NUM, num) + 48
        d.rounded_rectangle([LX, 300, LX + bw * e0, 392], 12, fill=RED + (240,))
        if e0 > 0.7:
            draw_text(L, (LX + 24, 310), num, F_NUM, WHITE, alpha=(e0 - 0.7) / 0.3, shadow=False)
        y = 430
        if kind == "big":
            draw_text(L, (LX - 6, y - 50 * (1 - e1)), scene["big"], F_BIG, WHITE, alpha=e1)
            y += 225
        y = multiline(L, LX, y + 30 * (1 - e1), scene["title"], F_TITLE, WHITE, e1, 96)
        # red underline + sub
        d.rectangle([LX, y + 18, LX + 120 * e2, y + 26], fill=RED + (255,))
        draw_text(L, (LX, y + 50), scene["sub"], F_SUB, (235, 235, 235), alpha=e2)

    elif kind == "list":
        e0 = pop(k, 0.0, 0.35)
        draw_text(L, (LX, 330 - 30 * (1 - e0)), scene["title"], F_TITLE, WHITE, alpha=e0)
        d.rectangle([LX, 440, LX + 120 * e0, 448], fill=RED + (255,))
        y = 500
        for txt, tw in scene["items"]:
            e = pop(t, vt(tw) - 0.05, 0.35)
            if e <= 0:
                y += 140; continue
            x = LX - 40 * (1 - e)
            d.ellipse([x, y, x + 76, y + 76], fill=(RED if not scene["good"] else (24, 24, 24)) + (int(240 * e),),
                      outline=(255, 255, 255, int(200 * e)) if scene["good"] else None, width=3)
            (check if scene["good"] else cross)(d, x + 18, y + 18, 40, e)
            yy_ = multiline(L, x + 104, y + 6, txt, F_LIST, WHITE, e, 64)
            y = max(y + 140, yy_ + 40)

    elif kind == "cta":
        e1, e2, e3 = pop(k, 0.0, 0.4), pop(t, vt(at("Schreib", T_WAS)), 0.4), pop(t, vt(at("du", T_WAS)), 0.4)
        draw_text(L, (W / 2, 420 - 30 * (1 - e1)), "WAS KOSTET'S", F_TITLE, WHITE, "ma", e1)
        draw_text(L, (W / 2, 520 - 30 * (1 - e1)), "FÜR DEIN AUTO?", F_TITLE, WHITE, "ma", e1)
        if e2 > 0:
            w = 760
            x0 = (W - w) / 2
            d.rounded_rectangle([x0 + w / 2 * (1 - e2), 690, x0 + w / 2 + w / 2 * e2, 800], 55, fill=RED + (245,))
            if e2 > 0.6:
                draw_text(L, (W / 2, 716), "SCHREIB UNS", F_NUM, WHITE, "ma", (e2 - 0.6) / 0.4, shadow=False)
        draw_text(L, (W / 2, 850), "Du bekommst ein persönliches Angebot", F_SUB, WHITE, "ma", e3)
    return L


def captions(t):
    """Word-by-word caption, current word in red, lower third (inside the Reels safe zone)."""
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for g in GROUPS:
        if g[0]["s"] - 0.05 <= t < g[-1]["e"] + 0.15:
            break
    else:
        return L
    sp = 18
    ws = [text_w(F_CAP, w["t"]) for w in g]
    total = sum(ws) + sp * (len(g) - 1)
    x = (W - total) / 2
    y = 1330
    e = pop(t, g[0]["s"] - 0.05, 0.15)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    d = ImageDraw.Draw(L)
    for w, wd in zip(g, ws):
        active = w["s"] - 0.03 <= t < w["e"] + 0.05 or (w is g[-1] and t >= w["s"])
        col = RED if active else WHITE
        yo = y + 14 * (1 - e)
        ds.text((x, yo + 4), w["t"], font=F_CAP, fill=(0, 0, 0, 200))
        d.text((x, yo), w["t"], font=F_CAP, fill=col + (int(255 * e),),
               stroke_width=4, stroke_fill=(0, 0, 0, int(220 * e)))
        x += wd + sp
    sh = sh.filter(ImageFilter.GaussianBlur(8))
    sh.alpha_composite(L)
    return sh


# ---------------------------------------------------------------- progress bar (top) + brand tag
def chrome(t):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    p = min(t / REEL_LEN, 1)
    d.rectangle([0, 0, W, 8], fill=(255, 255, 255, 50))
    d.rectangle([0, 0, W * p, 8], fill=RED + (255,))
    return L


def render(i):
    t = i / FPS
    for s in SCENES:
        if s["a"] <= t < s["b"]:
            break
    img = camera(s, t)
    img = Image.composite(BLACK, img, SHADE)
    # white flash at cuts
    k = t - s["a"]
    if s["a"] > 0 and k < 0.12:
        img = Image.blend(img, Image.new("RGB", (W, H), (255, 255, 255)), 0.35 * (1 - k / 0.12))
    if t < 0.3:
        img = Image.blend(BLACK, img, t / 0.3)
    img = img.convert("RGBA")
    img.alpha_composite(overlay(s, t))
    img.alpha_composite(captions(t))
    img.alpha_composite(chrome(t))
    return img.convert("RGB")


# ---------------------------------------------------------------- audio
def read_wav_mono(path):
    with wave.open(path) as wf:
        sr, ch, n = wf.getframerate(), wf.getnchannels(), wf.getnframes()
        x = np.frombuffer(wf.readframes(n), np.int16).astype(np.float32) / 32768
    x = x.reshape(-1, ch).mean(1)
    assert sr == SR
    return x


def music(n):
    """Minimal dark house groove, 124 bpm (synthesized, royalty-free)."""
    rng = np.random.default_rng(3)
    t = np.arange(n) / SR
    out = np.zeros(n)
    beat = 60 / 124
    for b in range(int(n / SR / beat) + 1):
        t0 = b * beat
        i0 = int(t0 * SR)
        L = int(0.35 * SR)
        seg = np.arange(min(L, n - i0)) / SR
        if len(seg) == 0:
            continue
        f = 45 + 90 * np.exp(-seg / 0.03)
        out[i0:i0 + len(seg)] += np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-seg / 0.18) * 0.9
        if b % 2 == 1:   # clap
            m = min(int(0.2 * SR), n - i0)
            nz = rng.standard_normal(m)
            nz = np.diff(np.concatenate([[0], nz]))
            out[i0:i0 + m] += nz * np.exp(-np.arange(m) / SR / 0.05) * 0.18
        ih = int((t0 + beat / 2) * SR)   # off-beat hat
        m = min(int(0.06 * SR), n - ih)
        if m > 0:
            nz = np.diff(np.concatenate([[0], rng.standard_normal(m)]))
            out[ih:ih + m] += nz * np.exp(-np.arange(m) / SR / 0.015) * 0.12
    # bass: Am – F – C – G, one chord per bar, off-beat 8ths
    roots = [55.0, 43.65, 65.41, 49.0]
    bar = beat * 4
    bass = np.zeros(n)
    for j in range(int(n / SR / bar) + 1):
        fr = roots[j % 4]
        for q in range(4):
            t0 = j * bar + q * beat + beat / 2
            i0 = int(t0 * SR); m = min(int(beat / 2 * SR), n - i0)
            if m <= 0:
                continue
            s = np.arange(m) / SR
            bass[i0:i0 + m] += np.tanh(2 * np.sin(2 * np.pi * fr * s)) * np.exp(-s / 0.12) * 0.35
    out += bass
    # soft pad
    pad = sum(np.sin(2 * np.pi * f * t) for f in (220, 261.6, 329.6)) * 0.02
    out += pad
    return out


def whoosh(n_len, rng):
    m = int(n_len * SR)
    nz = rng.standard_normal(m)
    y = np.zeros(m); acc = 0
    env = np.sin(np.linspace(0, np.pi, m)) ** 2
    cut = 400 + 6000 * env
    a = 1 - np.exp(-2 * np.pi * cut / SR)
    for k in range(m):
        acc += a[k] * (nz[k] - acc); y[k] = acc
    return y * env


def build_audio(path_full, path_vo_only):
    n = int(TOTAL * SR) + SR
    # voice-over: decode, tempo-adjust, loudness-normalise
    vo_wav = os.path.join(TMP, "vo.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(A, "vo.mp3"),
                    "-af", f"atempo={SPEED},highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=5:release=80,"
                           "loudnorm=I=-15:TP=-1.5:LRA=7",
                    "-ar", str(SR), "-ac", "1", vo_wav], check=True)
    vo = read_wav_mono(vo_wav)
    voice = np.zeros(n)
    i0 = int(VO_OFF * SR)
    voice[i0:i0 + len(vo)] = vo[: n - i0]

    rng = np.random.default_rng(11)
    fx = np.zeros(n)
    for s in SCENES[1:]:
        w = whoosh(0.45, rng)
        j = int((s["a"] - 0.3) * SR)
        fx[j:j + len(w)] += w * 0.22
    # outro sfx
    sfx = read_wav_mono(os.path.join(OUT, "sfx.wav"))
    j = int((REEL_LEN - XF) * SR)
    fx[j:j + len(sfx)] += sfx[: n - j] * 0.8

    mus = music(n)
    # duck under the voice (envelope follower)
    env = np.abs(voice)
    k = int(0.15 * SR)
    env = np.convolve(env, np.ones(k) / k, "same")
    duck = 1 - 0.55 * np.clip(env / 0.05, 0, 1)
    fade = np.clip((REEL_LEN - np.arange(n) / SR) / 1.0, 0, 1)   # music out into the outro
    mus = mus * duck * fade * 0.16

    def write(path, x):
        x = x[: int(TOTAL * SR)]
        x = x / max(1.0, np.max(np.abs(x)) / 0.97)
        st = (np.stack([x, x], 1) * 32767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
            wf.writeframes(st.tobytes())

    write(path_full, voice + fx + mus)
    write(path_vo_only, voice + fx)


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    import sys
    only = [float(a) for a in sys.argv[1:]]
    if only:  # preview stills at given seconds
        for s in only:
            render(int(s * FPS)).save(os.path.join(TMP, f"still_{s:05.2f}.png"))
        sys.exit()

    print(f"reel {REEL_LEN:.2f}s + outro -> total {TOTAL:.2f}s, {N} frames", flush=True)
    reel = os.path.join(TMP, "reel_part.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                          "-crf", "17", "-pix_fmt", "yuv420p", reel], stdin=subprocess.PIPE)
    for i in range(N):
        p.stdin.write(render(i).tobytes())
        if i % 150 == 0:
            print("frame", i, flush=True)
    p.stdin.close(); p.wait()

    full_wav, vo_wav = os.path.join(TMP, "mix_full.wav"), os.path.join(TMP, "mix_vo.wav")
    build_audio(full_wav, vo_wav)
    outro = os.path.join(OUT, "sphinix_outro_no_sound.mp4")
    for wav, name in [(full_wav, "reel_keramik.mp4"), (vo_wav, "reel_keramik_ohne_musik.mp4")]:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", reel, "-i", outro, "-i", wav,
                        "-filter_complex", f"[0:v][1:v]xfade=transition=fade:duration={XF}:offset={REEL_LEN - XF:.3f},format=yuv420p[v]",
                        "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest",
                        os.path.join(OUT, name)], check=True)
    print("done")
