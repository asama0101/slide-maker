"""final.html を Playwright(Python) で開き、部品の位置・大きさ・書式をモデルにする。"""

from contextlib import contextmanager
from pathlib import Path

RASTER_SCALE = 3  # 絵（pp-picture）を画像にするときの倍率（1280px の幅で 3840px）

# 絵を 1 枚ずつ撮るときの CSS。対象の絵以外（下地・ほかの部品）を隠し、背景を透明にして、
# 重なった部品が絵に写り込まないようにする
_SNAP_CSS = """
html.pp-snap, html.pp-snap body, html.pp-snap section.slide { background: transparent !important; \
background-image: none !important; }
html.pp-snap section.slide * { visibility: hidden !important; }
html.pp-snap section.slide [data-snap], html.pp-snap section.slide [data-snap] * { visibility: visible !important; }
"""


def _rasterize(page, slides: list[dict], out_dir: Path) -> None:
    """model の kind=picture の要素ごとに、その絵だけを透過の PNG にして `src` に入れる。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    page.add_style_tag(content=_SNAP_CSS)
    slide_els = page.query_selector_all("section.slide")
    for s, slide_el in zip(slides, slide_els, strict=False):
        pics = [e for e in s["elements"] if e["kind"] == "picture"]
        if not pics:
            continue
        handles = slide_el.query_selector_all(".pp-picture")
        for n, (e, h) in enumerate(zip(pics, handles, strict=False), start=1):
            path = out_dir / f"picture-{s['index']:02d}-{n:02d}.png"
            page.evaluate("document.documentElement.classList.add('pp-snap')")
            h.evaluate("el => el.setAttribute('data-snap', '')")
            try:
                h.screenshot(path=str(path), omit_background=True)
            finally:
                h.evaluate("el => el.removeAttribute('data-snap')")
                page.evaluate("document.documentElement.classList.remove('pp-snap')")
            e["src"] = str(path)


@contextmanager
def open_browser(browser=None):
    """Chromium を 1 つ開く。browser を渡すとそれをそのまま使う（build が測定と確認用の画像で共有する）。"""
    if browser is not None:
        yield browser
        return
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


def measure(html: Path, raster_dir: Path | None = None, browser=None) -> list[dict]:
    """raster_dir を渡すと、絵（pp-picture）を PNG にして raster_dir に置き、モデルの `src` に入れる（build 用）。"""
    js = (Path(__file__).parent / "measure.js").read_text(encoding="utf-8")
    html = Path(html).resolve()
    with open_browser(browser) as b:
        page = b.new_page(
            viewport={"width": 1280, "height": 720}, device_scale_factor=RASTER_SCALE if raster_dir else 1
        )
        try:
            page.goto(html.as_uri())
            page.evaluate("document.fonts.ready.then(() => true)")
            slides = page.evaluate(js)
            if raster_dir and slides:
                _rasterize(page, slides, raster_dir)
        finally:
            page.close()
    if not slides:
        raise ValueError(f"{html.name} に section.slide がありません")
    return slides
