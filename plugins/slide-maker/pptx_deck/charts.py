"""グラフ指定 → PowerPoint のネイティブグラフ。色は配色（Palette）から取る。"""

from decimal import ROUND_HALF_UP, Decimal

from lxml import etree
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE as C
from pptx.enum.chart import XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.oxml.ns import qn
from pptx.util import Pt

from .pptxutil import FONT, emu, rgb

TYPES = {
    "bar": C.COLUMN_CLUSTERED,
    "barh": C.BAR_CLUSTERED,
    "line": C.LINE_MARKERS,
    "pie": C.PIE,
    "stacked": C.COLUMN_STACKED,
    "waterfall": C.COLUMN_STACKED,
}
FONT_PT = 12


def chart_pt(scale: float) -> int:
    """グラフ内の文字の大きさ(pt)。既定の 12pt に倍率をかけ、10pt を下限にする。
    倍率は fontsize.current の既定（1.0）。"""
    return max(10, round(FONT_PT * scale))


SMALL_STEP = (
    0.08  # 軸の最大値（axis.max がなければデータの最大）に対する割合。これ未満の増減は、ラベルを棒の外（下）に出す
)


def _check_axis(axis):
    """axis の min・max・major は数値だけ。major は正、min は max 未満。"""
    for k in ("min", "max", "major"):
        if k in axis and (isinstance(axis[k], bool) or not isinstance(axis[k], (int, float))):
            raise ValueError(f"axis の {k} は数値で指定してください（{axis[k]!r}）")
    if "major" in axis and axis["major"] <= 0:
        raise ValueError(f"axis の major（目盛の間隔）は 0 より大きい数にしてください（{axis['major']}）")
    if "min" in axis and "max" in axis and axis["min"] >= axis["max"]:
        raise ValueError(f"axis の min は max より小さくしてください（min={axis['min']}, max={axis['max']}）")


def validate(spec) -> list[str]:
    """グラフ指定の問題を文にして返す（空なら正常）。check_model と add_chart が使う。"""
    if not isinstance(spec, dict):
        return ["グラフの指定（data-chart）がオブジェクトではありません"]
    if spec.get("_error"):
        return [f"グラフの指定（data-chart）が JSON として読めません（{spec['_error']}）"]
    t = spec.get("type")
    if not isinstance(t, str) or t not in TYPES:
        return [f"未対応のグラフ型: {t}（{', '.join(TYPES)}）"]
    out = []
    cats, series = spec.get("categories") or [], spec.get("series") or []
    if not isinstance(cats, list) or not isinstance(series, list):
        return ["categories と series は配列で指定してください"]
    if not all(isinstance(s, dict) for s in series):
        return ["series の各要素は {name, values} のオブジェクトで指定してください"]
    if not isinstance(spec.get("axis") or {}, dict):
        return ["axis はオブジェクトで指定してください"]
    if not cats:
        out.append("categories（カテゴリ）が空です")
    if not series:
        out.append("series（系列）が空です")
    hl = spec.get("highlight")
    for h in [] if hl is None else hl if isinstance(hl, (list, tuple)) else [hl]:
        if isinstance(h, bool) or not isinstance(h, int) or not 0 <= h < len(cats):
            out.append(f"highlight {h!r} が範囲外です（0 〜 {len(cats) - 1}）")
    try:
        _check_axis(spec.get("axis") or {})
    except ValueError as e:
        out.append(str(e))
    gap, fmt = spec.get("gap", 60), spec.get("fmt", "")
    if isinstance(gap, bool) or not isinstance(gap, (int, float)) or not 0 <= gap <= 500:
        out.append(f"gap（棒の間隔 %）は 0 〜 500 の数値で指定してください（{gap!r}）")
    if not isinstance(fmt, str):
        out.append(f"fmt（数値の書式）は文字列で指定してください（{fmt!r}）")
    for i, ser in enumerate(series):
        if not isinstance(ser.get("name"), str):
            out.append(f"series {i + 1} 番目の name は文字列で指定してください（{ser.get('name')!r}）")
        vals = ser.get("values")
        if (
            not isinstance(vals, (list, tuple))
            or (cats and len(vals) != len(cats))
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in vals)
        ):
            out.append(
                f"series {i + 1} 番目（{ser.get('name', '')}）の values は、"
                f"カテゴリ数（{len(cats)}）と同じ長さの数値の配列にしてください"
            )
    if t == "waterfall" and len(series) > 1:
        out.append("waterfall の series は 1 つだけです（2 つ目以降は描かれません）")
    totals = spec.get("totals")
    if t == "waterfall" and totals is not None and series and not out:
        n = len(series[0]["values"])
        if not (isinstance(totals, list) and all(type(i) is int and 0 <= i < n for i in totals)):
            out.append(f"totals は 0 以上 {n} 未満の整数の配列にしてください")
    if t == "waterfall" and series and not out:
        try:
            waterfall_series(series[0]["values"], spec.get("totals"))
        except ValueError as e:
            out.append(str(e))
    return out


def _plain(v: float) -> str:
    """指数表記にしない数字（数値書式の条件とラベルに使う。PowerPoint は 1.02e+07 を解釈できない）。"""
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _label_text(value: float, fmt: str) -> str:
    """数値書式 fmt の最初の区画で value を文字にする（小さい段のラベル用）。
    反映するのは、小数の桁数・桁区切り・引用符で囲んだ前置き／後置き。解釈できない書式は _plain。"""
    first = fmt.split(";")[0]
    while "[" in first and "]" in first:
        first = first[: first.index("[")] + first[first.index("]") + 1 :]
    prefix, number, suffix, quoted, pct = "", "", "", False, False
    for part in first.split('"'):
        if quoted:
            if number:
                suffix += part
            else:
                prefix += part
        else:
            seen = bool(number)
            for c in part:  # 引用符の外の % は値を 100 倍にして、書式の位置に出す
                if c in "#0?":
                    seen = True
                elif c == "%":
                    pct = True
                    if seen:
                        suffix += c
                    else:
                        prefix += c
            body = "".join(c for c in part if c in "#0?,.")
            if body:
                if number:
                    return _plain(value)  # 数値部分が 2 か所ある書式は解釈しない
                number = body
        quoted = not quoted
    if not any(c in number for c in "0#"):
        return _plain(value)
    decimals = len(number.split(".", 1)[1].replace(",", "")) if "." in number else 0
    comma = "," if "," in number.split(".")[0] else ""
    q = Decimal(1).scaleb(-decimals)
    num = (Decimal(str(value)) * (100 if pct else 1)).quantize(
        q, rounding=ROUND_HALF_UP
    )  # Excel は 0.5 を絶対値の大きい側へ丸める
    return f"{prefix}{num:{comma}.{decimals}f}{suffix}"


def _axis_fmt(fmt: str) -> str:
    """軸の目盛の書式。ラベルの fmt から条件（[>=2000] など）と 2 区画目以降（負・ゼロの書式）を外し、
    正の数の書式だけ使う。"""
    first = fmt.split(";")[0]
    while "[" in first and "]" in first:
        first = first[: first.index("[")] + first[first.index("]") + 1 :]
    return first or "#,##0"


def _highlights(spec) -> set:
    """highlight は 0 始まりの番号か、その配列。"""
    h = spec.get("highlight")
    if h is None:
        return set()
    return set(h) if isinstance(h, (list, tuple)) else {h}


def waterfall_series(values, totals):
    n = len(values)
    totals = set(totals if totals is not None else [0, n - 1])
    base, up, down, tot = [], [], [], []
    run = 0
    for i, v in enumerate(values):
        if i in totals:
            base.append(0)
            up.append(0)
            down.append(0)
            tot.append(v)
            run = v
        elif v >= 0:
            base.append(run)
            up.append(v)
            down.append(0)
            tot.append(0)
            run += v
        else:
            run += v
            if run < 0:
                raise ValueError(f"累計が 0 未満になります（{i + 1} 番目）。値を確認してください")
            base.append(run)
            up.append(0)
            down.append(-v)
            tot.append(0)
    return {"base": base, "up": up, "down": down, "total": tot}


def _series_colors(p):
    return [p.accent, p.accent_mid, "#8C8C8C", p.accent_dark, "#BFBFBF"]


def _fill(series, hex6):
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = rgb(hex6)


def add_chart(slide, el, palette, scale: float = 1.0):
    spec, r = el["chart"], el["rect"]
    t = spec["type"]
    if problems := validate(spec):
        raise ValueError("; ".join(problems))
    cd = CategoryChartData()
    cd.categories = spec["categories"]
    if t == "waterfall":
        w = waterfall_series(spec["series"][0]["values"], spec.get("totals"))
        for name, key in (("基準", "base"), ("増加", "up"), ("減少", "down"), ("合計", "total")):
            cd.add_series(name, w[key])
    else:
        for s in spec["series"]:
            cd.add_series(s["name"], s["values"])
    gf = slide.shapes.add_chart(TYPES[t], emu(r["x"]), emu(r["y"]), emu(r["w"]), emu(r["h"]), cd)
    chart = gf.chart
    chart.font.size = Pt(chart_pt(scale))
    chart.font.name = FONT
    latin = chart.font._element.find(qn("a:latin"))
    ea = etree.Element(qn("a:ea"))
    ea.set("typeface", FONT)
    latin.addnext(ea)  # 日本語は a:ea の書体で描かれる
    colors = _series_colors(palette)
    fmt = spec.get("fmt", "#,##0")
    plot = chart.plots[0]
    chart.has_title = False

    if t == "pie":
        ser = plot.series[0]
        cycle = [palette.accent, palette.accent_mid, "#8C8C8C", palette.accent_dark, "#BFBFBF"]
        hl = _highlights(spec)
        for i in range(len(spec["categories"])):
            pt = ser.points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = rgb(palette.emphasis if i in hl else cycle[i % 5])
        plot.has_data_labels = True
        plot.data_labels.number_format = fmt
        plot.data_labels.number_format_is_linked = False
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        return

    value_axis = chart.value_axis
    value_axis.has_major_gridlines = False
    value_axis.tick_labels.font.size = Pt(chart_pt(scale))
    value_axis.tick_labels.number_format = _axis_fmt(fmt)  # 目盛の桁区切りをラベルと揃える（30000 → 30,000）
    value_axis.tick_labels.number_format_is_linked = False
    axis = spec.get("axis") or {}  # 小グラフを並べるときは、軸の最小・最大・目盛を全パネルで揃える
    _check_axis(axis)
    if "min" in axis:
        value_axis.minimum_scale = axis["min"]
    if "max" in axis:
        value_axis.maximum_scale = axis["max"]
    if "major" in axis:
        value_axis.major_unit = axis["major"]
    chart.category_axis.tick_labels.font.size = Pt(chart_pt(scale))
    plot.gap_width = spec.get("gap", 60)  # 棒の間隔（%）。幅の狭いグラフで棒を太くするとき小さくする

    if t == "waterfall":
        plot.overlap = 100
        s_base, s_up, s_down, s_tot = plot.series
        s_base.format.fill.background()
        # 増減はどちらも灰（増加＝淡い灰、減少＝濃い灰）、合計は中間の灰。
        # 増加を基調色にすると「良い変化」に見えるので使わない
        _fill(s_up, "#BFBFBF")
        _fill(s_down, "#404040")
        _fill(s_tot, "#767676")
        s_base.data_labels.show_value = False
        # 棒の高さが軸の SMALL_STEP（8%）未満の増減は、棒の中に収まらない。棒の中のラベルは出さず、基準の系列に値を出す
        top = max(sum(parts) for parts in zip(w["base"], w["up"], w["down"], w["total"], strict=False))
        threshold = (axis.get("max") or top) * SMALL_STEP
        for s, color in ((s_up, palette.text), (s_down, "#FFFFFF"), (s_tot, "#FFFFFF")):
            dl = s.data_labels
            dl.show_value = True
            dl.number_format = f'[>={_plain(threshold)}]{_axis_fmt(fmt)};""'
            dl.number_format_is_linked = False
            dl.font.size = Pt(chart_pt(scale))
            dl.font.color.rgb = rgb(color)  # 濃い棒は白、淡い棒は本文色でコントラスト 4.5:1 以上
        # 注目する項目（highlight）だけ強調色。増減のどちらの系列にあるかで塗る点を選ぶ
        for i in _highlights(spec):
            s = s_up if w["up"][i] else s_down if w["down"][i] else s_tot
            pt = s.points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = rgb(palette.emphasis)
            pt.data_label.font.size = Pt(chart_pt(scale))
            pt.data_label.font.color.rgb = rgb("#FFFFFF")
        for i, (u, d) in enumerate(zip(w["up"], w["down"], strict=False)):
            step = u or d
            if 0 < step < threshold:
                lbl = s_base.points[i].data_label
                lbl.text_frame.text = _label_text(step, fmt)
                lbl.position = XL_LABEL_POSITION.INSIDE_END
                for obj in (lbl.font, lbl.text_frame.paragraphs[0].runs[0].font):
                    obj.size = Pt(chart_pt(scale))
                    obj.color.rgb = rgb(palette.text)
        chart.has_legend = False
        return

    for i, ser in enumerate(plot.series):
        if t == "line":
            ser.format.line.color.rgb = rgb(colors[i % 5])
            ser.format.line.width = Pt(2.5)
            ser.marker.format.fill.solid()  # マーカーも系列の色にする（既定のテーマ色だと線と食い違う）
            ser.marker.format.fill.fore_color.rgb = rgb(colors[i % 5])
            ser.marker.format.line.color.rgb = rgb(colors[i % 5])
            ser.smooth = False
        else:
            _fill(ser, colors[i % 5])
    if t in ("bar", "barh"):
        for i in _highlights(spec):  # 注目する棒（1 本か、主張に合わせた数本）だけ強調色
            pt = plot.series[0].points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = rgb(palette.emphasis)
    if t.startswith("stacked"):
        plot.overlap = 100
    plot.has_data_labels = True
    plot.data_labels.number_format = fmt
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.font.size = Pt(chart_pt(scale))
    for ser, s in zip(plot.series, spec["series"], strict=False):
        if s.get("labels") is False:  # 系列ごとにラベルを消す（折れ線で値が重なるとき、注目する系列だけ残す）
            ser.data_labels.show_value = False
    multi = len(plot.series) > 1
    chart.has_legend = multi
    if multi:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
