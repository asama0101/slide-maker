---
name: template
description: 利用者の PowerPoint テンプレート（.potx / .pptx）を、名前を付けて置き場に登録し、一覧を見る、消す。登録したテンプレートは、create で資料を作るとき、名前で選べる。「テンプレートを登録したい」「テンプレートの一覧を見たい」「登録したテンプレートを消したい」と頼まれたときに使う。資料の作成には使わない（create）。Windows 専用。
compatibility: Windows 専用。create と同じ環境（Python・python-pptx）。
allowed-tools: 'Bash(python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" template-list) Bash(python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" template-import *) Bash(python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" template-remove *)'
---

# slide-maker template

`${CLAUDE_PLUGIN_ROOT}` は、このプラグインのフォルダ。コマンドはすべて `python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" …`。環境が足りず終了コード 3 になったときは、create の 0 章（`${CLAUDE_PLUGIN_ROOT}/skills/create/SKILL.md`）に従う。

登録したテンプレートは、`${CLAUDE_PLUGIN_DATA}` の下の `templates/<名前>.potx`（または `.pptx`）に置かれる。プラグインを更新しても残る。この PC だけの置き場で、プラグインをアンインストールすると消える。

テンプレートから使うレイアウトは、表紙・本文・裏表紙の 3 つ。名前で探し、見つからない表紙・裏表紙は本文で代える。章扉・目次などの専用レイアウトは使わない（本文で代える）。

作成済みの成果物は、作業フォルダの `_template/` にコピーを持つので、登録を消しても、置き換えても影響しない。

## 手順

利用者の頼みが「登録」「一覧」「削除」のどれかが分からないときだけ、AskUserQuestion で聞く。

### 登録する

1. 登録するファイルのパス（`.potx` または `.pptx`）を聞く。登録名は、省略するとファイル名（拡張子なし）になる。変えたいときだけ聞く。
2. `python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" template-import "<パス>" [--name "<登録名>"]`。
   - 成功（終了コード 0）: 出力の `name`・`path` を伝える。
   - 終了コード 2: 標準エラーのメッセージを、そのまま利用者に伝える。何も登録されていない。16:9（13.33×7.5in）でない、本文のレイアウト（タイトルと本文の領域があるもの）がない、名前に使えない文字がある、ファイルが開けない、のどれか。
   - 終了コード 4: 同じ名前が既にある。「置き換える（`--force`）」か「別の名前にする」かを聞く。黙って置き換えない。

### 一覧を見る

`python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" template-list`。出力の `name`・`format`・`path` を表にして見せる。空の配列なら、「登録はない」と伝える。

### 消す

1. `template-list` を実行して一覧を見せ、消す名前を選んでもらう。
2. 「作成済みの成果物には影響しない」と伝え、消してよいかを確かめる。
3. `python "${CLAUDE_PLUGIN_ROOT}/run.py" --data "${CLAUDE_PLUGIN_DATA}" template-remove "<名前>"`。終了コード 2 は、その名前がないとき。

## 使い方を伝える

登録が済んだら、資料を作るとき（`/slide-maker:create`）にテンプレートの有無を聞かれるので、そこで登録名を選べると伝える。

## 守ること

- 頼まれた登録・削除以外はしない。置き場のファイルを直接消さない（`template-remove` を使う）。
- テンプレートのファイルの中身を直さない。
