"""題・ヘッドメッセージの文字の規約。既定は fontsize.ITEMS、作業フォルダの rules.json で項目ごとに上書きする。"""

import json
from pathlib import Path

from . import fontsize

FILE = "rules.json"
ITEMS = ("title", "lead")
FIELDS = ("size_px", "align")  # size_px は theme.css にも反映、align は検査のみ。font は固定
ALIGNS = ("left", "center", "right")
DEFAULT_FONT = "BIZ UDPゴシック"


def load(work: Path) -> dict[str, dict]:
    sizes = fontsize.current()
    rules = {k: {"size_px": sizes[k], "font": DEFAULT_FONT, "align": "left"} for k in ITEMS}
    f = Path(work) / FILE
    if not f.exists():
        return rules
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{FILE} を読めません: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{FILE} はオブジェクトで書いてください")
    for item, over in data.items():
        if item not in ITEMS or not isinstance(over, dict):
            raise ValueError(f"{FILE}: 未知の項目 {item!r}（{' / '.join(ITEMS)}）")
        for key, val in over.items():
            if key == "font":
                raise ValueError(f"{FILE}: フォントは {DEFAULT_FONT} 固定です")
            if key not in FIELDS:
                raise ValueError(f"{FILE}: {item} の未知のキー {key!r}（{' / '.join(FIELDS)}）")
            if key == "size_px" and not (isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0):
                raise ValueError(f"{FILE}: {item}.size_px は正の数で書いてください")
            if key == "align" and val not in ALIGNS:
                raise ValueError(f"{FILE}: {item}.align は {' / '.join(ALIGNS)} のどれかです")
        rules[item].update(over)
    return rules
