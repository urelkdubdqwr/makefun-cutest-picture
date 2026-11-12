#!/usr/bin/env python3
"""BERRY BUNNY — generative art for make.fun 'Make the cutest picture' (v2).

Maximum chibi: a cream bunny whose head fills most of the frame, with huge
glossy eyes and a tiny body, hugging one big strawberry. Pure Python 3
stdlib, fully deterministic (fixed constants only), writes
/output/entry.png (override with ENTRY_OUT for local runs).
"""
import math, os, struct, zlib

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

    def vgrad(self, stops, y_top=0, y_bot=None):
        if y_bot is None:
            y_bot = self.h
        for y in range(y_top, y_bot):
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


def sd_capsule(x1, y1, x2, y2, r):
    def f(px, py):
        ex, ey = x2 - x1, y2 - y1
        wx, wy = px - x1, py - y1
        t = clamp((wx * ex + wy * ey) / (ex * ex + ey * ey), 0.0, 1.0)
        return math.hypot(wx - ex * t, wy - ey * t) - r
    return f


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


def main():
    cv = Canvas(W, H)

    OUT = (170, 116, 128)        # soft mauve outline
    FUR = (255, 247, 238)        # warm cream white
    PINK = (255, 158, 180)       # inner ear / accents
    BLUSH = (255, 110, 150)

    # --- background: bubblegum pink melting into lilac ---
    cv.vgrad([(0.0, (250, 158, 203)), (0.55, (243, 168, 216)),
              (1.0, (203, 172, 246))])

    # soft halo behind the head so the cream fur pops off the pastel bg
    draw(cv, (512 - 430, 400 - 430, 512 + 430, 400 + 430), sd_circle(512, 400, 418),
         solid((255, 255, 255), 0.30), aa=60.0)

    # a few sparkles, kept sparse and out of the face
    for cx, cy, r in ((120, 150, 30), (906, 128, 24), (948, 470, 19), (74, 500, 17),
                      (842, 838, 21), (150, 856, 18)):
        draw(cv, (cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3), sd_sparkle(cx, cy, r),
             solid((255, 244, 190), 0.95), aa=1.6)
    for cx, cy, s in ((168, 300, 22), (872, 300, 18)):
        draw(cv, (cx - s - 4, cy - s - 4, cx + s + 4, cy + s + 4), sd_heart(cx, cy, s),
             solid((255, 120, 160), 0.85), aa=1.6)

    # ground shadow
    draw(cv, (512 - 320, 902 - 52, 512 + 320, 902 + 52), sd_ellipse(512, 908, 308, 46),
         solid((178, 110, 160), 0.35), aa=20.0)

    # --- ears: chains of circles leaning outward, pink inside ---
    def ear(x_base, x_tip, lean):
        pts = []
        for i in range(15):
            t = i / 14.0
            cx = x_base + (x_tip - x_base) * t
            cy = 348 - t * 300
            r = 68 - t * 26
            pts.append((cx, cy, r))
        for cx, cy, r in pts:
            draw(cv, (cx - r - 9, cy - r - 9, cx + r + 9, cy + r + 9),
                 sd_circle(cx, cy, r + 7), solid(OUT), aa=1.6)
        for cx, cy, r in pts:
            draw(cv, (cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4),
                 sd_circle(cx, cy, r), solid(FUR), aa=1.6)
        # inner ear: one smooth pink capsule, no segment bumps
        ix0 = x_base + (x_tip - x_base) * 0.16 + lean
        iy0 = 348 - 0.16 * 300
        ix1 = x_base + (x_tip - x_base) * 0.84 + lean
        iy1 = 348 - 0.84 * 300
        draw(cv, (min(ix0, ix1) - 34, iy1 - 34, max(ix0, ix1) + 34, iy0 + 34),
             sd_capsule(ix0, iy0, ix1, iy1, 25), solid(PINK), aa=1.8)
    ear(408, 344, 6)
    ear(616, 680, -6)

    # --- tiny body peeking out under the head ---
    draw(cv, (512 - 176, 690, 512 + 176, 946), sd_ellipse(512, 818, 168, 122),
         solid(OUT), aa=1.6)
    draw(cv, (512 - 168, 694, 512 + 168, 940), sd_ellipse(512, 818, 160, 116),
         solid(FUR), aa=1.6)

    # feet with pink pads
    for fx in (378, 646):
        draw(cv, (fx - 70, 872, fx + 70, 950), sd_ellipse(fx, 912, 63, 36),
             solid(OUT), aa=1.6)
        draw(cv, (fx - 63, 876, fx + 63, 946), sd_ellipse(fx, 912, 56, 30),
             solid(FUR), aa=1.6)
        draw(cv, (fx - 24, 896, fx + 24, 930), sd_ellipse(fx, 914, 19, 13),
             solid(PINK), aa=1.6)

    # --- THE HEAD: one huge ellipse, roughly 60% of the frame ---
    draw(cv, (512 - 326, 424 - 286, 512 + 326, 424 + 286), sd_ellipse(512, 424, 318, 280),
         solid(OUT), aa=1.6)
    draw(cv, (512 - 318, 424 - 280, 512 + 318, 424 + 280), sd_ellipse(512, 424, 310, 272),
         solid(FUR), aa=1.6)

    # muzzle patch
    draw(cv, (512 - 128, 462, 512 + 128, 622), sd_ellipse(512, 542, 122, 76),
         solid((255, 255, 255), 0.85), aa=3.0)

    # blush: two big soft ovals
    for bx in (296, 728):
        draw(cv, (bx - 62, 512, bx + 62, 586), sd_ellipse(bx, 549, 54, 30),
             solid(BLUSH, 0.55), aa=16.0)

    # --- EYES: huge, dark and glossy ---
    for ex in (392, 632):
        draw(cv, (ex - 54, 368, ex + 54, 526), sd_ellipse(ex, 447, 47, 71),
             solid((64, 34, 42)), aa=1.6)
        # warm iris glow at the bottom of each eye
        draw(cv, (ex - 40, 452, ex + 40, 522), sd_ellipse(ex, 492, 34, 26),
             solid((178, 84, 96), 0.55), aa=10.0)
        # main highlight + sparkle dot
        draw(cv, (ex - 34, 380, ex + 2, 424), sd_circle(ex - 15, 402, 16),
             solid((255, 255, 255), 0.97), aa=1.6)
        draw(cv, (ex + 2, 452, ex + 28, 484), sd_circle(ex + 14, 468, 9),
             solid((255, 255, 255), 0.9), aa=1.6)

    # nose: tiny rounded triangle
    nose = [(497, 512), (527, 512), (512, 530)]
    draw(cv, (494, 509, 530, 533), sd_poly(nose), solid((244, 108, 138)), aa=1.6)

    # mouth: little open smile with a tongue
    draw(cv, (512 - 26, 532, 512 + 26, 572), sd_ellipse(512, 550, 22, 16),
         solid((146, 62, 74)), aa=1.6)
    draw(cv, (512 - 15, 550, 512 + 15, 570), sd_ellipse(512, 559, 12, 8),
         solid((255, 138, 162)), aa=1.6)

    # --- THE STRAWBERRY: one big juicy prop hugged at chest height ---
    BX, BY, BS = 512, 710, 112
    draw(cv, (BX - BS - 8, BY - BS - 8, BX + BS + 8, BY + BS + 14), sd_heart(BX, BY, BS),
         solid((178, 40, 58)), aa=1.8)
    draw(cv, (BX - BS, BY - BS, BX + BS, BY + BS + 6), sd_heart(BX, BY, BS - 7),
         solid((244, 63, 88)), aa=1.8)
    # glossy sheen on the upper-left of the berry
    draw(cv, (BX - 74, BY - 78, BX - 6, BY - 6), sd_ellipse(BX - 40, BY - 44, 26, 34),
         solid((255, 255, 255), 0.35), aa=12.0)
    # seeds
    seed_rows = ((-44, (-34, 0, 34)), (-8, (-52, -18, 18, 52)), (28, (-40, 0, 40)),
                 (62, (-24, 14)), (92, (0,)))
    for dy, dxs in seed_rows:
        for dx in dxs:
            draw(cv, (BX + dx - 8, BY + dy - 11, BX + dx + 8, BY + dy + 11),
                 sd_ellipse(BX + dx, BY + dy, 5.5, 8.5), solid((255, 226, 170), 0.95), aa=1.4)
    # leafy cap + stem
    leaf = (86, 196, 96)
    for pts in ([(BX - 78, BY - 66), (BX - 6, BY - 62), (BX - 44, BY - 22)],
                [(BX + 78, BY - 66), (BX + 6, BY - 62), (BX + 44, BY - 22)],
                [(BX - 34, BY - 78), (BX + 34, BY - 78), (BX, BY - 26)]):
        draw(cv, (min(p[0] for p in pts) - 4, min(p[1] for p in pts) - 4,
                  max(p[0] for p in pts) + 4, max(p[1] for p in pts) + 4),
             sd_poly(pts), solid(leaf), aa=1.8)
    draw(cv, (BX - 8, BY - 118, BX + 8, BY - 66), sd_capsule(BX, BY - 112, BX + 3, BY - 70, 6),
         solid(leaf), aa=1.6)

    # paws hugging the berry from both sides
    for px in (404, 620):
        draw(cv, (px - 46, 668, px + 46, 764), sd_ellipse(px, 716, 39, 47),
             solid(OUT), aa=1.6)
        draw(cv, (px - 39, 672, px + 39, 758), sd_ellipse(px, 716, 32, 41),
             solid(FUR), aa=1.6)

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

# --- make.fun entry notes (cutest-picture-01, v2) -------------------------
# Entrant: @urelkdubdqwr. Deterministic generative art: pure stdlib SDF
# rasterizer, fixed math only, identical PNG bytes on every run.
# Duel design: chibi proportions first (head ~60% of frame), one red
# prop at chest height as the only saturated object in the scene.
