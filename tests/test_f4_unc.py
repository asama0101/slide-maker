"""束 F4: file: URL → パスの変換が UNC のホストを保つ、data-chart の破損、svg の id 接頭辞。"""

# ruff: noqa: S101  # pytest の assert
from pathlib import Path

import pytest
from slide_maker import build, charts, pptxutil, svgids

from tests._measure import model_of

pytestmark = pytest.mark.slow  # ブラウザ（Chromium）で測る


CONVERTERS = {
    "pptxutil": pptxutil.file_url_to_path,
    "build": lambda url: build.url_to_path(url, Path()),
}


@pytest.mark.parametrize("which", list(CONVERTERS), ids=list(CONVERTERS))
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("file://nas/share/a.png", "\\\\nas\\share\\a.png"),
        ("file:///C:/x/a%20b.png", "C:\\x\\a b.png"),
    ],
    ids=["UNC_ホストを保つ", "ドライブとパーセント"],
)
def test_file_URL_をパスにする(which, url, expected):
    assert str(CONVERTERS[which](url)) == expected


CHART_BOX = 'style="position:absolute;left:80px;top:120px;width:600px;height:360px"'
SERIES_OK = '"series":[{"name":"s","values":[1]}]'


def _chart_spec_problems(data_chart):
    m = model_of(f"<div class=\"pp-chart\" {CHART_BOX} data-chart='{data_chart}'></div>")
    (chart,) = (e for e in m[0]["elements"] if e["kind"] == "chart")
    return charts.validate(chart["chart"])


@pytest.mark.parametrize(
    ("data_chart", "messages"),
    [
        ('{"type":"bar",}', ["グラフの指定（data-chart）が JSON として読めません"]),
        (
            '{"type":"bar","categories":["a"],"series":["x"]}',
            ["series の各要素は {name, values} のオブジェクトで指定してください"],
        ),
        ("[1,2]", ["グラフの指定（data-chart）がオブジェクトではありません"]),
        ('{"type":"bar"}', ["categories（カテゴリ）が空です", "series（系列）が空です"]),
        ('{"type":"bar","categories":["a"],"series":"x"}', ["categories と series は配列で指定してください"]),
        (
            '{"type":"bar","categories":["a"],' + SERIES_OK + ',"axis":5}',
            ["axis はオブジェクトで指定してください"],
        ),
    ],
    ids=[
        "JSON構文エラー",
        "seriesの要素が辞書でない",
        "仕様が辞書でない",
        "必須キーなし",
        "seriesが配列でない",
        "axisが辞書でない",
    ],
)
def test_data_chart_が壊れていても_validate_が理由を返す(data_chart, messages):
    got = _chart_spec_problems(data_chart)
    assert len(got) == len(messages)
    for g, msg in zip(got, messages, strict=True):
        assert g.startswith(msg)


def test_単一引用符の_id_と_href_にも接頭辞を付ける():
    frag = (
        "<div class=\"pp-picture\"><svg><defs><symbol id='i-a'/></defs>"
        "<use href='#i-a'/><use xlink:href=\"#i-a\"/></svg></div>"
    )
    assert svgids.uniquify(frag, "p-") == (
        "<div class=\"pp-picture\"><svg><defs><symbol id='p-i-a'/></defs>"
        "<use href='#p-i-a'/><use xlink:href=\"#p-i-a\"/></svg></div>"
    )


def test_url_の4つの書き方すべてに接頭辞を付ける():
    frag = (
        '<div class="pp-picture"><svg><defs><marker id="m"/></defs>'
        '<path marker-end="url(\'#m\')"/><path marker-end=\'url("#m")\'/><path marker-end="url(#m)"/>'
        '<path style="fill:url( #m )"/></svg></div>'
    )
    assert svgids.uniquify(frag, "p-") == (
        '<div class="pp-picture"><svg><defs><marker id="p-m"/></defs>'
        '<path marker-end="url(\'#p-m\')"/><path marker-end=\'url("#p-m")\'/><path marker-end="url(#p-m)"/>'
        '<path style="fill:url( #p-m )"/></svg></div>'
    )
