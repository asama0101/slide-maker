"""体裁の検査（最小限）: はみ出し・重なり・文字の欠落・ヘッダー・フッター領域への侵入・文字サイズの下限。"""

from pathlib import Path

from . import template, theme
from .template import TemplateInfo

SLIDE_W, SLIDE_H = 1280, 720
MIN_PT_DEFAULT, MIN_PT_SMALL = 14, 10  # 本文 / 注記（role=caption|chrome）
OVERLAP_MIN_AREA = 4
SHAPE_KINDS = {"rect", "round", "ellipse", "triangle"}  # build.py の SHAPES と同じ。これ以外は build が止まる


def _v(rule, slide, message, severity="error"):
    return {"rule": rule, "slide": slide, "message": message, "severity": severity}


def errors(violations):
    return [v for v in violations if v["severity"] == "error"]


def _r(el):
    return el.get("box") if el["kind"] == "text" else el["rect"]


def _inter(a, b):
    ix = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    iy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return ix * iy if ix > 0 and iy > 0 else 0


def _contains(a, b, tol=2):
    return (
        a["x"] - tol <= b["x"]
        and a["y"] - tol <= b["y"]
        and a["x"] + a["w"] + tol >= b["x"] + b["w"]
        and a["y"] + a["h"] + tol >= b["y"] + b["h"]
    )


def check_model(
    model,
    info: TemplateInfo,
    palette: theme.Palette | None = None,
    rules: dict | None = None,
    backgrounds: dict[str, str] | None = None,
):
    """backgrounds は template.background_colors の cover・body・closing の背景色（なければ白）。"""
    out = []
    for s in model:
        n = s["index"]
        # スライドが使うレイアウト（表紙・本文・裏表紙）の、ヘッダー・フッター・ロゴの領域で検査する
        li = template.layout_index(info, s)
        keepout = [r.to_dict() for r in template.keepout_for(info, li)]  # 測っていないレイアウトは本文のもの
        els = s["elements"]
        for e in els:
            if e["kind"] == "shape" and e.get("shape") not in SHAPE_KINDS:
                out.append(
                    _v(
                        "shapeKind",
                        n,
                        f'shape#{e["idx"]}: data-shape="{e.get("shape")}" は使えません'
                        f"（{' / '.join(sorted(SHAPE_KINDS))}）",
                    )
                )
        for e in els:
            k, rect = e["kind"], _r(e)
            label = f"{k}#{e['idx']}"
            if k == "text":
                if e.get("overflow"):
                    out.append(
                        _v(
                            "overflow",
                            n,
                            f"{label}: 文字が枠からはみ出しています。幅・高さを広げるか文章を減らしてください",
                        )
                    )
                if e.get("lost"):
                    out.append(
                        _v(
                            "textLost",
                            n,
                            f"{label}: 「{e['lost'][:20]}」が PPTX に入りません。"
                            "段落は p・div・li で並べ、入れ子の ul や段落と混ざった裸の文字を使わないでください",
                        )
                    )
                for p in e["paras"]:
                    for run in p["runs"]:
                        if "text" not in run:
                            continue
                        pt = run["size_px"] * 0.75
                        small = e.get("role") in ("caption", "chrome") or e.get("chrome")
                        floor = MIN_PT_SMALL if small else MIN_PT_DEFAULT
                        if pt < floor:
                            out.append(_v("fontMin", n, f"{label}: {pt:g}pt は下限 {floor}pt 未満です"))
            if k == "table":
                for row in e["table"]["rows"]:
                    for c in row["cells"]:
                        for p in c["paras"]:
                            for run in p["runs"]:
                                if "text" in run and run["size_px"] * 0.75 < MIN_PT_DEFAULT:
                                    out.append(
                                        _v(
                                            "fontMin",
                                            n,
                                            f"{label}: 表の文字 {run['size_px'] * 0.75:g}pt は"
                                            f"下限 {MIN_PT_DEFAULT}pt 未満です",
                                        )
                                    )
            if (
                rect["x"] < -1
                or rect["y"] < -1
                or rect["x"] + rect["w"] > SLIDE_W + 1
                or rect["y"] + rect["h"] > SLIDE_H + 1
            ):
                out.append(_v("outOfSlide", n, f"{label}: スライドの外にはみ出しています"))
            if not e.get("chrome") and not e.get("ph") and k != "line":
                for z in keepout:
                    if _inter(rect, z) > OVERLAP_MIN_AREA:
                        out.append(_v("keepout", n, f"{label}: テンプレートのヘッダー・フッター領域に入っています"))
                        break
        # 重なり
        cand = [
            e
            for e in els
            if e["kind"] in ("text", "shape", "image", "table", "chart", "picture")
            and not (e["kind"] == "text" and not e["paras"])
        ]
        for i, a in enumerate(cand):
            for b in cand[i + 1 :]:
                if a["overlap"] or b["overlap"]:
                    continue
                ra, rb = _r(a), _r(b)
                if _inter(ra, rb) <= OVERLAP_MIN_AREA:
                    continue
                if (a["kind"] == "shape" and _contains(ra, rb)) or (b["kind"] == "shape" and _contains(rb, ra)):
                    continue
                out.append(
                    _v(
                        "overlap",
                        n,
                        f"{a['kind']}#{a['idx']} と {b['kind']}#{b['idx']} が重なっています"
                        "（意図的なら data-overlap を両方に付ける）",
                    )
                )
        if palette is not None:
            out += _color_rules(n, els, _slide_bg(s, backgrounds))
        if rules is not None:
            out += _chrome_spec(n, els, rules)
    if palette is not None:
        out += _range_rule(model, palette)
    return out


FONT_ALIASES = {"BIZ UDPGothic": "BIZ UDPゴシック"}  # CSS の英名と PPTX の和名は同じフォント


def _chrome_spec(n, els, rules):
    """題・ヘッドメッセージ（role=title|lead）の大きさ・フォント・配置が規約と違うものを挙げる。"""
    out = []
    for e in els:
        spec = rules.get(e.get("role")) if e["kind"] == "text" else None
        if not spec:
            continue
        paras = e.get("paras") or []
        sizes = {round(r["size_px"]) for p in paras for r in p["runs"] if "size_px" in r}
        aligns = {p["align"] for p in paras if "align" in p}
        diffs = []
        if sizes and sizes != {round(spec["size_px"])}:
            diffs.append(f"文字の大きさ {'/'.join(map(str, sorted(sizes)))}px（規約 {spec['size_px']:g}px）")
        if e.get("family") and FONT_ALIASES.get(e["family"], e["family"]) != FONT_ALIASES.get(
            spec["font"], spec["font"]
        ):
            diffs.append(f"フォント {e['family']}（規約 {spec['font']}）")
        if aligns and aligns != {spec["align"]}:
            diffs.append(f"配置 {'/'.join(sorted(aligns))}（規約 {spec['align']}）")
        if diffs:
            out.append(_v("chromeSpec", n, f"text#{e['idx']}（{e['role']}）が規約と違います: " + "、".join(diffs)))
    return out


HUE_GROUP_DEG = 25  # この範囲に入る色相は同じ色の仲間として数える
MAX_HUE_GROUPS = 3  # 基調色の系統 1 つ + 強調色 2 つ
NEON_MIN = 0.9  # HSV の彩度・明度がどちらもこれを超える色は蛍光色
MIN_TEXT_CONTRAST = 4.5


def _hex6(c):
    return "#" + c.lstrip("#").upper()


def _colors(els):
    """モデルの全色（文字・塗り・線・表のセル）を (#RRGGBB, 場所) で返す。グラフの色は数えない。"""
    out = []
    for e in els:
        if e["kind"] == "chart":
            continue
        label = f"{e['kind']}#{e['idx']}"
        for key in ("fill", "line"):
            if e.get(key):
                out.append((_hex6(e[key]["hex"]), label))
        for p in e.get("paras", []):
            out += [(_hex6(r["color"]), label) for r in p["runs"] if "text" in r and r.get("color")]
        if e["kind"] == "table":
            for row in e["table"]["rows"]:
                for c in row["cells"]:
                    if c.get("fill"):
                        out.append((_hex6(c["fill"]["hex"]), label))
                    for p in c["paras"]:
                        out += [(_hex6(r["color"]), label) for r in p["runs"] if "text" in r and r.get("color")]
    return out


PALE_MAX_SAT, PALE_MIN_LIGHT = 0.35, 0.9  # 彩度が低く明るい色は、淡い灰色として数えない


def _neutral(c, palette):
    """色の系統として数えない色: 彩度の低い色、palette の固定の無彩色、彩度が低く明るい色。"""
    if theme.is_gray(c) or c in (palette.line, palette.bg_soft, palette.text, palette.text_sub):
        return True
    _, light, sat = theme._hls(c)
    return sat < PALE_MAX_SAT and light > PALE_MIN_LIGHT


def _range_rule(model, palette):
    """色相の系統の数は資料全体で数える。palette の色（基調色・強調色とその濃淡）を先頭の代表にして、
    残りを色相順にまとめる（要素の順序に左右されない）。"""
    first = {}  # 色 → 最初に現れたスライド
    for s in model:
        for c, _ in _colors(s["elements"]):
            if not _neutral(c, palette):
                first.setdefault(c, s["index"])
    prio = [palette.accent, palette.emphasis, *palette.emphasis_extra]
    prio += [palette.accent_dark, palette.accent_mid, palette.accent_soft, palette.accent_light]
    prio = [_hex6(c) for c in prio]

    def order(c):
        return (prio.index(c), 0, c) if c in prio else (len(prio), theme._hls(c)[0], c)

    groups = []  # [(代表色, 最初のスライド)]
    for c in sorted(first, key=order):
        for rep, _first in groups:
            if theme.hue_distance(rep, c) <= HUE_GROUP_DEG:
                break
        else:
            groups.append((c, first[c]))
    if len(groups) <= MAX_HUE_GROUPS:
        return []
    extra = ", ".join(f"{rep}（スライド {sl}）" for rep, sl in groups[MAX_HUE_GROUPS:])
    return [
        _v(
            "colorRange",
            groups[MAX_HUE_GROUPS][1],
            f"資料全体で色相の系統が {len(groups)} つあります（上限 {MAX_HUE_GROUPS}）。超えた色: {extra}。"
            "基調色の濃淡か強調色に置き換えてください",
        )
    ]


def _covers(o, cx, cy):
    r = _r(o)
    return r["x"] <= cx <= r["x"] + r["w"] and r["y"] <= cy <= r["y"] + r["h"]


def _slide_bg(slide, backgrounds):
    """スライドが使うレイアウト（表紙・本文・裏表紙）の背景色。"""
    bgs = backgrounds or {}
    kind = slide.get("layout")
    return _hex6(bgs.get(kind if kind in ("cover", "closing") else "body") or bgs.get("body") or "#FFFFFF")


def _color_rules(n, els, slide_bg="#FFFFFF"):
    out = []
    colors = _colors(els)
    for c, where in dict.fromkeys(colors):
        r, g, b = (int(c[i : i + 2], 16) / 255 for i in (1, 3, 5))
        mx, mn = max(r, g, b), min(r, g, b)
        if mx > NEON_MIN and mx > 0 and (mx - mn) / mx > NEON_MIN:
            out.append(_v("colorNeon", n, f"{where}: {c} は蛍光色です。彩度か明度を下げてください"))
    for e in els:
        if e["kind"] != "text":
            continue
        box = e["box"]
        cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2

        if any(o["kind"] == "image" and _covers(o, cx, cy) for o in els):
            continue  # 写真の上は背景が分からないので検査しない
        bg = slide_bg
        for o in els:  # 後ろにあるものほど手前に描かれる
            if o is e or not o.get("fill") or o["kind"] == "chart" or not _covers(o, cx, cy):
                continue
            fill = _hex6(o["fill"]["hex"])
            a = o["fill"].get("a", 1)
            bg = fill if a >= 1 else theme.mix(bg, fill, a)  # 透ける塗りは下の背景と合成する
        for p in e["paras"]:
            for run in p["runs"]:
                if "text" in run and theme.contrast(_hex6(run.get("color", "000000")), bg) < MIN_TEXT_CONTRAST:
                    out.append(
                        _v(
                            "colorContrast",
                            n,
                            f"text#{e['idx']}: 文字色 {_hex6(run.get('color', '000000'))} と背景 {bg} のコントラストが"
                            f" {MIN_TEXT_CONTRAST} 未満です",
                        )
                    )
    return out


def check_pptx(path: Path):
    from pptx import Presentation

    prs = Presentation(str(path))
    W, H = prs.slide_width, prs.slide_height
    tol = 9525
    out = []
    for i, s in enumerate(prs.slides, start=1):
        for sh in s.shapes:
            if sh.left is None:
                continue
            if sh.left < -tol or sh.top < -tol or sh.left + sh.width > W + tol or sh.top + sh.height > H + tol:
                out.append(_v("pptxBounds", i, f"{sh.name}: スライドの外にはみ出しています"))
            if sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    for r in p.runs:
                        if r.font.size is not None and r.font.size.pt < MIN_PT_SMALL:
                            out.append(
                                _v(
                                    "pptxFontMin",
                                    i,
                                    f"{sh.name}: {r.font.size.pt:g}pt は下限 {MIN_PT_SMALL}pt 未満です",
                                )
                            )
    return out
