# ruff: noqa: S101  # pytest の assert

from pptx_deck import initdir, paths


def test_作業フォルダの親は出力先で_成果物名がフォルダ名になる(deck_base):
    work = paths.resolve_work(deck_base)
    assert work == deck_base.resolve()
    assert paths.deck_dir(work) == deck_base.parent.parent.resolve()
    assert paths.deck_name(work) == "deck"


def test_init_は渡した作業フォルダの直下に成果物を作り_source_を作らない(deck_base):
    r = initdir.init(deck_base)
    assert (deck_base / "template.json").is_file()
    assert not (deck_base / "source").exists()
    assert r["workdir"] == str(deck_base.resolve())
