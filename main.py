#!/usr/bin/env python3
"""Mochi the kitten — generative picture for make.fun 'Make the cutest picture'.

Pure Python 3 stdlib (no PIL in the sandbox). A chubby orange kitten with huge
shiny eyes, blush and a tiny heart, on a soft pastel background with clouds,
hearts and sparkles. 1024x1024, fully deterministic (fixed seeds -> identical
bytes every run). Writes /output/entry.png (override with ENTRY_OUT locally).
"""
import math, os, random, struct, zlib

W = H = 1024


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


def grad(stops, t):
    if t <= stops[0][0]:
        return stops[0][1]
    for i in range(1, len(stops)):
        if t <= stops[i][0]:
            p0, c0 = stops[i - 1]
            p1, c1 = stops[i]
            return mix(c0, c1, (t - p0) / (p1 - p0))
    return stops[-1][1]


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.p = bytearray(w * h * 3)

    def blend(self, x, y, c, a):
        if a <= 0.0 or x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        i = (y * self.w + x) * 3
        ia = 1.0 - a
        self.p[i] = int(self.p[i] * ia + c[0] * a)
        self.p[i + 1] = int(self.p[i + 1] * ia + c[1] * a)
        self.p[i + 2] = int(self.p[i + 2] * ia + c[2] * a)

    def vgrad(self, stops):
        for y in range(self.h):
            c = grad(stops, y / (self.h - 1))
            row = bytes((int(c[0]), int(c[1]), int(c[2]))) * self.w
            i = y * self.w * 3
            self.p[i:i + self.w * 3] = row


def draw(cv, bbox, sdf, paint, aa=1.0):
    x0 = max(0, int(bbox[0])); y0 = max(0, int(bbox[1]))
    x1 = min(cv.w, int(bbox[2]) + 1); y1 = min(cv.h, int(bbox[3]) + 1)
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = sdf(x + 0.5, y + 0.5)
            a = clamp(0.5 - d / aa, 0.0, 1.0)
            if a > 0.0:
                c = paint(x + 0.5, y + 0.5)
                cv.blend(x, y, c, a * c[3])


def solid(c, a=1.0):
    return lambda x, y: (c[0], c[1], c[2], a)


def sd_circle(cx, cy, r):
    return lambda x, y: math.hypot(x - cx, y - cy) - r


def sd_ellipse(cx, cy, rx, ry):
    m = min(rx, ry)
    return lambda x, y: (math.hypot((x - cx) / rx, (y - cy) / ry) - 1.0) * m


def sd_poly(pts):
    """Inigo Quilez polygon SDF (exact sign test)."""
    def f(px, py):
        d = (px - pts[0][0]) ** 2 + (py - pts[0][1]) ** 2
        s = 1.0
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]; xj, yj = pts[j]
            ex, ey = xj - xi, yj - yi
            wx, wy = px - xi, py - yi
            ee = ex * ex + ey * ey
            t = clamp((wx * ex + wy * ey) / ee, 0.0, 1.0) if ee > 0 else 0.0
            dx, dy = wx - ex * t, wy - ey * t
            dd = dx * dx + dy * dy
            if dd < d:
                d = dd
            c1 = py >= yi
            c2 = py < yj
            c3 = ex * wy > ey * wx
            if c1 == c2 == c3:
                s = -s
            j = i
        return s * math.sqrt(d)
    return f


def sd_capsule(x1, y1, x2, y2, r):
    def f(px, py):
        ex, ey = x2 - x1, y2 - y1
        wx, wy = px - x1, py - y1
        t = clamp((wx * ex + wy * ey) / (ex * ex + ey * ey), 0.0, 1.0)
        return math.hypot(wx - ex * t, wy - ey * t) - r
    return f


def sd_heart(cx, cy, s):
    """Plump heart = union of two lobe circles and a downward triangle."""
    c1 = sd_circle(cx - 0.42 * s, cy - 0.30 * s, 0.56 * s)
    c2 = sd_circle(cx + 0.42 * s, cy - 0.30 * s, 0.56 * s)
    tri = sd_poly([(cx - 0.92 * s, cy - 0.24 * s), (cx + 0.92 * s, cy - 0.24 * s),
                   (cx, cy + 1.04 * s)])
    return lambda x, y: min(c1(x, y), c2(x, y), tri(x, y))


def sd_sparkle(cx, cy, r):
    """4-point star: min of two thin diamonds."""
    def f(px, py):
        x, y = abs(px - cx), abs(py - cy)
        d1 = (x / (r * 0.16) + y / r) - 1.0
        d2 = (x / r + y / (r * 0.16)) - 1.0
        return min(d1, d2) * r * 0.16
    return f


def cloud(cv, cx, cy, s, col, alpha):
    for dx, dy, r in ((-70, 14, 44), (-30, -6, 58), (22, -12, 64), (66, 10, 46), (0, 16, 52)):
        draw(cv, (cx + (dx - r - 24) * s, cy + (dy - r - 24) * s,
                  cx + (dx + r + 24) * s, cy + (dy + r + 24) * s),
             sd_circle(cx + dx * s, cy + dy * s, r * s), solid(col, alpha), aa=16.0)


def main():
    cv = Canvas(W, H)
    rng = random.Random(777)

    # --- background: dreamy pink -> peach -> cream ---
    cv.vgrad([(0.0, (255, 205, 225)), (0.45, (255, 218, 205)),
              (0.75, (255, 233, 200)), (1.0, (255, 240, 214))])

    # polka dots, soft white
    for gy in range(5):
        for gx in range(5):
            cx = 70 + gx * 215 + (55 if gy % 2 else 0)
            cy = 60 + gy * 205
            if 330 < cx < 700 and 180 < cy < 900:
                continue  # keep the kitten's area clean
            draw(cv, (cx - 26, cy - 26, cx + 26, cy + 26), sd_circle(cx, cy, 15),
                 solid((255, 255, 255), 0.35), aa=6.0)

    # clouds
    cloud(cv, 150, 128, 1.0, (255, 255, 255), 0.85)
    cloud(cv, 872, 108, 0.85, (255, 255, 255), 0.85)
    cloud(cv, 916, 856, 0.7, (255, 255, 255), 0.6)
    cloud(cv, 104, 830, 0.62, (255, 255, 255), 0.6)

    # floating hearts + sparkles
    for cx, cy, s, col in [(238, 300, 30, (255, 130, 165)), (806, 330, 24, (255, 150, 150)),
                           (862, 560, 19, (255, 130, 165)), (168, 566, 21, (255, 170, 160))]:
        draw(cv, (cx - s - 4, cy - s - 4, cx + s + 4, cy + s + 4), sd_heart(cx, cy, s),
             solid(col, 0.9), aa=1.6)
    for cx, cy, r, col in [(316, 168, 26, (255, 214, 90)), (724, 196, 20, (255, 224, 130)),
                           (120, 430, 17, (255, 214, 90)), (912, 442, 22, (255, 224, 130)),
                           (648, 96, 15, (255, 230, 150))]:
        draw(cv, (cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3), sd_sparkle(cx, cy, r),
             solid(col, 0.95), aa=1.6)

    # --- ground shadow + rug ---
    draw(cv, (512 - 330, 856 - 66, 512 + 330, 856 + 66), sd_ellipse(512, 862, 322, 58),
         solid((238, 164, 150), 0.35), aa=22.0)
    draw(cv, (512 - 348, 852 - 84, 512 + 348, 852 + 84), sd_ellipse(512, 856, 340, 76),
         solid((255, 183, 197), 0.85), aa=3.0)
    draw(cv, (512 - 348, 852 - 84, 512 + 348, 852 + 84), sd_ellipse(512, 856, 268, 54),
         solid((255, 205, 214), 0.9), aa=3.0)

    OUT = (176, 106, 54)      # soft outline brown-orange
    FUR = (250, 166, 74)      # warm orange
    FUR_D = (232, 132, 44)    # stripes
    CREAM = (255, 226, 178)   # belly / muzzle
    PINK = (255, 133, 161)
    NOSE = (244, 104, 132)

    # --- tail: chain of circles curling up the right side ---
    tail_pts = []
    for i in range(21):
        t = i / 20.0
        ang = -0.5 + t * 2.05
        cx = 688 + math.cos(ang) * 128
        cy = 800 - math.sin(t * math.pi) * 168 - t * 26
        tail_pts.append((cx, cy, 40 - t * 7))
    for cx, cy, r in tail_pts:
        draw(cv, (cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8),
             sd_circle(cx, cy, r + 5), solid(OUT), aa=1.4)
    for cx, cy, r in tail_pts:
        draw(cv, (cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4),
             sd_circle(cx, cy, r), solid(FUR), aa=1.4)
    tx, ty, tr = tail_pts[-1]
    draw(cv, (tx - tr - 4, ty - tr - 4, tx + tr + 4, ty + tr + 4),
         sd_circle(tx, ty, tr), solid(CREAM), aa=1.4)  # cream tail tip

    # --- body ---
    draw(cv, (512 - 232, 470 - 8, 512 + 232, 880), sd_ellipse(512, 672, 224, 204),
         solid(OUT), aa=1.6)
    draw(cv, (512 - 224, 470, 512 + 224, 872), sd_ellipse(512, 672, 216, 196),
         solid(FUR), aa=1.6)
    draw(cv, (512 - 130, 600, 512 + 130, 880), sd_ellipse(512, 742, 122, 126),
         solid(CREAM), aa=2.0)

    # feet
    for fx in (392, 632):
        draw(cv, (fx - 76, 800, fx + 76, 892), sd_ellipse(fx, 846, 70, 44),
             solid(OUT), aa=1.6)
        draw(cv, (fx - 70, 802, fx + 70, 888), sd_ellipse(fx, 846, 63, 38),
             solid(FUR), aa=1.6)
        for txo in (-24, 0, 24):  # toe beans lines
            draw(cv, (fx + txo - 3, 826, fx + txo + 3, 852),
                 sd_capsule(fx + txo, 830, fx + txo, 848, 2.2), solid(OUT, 0.55), aa=1.2)

    # --- ears (behind head) ---
    ear_l = [(372, 268), (330, 108), (486, 190)]
    ear_r = [(652, 268), (694, 108), (538, 190)]
    for ear in (ear_l, ear_r):
        big = [(512 + (x - 512) * 1.07, 268 + (y - 268) * 1.10) for (x, y) in ear]
        draw(cv, (min(p[0] for p in big) - 4, min(p[1] for p in big) - 4,
                  max(p[0] for p in big) + 4, max(p[1] for p in big) + 4),
             sd_poly(big), solid(OUT), aa=1.8)
        draw(cv, (min(p[0] for p in ear) - 4, min(p[1] for p in ear) - 4,
                  max(p[0] for p in ear) + 4, max(p[1] for p in ear) + 4),
             sd_poly(ear), solid(FUR), aa=1.8)
    for ear, inset in ((ear_l, 0.55), (ear_r, 0.55)):
        cx = sum(p[0] for p in ear) / 3
        cy = sum(p[1] for p in ear) / 3
        small = [(cx + (x - cx) * inset, cy + (y - cy) * inset) for (x, y) in ear]
        draw(cv, (min(p[0] for p in small) - 4, min(p[1] for p in small) - 4,
                  max(p[0] for p in small) + 4, max(p[1] for p in small) + 4),
             sd_poly(small), solid(PINK), aa=2.0)

    # --- head ---
    draw(cv, (512 - 204, 158, 512 + 204, 566), sd_circle(512, 362, 198), solid(OUT), aa=1.6)
    draw(cv, (512 - 196, 166, 512 + 196, 558), sd_circle(512, 362, 190), solid(FUR), aa=1.6)
    # muzzle / cheeks cream patch
    draw(cv, (512 - 128, 396, 512 + 128, 566), sd_ellipse(512, 486, 122, 76),
         solid(CREAM), aa=2.4)

    # forehead stripes
    for dx, ln in ((-52, 44), (0, 54), (52, 44)):
        draw(cv, (512 + dx - 12, 168, 512 + dx + 12, 168 + ln + 10),
             sd_capsule(512 + dx, 178, 512 + dx, 178 + ln, 10), solid(FUR_D, 0.8), aa=1.6)
    # cheek stripes
    for sgn in (-1, 1):
        for k, yy in enumerate((392, 428)):
            x0 = 512 + sgn * 148
            draw(cv, (min(x0, x0 + sgn * 44) - 10, yy - 10, max(x0, x0 + sgn * 44) + 10, yy + 10),
                 sd_capsule(x0, yy, x0 + sgn * 42, yy + 4, 8), solid(FUR_D, 0.65), aa=1.6)

    # --- eyes: big, glossy ---
    for ex in (424, 600):
        draw(cv, (ex - 47, 330, ex + 47, 452), sd_ellipse(ex, 392, 41, 55),
             solid((74, 44, 30)), aa=1.6)
        draw(cv, (ex - 30, 344, ex + 4, 392), sd_circle(ex - 13, 368, 15),
             solid((255, 255, 255), 0.95), aa=1.6)
        draw(cv, (ex + 2, 398, ex + 26, 424), sd_circle(ex + 13, 411, 8),
             solid((255, 255, 255), 0.85), aa=1.6)

    # nose + mouth
    nose = [(512 - 17, 452), (512 + 17, 452), (512, 472)]
    draw(cv, (512 - 20, 449, 512 + 20, 475), sd_poly(nose), solid(NOSE), aa=1.6)
    for sgn in (-1, 1):  # little 'w' mouth arcs via capsules
        draw(cv, (512 + sgn * 2 - 32, 470, 512 + sgn * 32 + 4, 504),
             sd_capsule(512 + sgn * 3, 476, 512 + sgn * 26, 490, 3.4), solid(OUT, 0.85), aa=1.2)

    # blush
    for bx in (368, 656):
        draw(cv, (bx - 52, 448, bx + 52, 508), sd_ellipse(bx, 478, 44, 24),
             solid((255, 120, 150), 0.5), aa=15.0)

    # whiskers
    for sgn in (-1, 1):
        for k, (dy, tilt) in enumerate(((-6, -7), (6, 0), (18, 8))):
            x0 = 512 + sgn * 118
            x1 = 512 + sgn * 218
            draw(cv, (min(x0, x1) - 4, 452 + dy - 12, max(x0, x1) + 4, 452 + dy + tilt + 12),
                 sd_capsule(x0, 458 + dy, x1, 458 + dy + tilt, 2.4),
                 solid((255, 250, 244), 0.75), aa=1.2)

    # --- front paws holding a heart on the belly ---
    for px in (446, 578):
        draw(cv, (px - 40, 618, px + 40, 706), sd_ellipse(px, 664, 34, 42),
             solid(OUT), aa=1.6)
        draw(cv, (px - 34, 622, px + 34, 700), sd_ellipse(px, 664, 28, 36),
             solid(FUR), aa=1.6)
    draw(cv, (512 - 66, 596, 512 + 66, 716), sd_heart(512, 648, 62),
         solid((214, 84, 110)), aa=1.8)
    draw(cv, (512 - 60, 602, 512 + 60, 710), sd_heart(512, 650, 55),
         solid((255, 92, 128)), aa=1.8)
    draw(cv, (512 - 60, 602, 512 + 60, 710), sd_heart(512, 650, 55),
         lambda x, y: (255, 150, 175, clamp((512 - 18 - x) / 130 + (650 - 26 - y) / 200, 0, 0.5)),
         aa=2.0)  # soft top-left sheen

    # --- PNG encode (deterministic) ---
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        raw.append(0)
        raw += cv.p[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", comp)
           + chunk(b"IEND", b""))
    out = os.environ.get("ENTRY_OUT", "/output/entry.png")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(png)
    print(f"wrote {out}: {len(png)} bytes")


if __name__ == "__main__":
    main()

# --- make.fun entry notes (cutest-picture-01) -----------------------------
# Entrant: @urelkdubdqwr. Deterministic generative art: pure stdlib SDF
# rasterizer, fixed seedless math only, so every run writes the identical
# PNG bytes to /output/entry.png.
# Cuteness levers, in order: eye size and gloss, cheek blush, the heart
# held in both paws, toe beans, and a cream-tipped curled tail.
