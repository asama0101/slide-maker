---
name: doctor
description: slide-maker が動く環境かを点検し、インストール中の版が最新かを確かめる。専用の仮想環境・ライブラリ・chromium・BIZ UDPゴシックの有無と、GitHub をマーケットプレイスに登録していれば新しい版の有無を、項目ごとに伝える。「環境を点検して」「doctor」「最新版か確認して」「動かない原因を調べて」と頼まれたときに使う。資料の作成には使わない（create）。Windows 専用。
compatibility: Windows 専用。Python 3.10 以上。
allowed-tools: 'Bash(python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" doctor)'
---

# slide-maker doctor

環境を変えずに点検して、結果を利用者に伝える。

1. `python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" doctor` を実行する。
2. 終了コード 0 なら、出力の行を項目ごとに伝える。
   - `[OK]`: 一言で済ませる。
   - `[情報]`: 版の行。最新でないとき（「→」の行がある）は、更新の手順を伝える。
   - `[任意]`: BIZ UDPゴシック未導入。PowerPoint で折り返しがずれることがあるだけで、使わなくても動く。
3. 終了コード 3 は、`[NG]` がある（OS・実行環境・保存先、または専用の仮想環境がない・足りない）。出力の `[NG]` の項目と、「→」の対処を伝える。導入（`setup --yes`）は、利用者に「`${CLAUDE_PLUGIN_DATA}` の下に専用の仮想環境と chromium（数百 MB）を入れてよいか」を確かめ、承認を得てから実行する。
