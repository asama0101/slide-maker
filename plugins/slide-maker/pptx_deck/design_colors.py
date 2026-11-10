"""設計図（design.md）の `基調色:`・`強調色:` から配色を作る。"""

import dataclasses
import re
from pathlib import Path

from . import theme

DEFAULT_ACCENT = "#1F3A5F"
_LINE = re.compile(r"^\s*(?:-\s+)?(基調色|強調色)\s*[:：]\s*(.+?)\s*$", re.MULTILINE)


def _hex(value: str, source: str = "設計図の基調色") -> str:
    value = value.strip()
    if not theme._HEX.match(value):
        raise ValueError(f"{source}が #RRGGBB ではありません: {value}")
    return value.upper()


def _read_design(work: Path) -> tuple[str | None, list[str]]:
    path = Path(work) / "design.md"
    if not path.is_file():
        return None, []
    found = dict(_LINE.findall(path.read_text(encoding="utf-8")))
    accent = _hex(found["基調色"]) if "基調色" in found else None
    emphasis = [_hex(c, "設計図の強調色") for c in found["強調色"].split(",")][:2] if "強調色" in found else []
    return accent, emphasis


def load(work: Path, cfg: dict, template_accents: tuple[str, ...] = ()) -> theme.Palette:
    """設計図 → cfg の color（旧形式）→ テンプレートの accent1・accent2 → 既定の順で色を決める。"""
    accent, emphasis = _read_design(work)
    if accent is None:
        if cfg.get("color"):
            accent = _hex(cfg["color"], "template.json の color（旧形式の基調色）")
        elif template_accents:
            accent = _hex(template_accents[0])
            if not emphasis and len(template_accents) > 1:
                emphasis = [_hex(template_accents[1])]
        else:
            accent = DEFAULT_ACCENT
    p = theme.derive(accent, emphasis[0] if emphasis else None)
    return dataclasses.replace(p, emphasis_extra=tuple(theme._readable(c) for c in emphasis[1:]))


def load_for(work: Path, cfg: dict) -> theme.Palette:
    """load に、cfg のテンプレートの accent1・accent2 を渡す。"""
    from . import template

    return load(Path(work), cfg, template.accent_colors(Path(work) / cfg["template"]))


def chromatic_budget(p: theme.Palette) -> list[str]:
    """検査用。基調色と強調色の #RRGGBB の並び。"""
    return [p.accent, p.emphasis, *p.emphasis_extra]
