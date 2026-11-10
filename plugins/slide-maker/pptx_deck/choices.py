"""Artifact（スライド案の選択ページ）が書いた選択結果の読み込み。

選択結果は、スライド 1 枚につき 1 ファイル `<dir>/choices/<NN>.json`（NN はスライド番号 2 桁）。
中身は `{"at": …, "comment": "…", "pick": "R3", "status": "saved" | "approved"}`。"""

import json
from pathlib import Path

from . import paths


def load(base: Path) -> dict[str, dict]:
    """`base` は `choices/` フォルダを含むフォルダ（`ArtifactData` の `out_dir` に渡したもの）。
    スライド番号 → {"pick": str | None, "comment": str, "status": str}。読めないファイルは全件まとめて ValueError。"""
    d = Path(base) / "choices"
    if not d.is_dir():
        raise ValueError(f"{d} がありません（--choices には choices/ を含むフォルダを渡してください）")
    out: dict[str, dict] = {}
    errors: list[str] = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(paths.read_text(f))
            if not isinstance(data, dict):
                raise ValueError("JSON のオブジェクトではありません")
        except ValueError as e:
            errors.append(f"{f.name}: 読めません（{e}）")
            continue
        out[f.stem] = {
            "pick": data.get("pick") or None,
            "comment": str(data.get("comment") or "").strip(),
            "status": data.get("status", ""),
        }
    if errors:
        raise ValueError("\n".join(errors))
    return out
