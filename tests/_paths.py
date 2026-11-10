"""テストが参照するパス（リポジトリのルートとプラグイン本体）。import 経路は pyproject.toml の pythonpath で通す。"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "plugins" / "slide-maker"
