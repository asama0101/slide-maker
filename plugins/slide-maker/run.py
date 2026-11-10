"""入口。標準ライブラリのみ。専用の仮想環境の Python で slide_maker を実行する。

  python run.py [--data <パス>] setup [--yes]   # 仮想環境の作成（--yes は利用者の承認後）
  python run.py [--data <パス>] <サブコマンド>   # それ以外は専用の仮想環境の Python に渡す

置き場（<パス>\\venv に仮想環境を作る）は、環境変数 SLIDE_MAKER_HOME（優先）か、
先頭の --data（SKILL.md が渡す ${CLAUDE_PLUGIN_DATA}）。
どちらもなければ終了コード 3。
--data の値が不正（未置換の ${ を含む・絶対パスでない・値がない）なら、何もせず終了コード 2。
"""

import os
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 10):  # noqa: UP036  # 古い Python で起動されたときに案内を出すための検査
    print(
        f"Python 3.10 以上が必要です（今は {sys.version_info[0]}.{sys.version_info[1]}）。"
        "venv と ensurepip が使える Python で実行してください。"
    )
    sys.exit(3)

SKILL = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL))

from slide_maker import env, paths  # noqa: E402  標準ライブラリのみで動く

_ENTRY = 'python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}"'


def split_data(argv: list[str]) -> tuple[str | None, list[str]]:
    """argv の先頭の `--data <値>` を取り除く。先頭以外の --data は、サブコマンド側の引数なので触らない。"""
    if argv[:1] != ["--data"]:
        return None, argv
    if len(argv) < 2:
        raise ValueError("--data に置き場のパスがありません")
    return argv[1], argv[2:]


def check_data(value: str, name: str = "--data") -> str:
    """${CLAUDE_PLUGIN_DATA} が置き換わらなかった値や、相対パスは、間違った場所に作らないよう弾く。"""
    if "${" in value:
        raise ValueError(f"{name} が置き換わっていません: {value}（SKILL.md の本文に書いたコマンドで実行してください）")
    if not value.strip() or not Path(value).is_absolute():
        raise ValueError(f"{name} は絶対パスで指定してください: {value!r}")
    return value


def _legacy_note() -> str | None:
    old = Path(os.environ.get("LOCALAPPDATA", "")) / "pptx-deck" / "venv"
    if os.environ.get("LOCALAPPDATA") and old.exists():
        return (
            f"旧い仮想環境（{old}）は使いません。新しい置き場に作り直します（旧い方は不要なら削除してかまいません）。"
        )
    return None


def child_env(base) -> dict:
    """子プロセスの環境。利用者の PYTHONPATH は残し（判定の probe も同じ環境で調べる）、プラグインを先頭に足す。"""
    pp = [str(SKILL), *([base["PYTHONPATH"]] if base.get("PYTHONPATH") else [])]
    return {**base, "PYTHONPATH": os.pathsep.join(pp), "PYTHONUTF8": "1"}


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # 子プロセス（PYTHONUTF8=1）と出力の文字コードをそろえる
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        data, rest = split_data(argv)
        if data is not None:
            check_data(data)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    home = os.environ.get("SLIDE_MAKER_HOME") or data  # 環境変数（テスト・特殊な環境用）が優先
    if home and home != data:
        try:
            check_data(home, "SLIDE_MAKER_HOME")
        except ValueError as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 2
    if not home:
        print("専用の仮想環境の置き場が指定されていません。")
        print(
            f"SKILL.md のコマンドは `{_ENTRY} <サブコマンド>` の形で実行してください"
            "（直接実行するときは、環境変数 SLIDE_MAKER_HOME か `--data <絶対パス>`）。"
        )
        print(
            "仮想環境がまだなければ、利用者に「置き場の下の venv に仮想環境と chromium（数百 MB）を"
            "導入してよいか」を確認し、承認後に同じ形で `setup --yes` を実行してください。"
            "作成元の Python は 3.10 以上で、venv と ensurepip が使えるものにしてください。"
        )
        return 3
    os.environ["SLIDE_MAKER_HOME"] = home  # paths.home_dir() と子プロセスが読む
    if rest[:1] == ["setup"]:
        return env.setup(yes="--yes" in rest)
    sel = env.select_python(refresh=rest[:1] == ["doctor"])  # doctor は実際に調べ直し、キャッシュも更新する
    if sel.path is None:
        if rest[:1] == ["doctor"]:
            print("\n".join(env.diagnosis(sel)))
        print("実行できる専用の仮想環境がありません。")
        print(f"- 仮想環境（{paths.venv_dir()}）: " + "、".join(sel.missing))
        print(
            f"利用者に「{paths.venv_dir()} に仮想環境と chromium"
            "（数百 MB。chromium は Playwright の共有の場所に入る）を導入してよいか」を確認し、"
            f"承認後に `{_ENTRY} setup --yes` を実行してください。"
        )
        note = _legacy_note()
        if note:
            print(note)
        return 3
    return subprocess.call([str(sel.path), "-m", "slide_maker", *rest], env=child_env(os.environ))  # noqa: S603  # 引数は配列、実行ファイルは選んだ Python


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
