"""配色。基調色 1 つから、薄色・濃色・強調色を導く。色は #RRGGBB（大文字）。"""

import colorsys
import re
from dataclasses import dataclass

_EMPHASIS = ["#B85A0B", "#0B6E99", "#7A3E9D", "#1E7A4A"]
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class Palette:
    accent: str
    accent_dark: str
    accent_soft: str
    accent_mid: str
    accent_light: str
    emphasis: str
    text: str
    text_sub: str
    line: str
    bg_soft: str
    emphasis_extra: tuple[str, ...] = ()  # 設計図が 2 つ目の強調色を指定したとき


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb) -> str:
    r, g, b = (round(c) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(a: str, b: str, t: float) -> str:
    return _hex(tuple(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b), strict=False)))


def luminance(h: str) -> float:
    def f(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (f(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _hls(h: str):
    r, g, b = (c / 255 for c in _rgb(h))
    return colorsys.rgb_to_hls(r, g, b)


def tint(base: str, t: float) -> str:
    """基調色を白へ t だけ近づけた淡色。RGB で白と混ぜると灰色に見えるので、色相と彩度（65%）を残して明るくする。"""
    h, light, s = _hls(base)
    r, g, b = colorsys.hls_to_rgb(h, light + (1 - light) * t, s * 0.65)
    return _hex((r * 255, g * 255, b * 255))


def is_gray(h: str) -> bool:
    _, light, s = _hls(h)
    return s < 0.15 or light > 0.97 or light < 0.03


def hue_distance(a: str, b: str) -> float:
    d = abs(_hls(a)[0] * 360 - _hls(b)[0] * 360) % 360
    return min(d, 360 - d)


def _readable(color: str) -> str:
    """白地で 4.5:1 になるまで黒へ寄せる（色相は保つ）。"""
    color = color.upper()
    while contrast(color, "#FFFFFF") < 4.5:
        color = mix(color, "#000000", 0.1)
    return color


def derive(base: str, emphasis: str | None = None) -> Palette:
    accent = base.upper()
    # 基調色の文字は白地とパネル地（bg_soft）の両方で読めること
    while contrast(accent, "#FFFFFF") < 4.5 or contrast(accent, "#EEF3F6") < 4.5:
        accent = mix(accent, "#000000", 0.1)
    if emphasis is not None:
        emphasis = _readable(emphasis)
    elif is_gray(accent):
        emphasis = _EMPHASIS[0]
    else:
        emphasis = next(
            (c for c in _EMPHASIS if hue_distance(c, accent) >= 60 and contrast(c, "#FFFFFF") >= 4.5), "#404040"
        )
    accent_mid = tint(accent, 0.52)
    dark_ratio = 0.35
    while contrast(mix(accent, "#000000", dark_ratio), accent_mid) < 4.5 and dark_ratio < 0.8:
        dark_ratio += 0.05  # 濃い基調色の文字が、中間の面（accent_mid）の上でも読めること
    soft_ratio = 0.28
    while contrast("#FFFFFF", tint(accent, soft_ratio)) < 4.5 and soft_ratio > 0:
        soft_ratio = max(0.0, soft_ratio - 0.04)  # 白い文字が、淡い基調色の面（accent_soft）の上でも読めること
    return Palette(
        accent=accent,
        accent_dark=mix(accent, "#000000", dark_ratio),
        accent_soft=tint(accent, soft_ratio),
        accent_mid=accent_mid,
        accent_light=tint(accent, 0.75),
        emphasis=emphasis,
        text="#1A1A1A",
        text_sub="#595959",
        line="#D9DEE3",
        bg_soft="#EEF3F6",
    )


def theme_css(p: Palette, extra: str = "") -> str:
    rows = [
        ("accent", p.accent),
        ("accent-dark", p.accent_dark),
        ("accent-soft", p.accent_soft),
        ("accent-mid", p.accent_mid),
        ("accent-light", p.accent_light),
        ("emphasis", p.emphasis),
        ("text", p.text),
        ("text-sub", p.text_sub),
        ("line", p.line),
        ("bg-soft", p.bg_soft),
    ]
    body = "".join(f"  --{k}: {v};\n" for k, v in rows)
    return f":root {{\n{body}{extra}}}\n"
