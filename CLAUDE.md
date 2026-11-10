# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Windows 専用の Claude Code プラグイン `slide-maker`（`plugins/slide-maker/`）。承認文書を、HTML スライドを経由して編集可能な PPTX にする（機能を絞った）。利用者向けの説明は README.md。

## コマンド

すべてリポジトリのルートで実行する。ビルド設定はなく、検証は `ruff`・`pytest`（設定は `pyproject.toml`。テストの規則は `~/.claude/rules/python-testing.md`）と、プラグイン自身の検査コマンドで行う。

## アーキテクチャ

**2 層に分かれる。** プラグイン（`plugins/slide-maker/`）は読み取り専用で、利用者が作る成果物は別の場所（`<出力先>/slide-maker-source/<成果物名>/` と `<出力先>/<成果物名>.pptx`）に置く。入力・出力先・成果物名はチャットで受け取り、`init` で作業フォルダを作る。コマンドの作業フォルダの引数は `<出力先>/<成果物名>.pptx` のパスでもよい（`paths.resolve_work`。旧配置の `<名前>/source/` は終了コード 2）。確認用の画像は `%TEMP%\slide-maker\<成果物名>-<作業フォルダの絶対パスのハッシュ 8 桁>\`（`paths.temp_dir(name, work)`）。

**実行の入口。** `run.py`・`paths.py`・`env.py` は標準ライブラリだけで動く。`run.py` は、argv の先頭の `--data <パス>`（SKILL.md が渡す `${CLAUDE_PLUGIN_DATA}`。`${` を含む・絶対パスでない・値がないときは終了コード 2）を環境変数 `SLIDE_MAKER_HOME`（あればこちらが優先。テスト用）として子プロセスへ渡し、`paths.home_dir()` はそれだけを読む。どちらもなければ終了コード 3。実行に使う Python は**専用 venv だけ**（`home_dir()/venv/Scripts/python.exe`）。`env.select_python` が版（`requirements.txt`、すべて `==`）と chromium を確かめ、不足なら終了コード 3 で、`setup --yes`（利用者の承認後）を案内する。`doctor` は不足を項目ごとの OK/NG で出す。`run.py` が `python -m slide_maker <サブコマンド>` を子プロセスで実行し、`setup` だけは `run.py` が直接処理する。利用者のテンプレートの置き場は `home_dir()/templates/<名前>.potx|.pptx`（`templatestore.py`。`template-import`・`template-list`・`template-remove`。使うレイアウトは**表紙・本文・裏表紙の 3 つだけ**）。共通の規則は `~/.claude/reference/plugin-rules.md`（章 A）。

**HTML が正本で、PPTX はそこから測って作る。**

1. `<元データ>/design.md`（設計図）→ `script.md`（原稿。`script_lint.py` が検査）。人の承認の関門はない。
2. `<元データ>/slides/` の断片を書く。全ページ `NN-R1.html`〜`NN-R3.html`（2〜3 案。`NN-A.html` は廃止。主役の種類が違う案）。`assets/components/` の型は見本。`candidates.collect` が命名・案の数・番号の連続・SVG の id の一意化を検査し、`review-page` は `{"path", "warnings"}` を出力する（図・絵・表・グラフが主役でない案は警告。表紙・裏表紙・区切りは除く）。色は設計図の `基調色:`・`強調色:`（なければテンプレートの色）で、`init --color` は廃止。題・リードの文字の規約は `rules.json`（`rules.py`）で変えられる。
3. `review-page`（`review_page.py`）が `review.html` を作る。Claude が `Artifact` ツール（`capabilities` は `review_page.CAPABILITIES` = `db` と `comments`（`composer_only`・`customAnchors`）、非公開）で公開し、利用者が 1 ページごとに案の選択・承認をする。画面は「一覧＋大きな表示」（上の帯に進捗、左に状態の印つきの一覧、各ページは選んだ案を大きく、ほかの案は小さな一覧から選ぶ。大きな表示の大きさは全ページで同じ）。スライドは Shadow DOM の中に入れる（共通 CSS の `body`・`*` が画面の枠に効かないように）。ローカルの画像は data URI に埋め込む（12 MiB まで）。コメントは画面の中に欄を持たず、claude.ai の標準のコメントに一本化している: 「このページにコメントする」が `customAnchors` の `compose` で入力を開き、入力が閉じたら `exitMode()` でコメントのモードを終える（`openComposer` だけだとモードが入ったままになり、承認が押せなくなる）。コメントは「Claude に送信」にチェックして送ったものだけ、Claude が `ArtifactComments` で読み・返信・解決できる。ページは、位置（`#pg-NN …`）で特定する。選択結果は `db` の `choices/<NN>`（`{at, comment, pick, status: saved|approved}`。`comment` は常に空）に入り、Claude が `ArtifactData` の `list ... out_dir=<dir>` で `<dir>/choices/<NN>.json` に書き出す。
4. コメントのあるページは、Claude が断片だけ直して同じ Artifact を再公開し、スレッドに返信して解決する。承認済みだったページは、`choices` の `status` を `saved` に戻して、再承認してもらう。`finalize --choices <dir>`（`<dir>` は `choices/` の親）は、全ページ承認済み・`pick` が実在することを確かめて `final.html` を作る。未解決のコメントが残っていないかは、コードではなく Claude の手順（`ArtifactComments`）で確かめる。
5. `measure.py` が Playwright で `final.html` を開き、`measure.js` が `.pp-*` 部品の位置・サイズ・書式をモデルにする。**`pp-text`・`pp-shape`・`pp-line`・`pp-image`・`pp-table`・`pp-chart`・`pp-picture` 以外のクラスは PPTX に出ない。**
6. `cli.py` の `build` が、測ったモデルを `check.check_model` で検査し（エラーがあれば PPTX を作らない）、`build.py` が python-pptx でテンプレート（既定は `assets/template/standard.potx`）の上に書き出し、できた PPTX を `check.check_pptx` で再検査する。検査は `overflow`・`overlap`・`textLost`・`keepout`・`fontMin`・`chromeSpec`・`colorRange`・`colorNeon`・`colorContrast` と、`outOfSlide`・`shapeKind`・`pptxBounds`・`pptxFontMin`。不正な `data-chart` は `build` が `エラー:` で止める。出力先に同名の PPTX があれば `--force` がない限り終了コード 4。グラフは `charts.py` がネイティブのグラフにする。`template.py` がテンプレートからヘッダー・フッター・背景色・3 つのレイアウトを読む。

**絵（`pp-picture`）。** 型に当てはまらない図は、`<div class="pp-picture" data-alt>` の中のインライン SVG で描く。`measure.js` が位置・代替テキスト・内部の文字の大きさと範囲を測り、`measure.py` が絵だけを透過・3 倍の PNG にして `src` に入れ、`build.py` が `pp-picture` という名前の画像として貼る。絵の中身は PowerPoint で直せない。ワークフローは create スキルの 3 章、作法は `references/picture-craft.md`。

**派生ファイルと直し方。** `review.html`・`final.html`・`theme.css`・`base.css`・`chart-preview.js`・`icons/` は再生成できる派生ファイルで、`build` 成功時に `lifecycle.DERIVED_FILES` だけが消される（元データは消さない）。`theme.css`・`base.css`・`chart-preview.js` は `init` 時に `assets/web/` から作業フォルダへ**写される**ので、プラグイン側を直しても既存の作業フォルダには `init --force` まで届かない。作成後の直しは PowerPoint で行い、構成を大きく変えるときは最初から作り直す（revise/rebuild はない。PowerPoint での手直しは取り込まない）。

**ワークフローはスキルが握っている。** `skills/*/SKILL.md`（create・template）が手順を持ち、規則は `references/*.md`（`head-rules`・`html-rules`・`patterns`・`components`・`review-flow`・`check-rules`・`icons`・`picture-craft`）にある。型の追加は `assets/components/` に足したうえで `references/components.md`・`patterns.md` も更新する。アイコン（30 個）は `assets/icons/` と `references/icons.md`。

## 注意

- **レビューページと、スライドのテーマが同じ DOM・同じ CSS 変数を共有する。** `review_page.py` のページ側の変数は `--rv-bg` のように接頭辞を付けてある。`--bg`・`--line`・`--text` などテーマ側（`theme.css`）と同名にすると、スライドの背景や罫線が上書きされて見えなくなる。
- 絵の SVG の中の色は、`base.css` の `sv-f-*`・`sv-s-*`（テーマの変数）で塗る。`marker` は path の終点にだけ付くので、矢印は 1 本ずつ別の path にする。絵を撮るときは、他の部品を `visibility:hidden` にして背景を透明にする（`measure.py` の `_SNAP_CSS`）。`<defs>` の `symbol`・`marker` は、絵の `<svg>` の中に置く。
- `chart-preview.js` はブラウザ用の近似で、`fmt`（桁区切りなど）や軸は PowerPoint の実際のグラフと一致しない。
- `tests/test_docs.py` が文書を検査する: SKILL.md にハードコードしたパス（`C:/Users`・`${CLAUDE_SKILL_DIR}`）を書かない（`${CLAUDE_PLUGIN_ROOT}` を使う）、LibreOffice を依存として書かない（README を含む）、削除したコマンドの名前を文書に書かない。
- 行末は LF 固定（`.gitattributes`）。`docs/*.pdf` は著作物なのでコミットしない。`docs/superpowers/` は `.gitignore` の対象。
- コメント・コミットメッセージ・文書は日本語（既存の履歴に合わせる）。README.md に関わる変更をしたら README も更新する。
