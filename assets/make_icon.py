"""Generuje assets/icon.ico (bez zewnętrznych bibliotek).

Wzór jak ekran startowy: zaokrąglony kwadrat przecięty ukośnie –
lewa strona fioletowa ze strzałką w dół (klient), prawa niebieska
ze strzałką w górę (host). Uruchom: python assets/make_icon.py [podgląd.png]
"""
import os
import struct
import sys
import zlib

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
SS = 4  # próbek na oś piksela (antyaliasing)


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


PURPLE_TOP, PURPLE_BOT = hex_rgb("#a855f7"), hex_rgb("#6d28d9")
BLUE_TOP, BLUE_BOT = hex_rgb("#60a5fa"), hex_rgb("#2563eb")
WHITE = (255, 255, 255)


def line_x(y):
    return 0.62 - 0.24 * y


def in_rounded_square(x, y, m=0.03, r=0.22):
    if not (m <= x <= 1 - m and m <= y <= 1 - m):
        return False
    cx = min(max(x, m + r), 1 - m - r)
    cy = min(max(y, m + r), 1 - m - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_arrow(x, y, cx, down):
    if not down:
        y = 1 - y  # strzałka w górę = odbita strzałka w dół
    if abs(x - cx) <= 0.055 and 0.25 <= y <= 0.55:
        return True
    return 0.48 <= y <= 0.74 and abs(x - cx) <= 0.16 * (0.74 - y) / 0.26


def sample(x, y):
    if not in_rounded_square(x, y):
        return None
    lx = line_x(y)
    if in_arrow(x, y, 0.27, True) and x < lx - 0.04 or in_arrow(x, y, 0.73, False) and x > lx + 0.04:
        return WHITE
    # odległość od przekątnej (wektor normalny linii x = 0.62 - 0.24y)
    d = abs(x - lx) / (1 + 0.24 ** 2) ** 0.5
    if d < 0.016:
        return WHITE
    if d < 0.045:  # poświata wokół linii
        base = lerp(PURPLE_TOP, PURPLE_BOT, y) if x < lx else lerp(BLUE_TOP, BLUE_BOT, y)
        return lerp(base, WHITE, 0.35 * (1 - (d - 0.016) / 0.029))
    return lerp(PURPLE_TOP, PURPLE_BOT, y) if x < lx else lerp(BLUE_TOP, BLUE_BOT, y)


def render(size):
    rows = []
    n = SS * SS
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                for sx in range(SS):
                    c = sample((px + (sx + 0.5) / SS) / size, (py + (sy + 0.5) / SS) / size)
                    if c:
                        r += c[0]; g += c[1]; b += c[2]; a += 1
            if a:
                row += bytes((round(r / a), round(g / a), round(b / a), round(255 * a / n)))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return rows


def png(size, rows):
    def chunk(tag, data):
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xffffffff)
    raw = b"".join(b"\0" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def bmp(size, rows):
    """Klasyczny wpis ICO (DIB 32 bpp) – najlepiej obsługiwany przez Eksplorator."""
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = bytearray()
    for r in reversed(rows):  # DIB zapisuje wiersze od dołu
        for i in range(0, len(r), 4):
            pixels += bytes((r[i + 2], r[i + 1], r[i], r[i + 3]))  # RGBA -> BGRA
    mask_row = ((size + 31) // 32) * 4
    return header + bytes(pixels) + bytes(mask_row * size)


def main():
    rendered = [(s, render(s)) for s in SIZES]
    # 256 px jako PNG (standard Windows), mniejsze jako BMP
    images = [(s, png(s, r) if s == 256 else bmp(s, r)) for s, r in rendered]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b"", b""
    for s, img in images:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset + len(data))
        data += img
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    with open(out, "wb") as f:
        f.write(header + entries + data)
    print("Zapisano", out)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "wb") as f:
            f.write(png(256, rendered[-1][1]))


if __name__ == "__main__":
    main()
