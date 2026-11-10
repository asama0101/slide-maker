"""GitHub をマーケットプレイスとして登録しているとき、インストール中の版が最新かを調べる（doctor 用）。

標準ライブラリのみ。
"""

import json
import os
import re
from pathlib import Path
from urllib.request import urlopen

PLUGIN_JSON = "plugins/slide-maker/.claude-plugin/plugin.json"  # マーケットプレイスのリポジトリ内の場所
TIMEOUT = 5


def _config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def registered_repo(repository: str) -> str | None:
    """known_marketplaces.json に、このプラグインのリポジトリが GitHub として登録されていれば `owner/repo` を返す。"""
    m = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", repository)
    if not m:
        return None
    try:
        data = json.loads((_config_dir() / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for entry in data.values() if isinstance(data, dict) else ():
        src = entry.get("source", {}) if isinstance(entry, dict) else {}
        if src.get("source") == "github" and str(src.get("repo", "")).lower() == m.group(1).lower():
            return m.group(1)
    return None


def _ver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-")[0]))


def check(current: str, plugin_root: Path) -> dict | None:
    """未登録なら None。登録済みなら {"repo", "latest", "up_to_date"}、取得できなければ {"repo", "error"}。"""
    try:
        manifest = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    repo = registered_repo(str(manifest.get("repository", "")))
    if repo is None:
        return None
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{PLUGIN_JSON}"
    try:
        with urlopen(url, timeout=TIMEOUT) as r:  # noqa: S310  # https 固定の URL
            latest = str(json.load(r)["version"])
    except (OSError, ValueError, KeyError) as e:  # URLError は OSError の子
        return {"repo": repo, "error": f"最新版を取得できませんでした（{e}）"}
    return {"repo": repo, "latest": latest, "up_to_date": _ver(current) >= _ver(latest)}
