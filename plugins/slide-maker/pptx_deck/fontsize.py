"""文字サイズの項目。既定と CSS 変数を扱う。"""

from typing import NamedTuple


class Item(NamedTuple):
    key: str
    var: str
    default: float
    kind: str  # "px" か "scale"


ITEMS: tuple[Item, ...] = (
    Item("title", "--fs-title", 37, "px"),  # 題
    Item("lead", "--fs-lead", 27, "px"),  # ヘッドメッセージ
    Item("body", "--fs-body", 19, "px"),  # 本文
    Item("caption", "--fs-caption", 16, "px"),  # 注記
    Item("source", "--fs-source", 14, "px"),  # 出典・脚注
    Item("cover-title", "--fs-cover-title", 40, "px"),  # 表紙・章扉の題
    Item("cover-sub", "--fs-cover-sub", 22, "px"),  # 表紙・章扉の副題
    Item("subhead", "--fs-subhead", 22, "px"),  # 小見出し
    Item("num-scale", "--num-scale", 1.0, "scale"),  # 大きな数字の倍率
    Item("chart-scale", "--chart-scale", 1.0, "scale"),  # グラフ内の文字の倍率
)


def current() -> dict[str, float]:
    """文字サイズは変えられないので、常に既定。古い template.json の fontsizes は読まない。"""
    return {it.key: it.default for it in ITEMS}


def css(values: dict[str, float]) -> str:
    """:root の中に置く変数の行。"""
    rows = []
    for it in ITEMS:
        v = values.get(it.key, it.default)
        rows.append(f"  {it.var}: {v:g}{'px' if it.kind == 'px' else ''};\n")
    return "".join(rows)
