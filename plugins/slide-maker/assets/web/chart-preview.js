/* グラフのブラウザ用プレビュー（近似）。実際のグラフは PowerPoint のネイティブグラフで出る。 */
(function () {
  var NS = 'http://www.w3.org/2000/svg';
  var ctx = document.documentElement;      // 色の変数を読む要素（描画するグラフ自身。親のクラスで配色を変えても追従する）
  var css = function (n) { return getComputedStyle(ctx).getPropertyValue(n).trim() || '#333'; };
  var el = function (t, a, p) {
    var e = document.createElementNS(NS, t);
    for (var k in a) e.setAttribute(k, a[k]);
    if (p) p.appendChild(e);
    return e;
  };
  // 文字の倍率（--chart-scale）。縮小（1 未満）のときだけ 10pt（約 13.3px）を下限にする
  var fs = function (size) {
    var sc = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--chart-scale')) || 1;
    var v = Math.round(size * sc);
    return sc < 1 ? Math.max(10 * 96 / 72, v) : v;
  };
  var txt = function (p, x, y, s, o) {
    o = o || {};
    var t = el('text', { x: x, y: y, 'font-size': fs(o.size || 14), 'text-anchor': o.anchor || 'middle',
      fill: o.fill || css('--text'), 'font-weight': o.bold ? 700 : 400 }, p);
    t.textContent = s;
    return t;
  };
  var nice = function (v) {
    if (v <= 0) return 1;
    var p = Math.pow(10, Math.floor(Math.log10(v))), m = v / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
  };
  // PowerPoint の自動目盛りに近い上限（目盛り幅は 1・2・5 × 10^n で、区間は 8 以下。データ最大に 5% の余白を足して切り上げる）
  var niceMax = function (v) {
    if (v <= 0) return 1;
    var p = Math.pow(10, Math.floor(Math.log10(v))), step = p;
    [0.1, 0.2, 0.5, 1, 2, 5, 10].some(function (m) { step = m * p; return v / step <= 8; });
    return Math.ceil(v * 1.05 / step) * step;
  };
  var fmt = function (v) { return (Math.round(v * 10) / 10).toLocaleString('en-US', { maximumFractionDigits: 1 }); };    // 桁区切りは、PowerPoint の既定の書式（#,##0）に合わせる
  // 横幅 maxW（px）に収まるよう、軸ラベルを最大 2 行に折り返す。空白があればそこで折り、2 行を超える分だけ「…」で省く
  var wrap = function (s, maxW) {
    var cw = function (c) { return c.charCodeAt(0) > 255 ? 13 : 7; };      // 13px の全角・半角の概算幅
    var width = function (t) { return t.split('').reduce(function (a, c) { return a + cw(c); }, 0); };
    var lines = [], cur = '';
    s.split('').forEach(function (c) {
      cur += c;
      if (width(cur) <= maxW) return;
      var sp = cur.lastIndexOf(' ');
      if (sp > 0) { lines.push(cur.slice(0, sp)); cur = cur.slice(sp + 1); }
      else { lines.push(cur.slice(0, -1)); cur = c; }
    });
    lines.push(cur);
    return lines.length > 2 ? [lines[0], lines[1].slice(0, -1) + '…'] : lines;
  };
  var palette = function () {
    return [css('--accent'), css('--accent-mid'), '#8C8C8C', css('--accent-dark'), '#BFBFBF'];
  };

  function stacks(spec) {
    var n = spec.categories.length, S = spec.series;
    if (spec.type === 'waterfall') {
      var vals = S[0].values, tot = {}, run = 0;
      (spec.totals || [0, n - 1]).forEach(function (i) { tot[i] = 1; });
      var hl = {};
      [].concat(spec.highlight == null ? [] : spec.highlight).forEach(function (i) { hl[i] = 1; });
      // 色は PowerPoint のグラフと同じ（増加＝淡い灰、減少＝濃い灰、合計＝中間の灰。注目する項目だけ強調色）
      var pick = function (i, c) { return hl[i] ? css('--emphasis') : c; };
      return vals.map(function (v, i) {
        if (tot[i]) { run = v; return [{ lo: 0, hi: v, v: v, color: pick(i, '#767676') }]; }
        if (v >= 0) { var a = [{ lo: run, hi: run + v, v: v, color: pick(i, '#BFBFBF') }]; run += v; return a; }
        var b = [{ lo: run + v, hi: run, v: -v, color: pick(i, '#404040') }]; run += v; return b;
      });
    }
    var pal = palette(), stacked = spec.type.indexOf('stacked') === 0;
    return spec.categories.map(function (_, i) {
      if (!stacked) return S.map(function (s, j) {
        var hl = j === 0 && spec.highlight === i;
        return { lo: 0, hi: s.values[i], v: s.values[i], j: j, n: S.length, color: hl ? css('--emphasis') : pal[j % 5] };
      });
      var acc = 0, d = 1;
      return S.map(function (s, j) {
        var v = s.values[i] / d, r = { lo: acc, hi: acc + v, v: s.values[i], color: pal[j % 5] };
        acc += v; return r;
      });
    });
  }

  function legend(svg, spec, W, H) {
    if (spec.series.length < 2 || spec.type === 'waterfall') return;
    var pal = palette(), x = 56;
    spec.series.forEach(function (s, j) {
      el('rect', { x: x, y: H - 18, width: 12, height: 12, fill: pal[j % 5] }, svg);
      txt(svg, x + 18, H - 7, s.name, { anchor: 'start', size: 13 });
      x += 30 + s.name.length * 14;
    });
  }

  function columns(svg, spec, W, H, horizontal) {
    var L = 56, R = 16, T = 24, B = spec.series.length > 1 && spec.type !== 'waterfall' ? 56 : 40;
    var pw = W - L - R, ph = H - T - B, st = stacks(spec);
    var lo = 0, hi = 0;
    st.forEach(function (c) { c.forEach(function (b) { lo = Math.min(lo, b.lo, b.hi); hi = Math.max(hi, b.lo, b.hi); }); });
    hi = niceMax(hi);
    var ax = spec.axis || {};                  // 軸の固定（小グラフを並べるときに全パネルで揃える）
    if (ax.min !== undefined) lo = ax.min;
    if (ax.max !== undefined) hi = ax.max;
    var range = hi - lo || 1, n = st.length, slot = (horizontal ? ph : pw) / n;
    var pos = function (v) { return (v - lo) / range * (horizontal ? pw : ph); };
    el('line', horizontal ? { x1: L + pos(0), y1: T, x2: L + pos(0), y2: T + ph, stroke: '#BFBFBF' }
      : { x1: L, y1: T + ph - pos(0), x2: L + pw, y2: T + ph - pos(0), stroke: '#BFBFBF' }, svg);
    st.forEach(function (c, i) {
      c.forEach(function (b) {
        var k = b.n || 1, w = slot * 0.62 / k, off = slot * 0.19 + (b.j || 0) * w;
        var a = pos(Math.min(b.lo, b.hi)), len = Math.abs(pos(b.hi) - pos(b.lo));
        if (horizontal) el('rect', { x: L + a, y: T + i * slot + off, width: len, height: w, fill: b.color }, svg);
        else el('rect', { x: L + i * slot + off, y: T + ph - a - len, width: w, height: len, fill: b.color }, svg);
        if (horizontal) txt(svg, L + a + len + 6, T + i * slot + off + w / 2 + 5, fmt(b.v), { anchor: 'start', size: 13 });
        else txt(svg, L + i * slot + off + w / 2, T + ph - a - len - 6, fmt(b.v), { size: 13 });
      });
      var label = spec.categories[i];
      if (horizontal) txt(svg, L - 8, T + i * slot + slot / 2 + 5, label, { anchor: 'end', size: 13 });
      else wrap(label, slot - 8).forEach(function (s, k) { txt(svg, L + i * slot + slot / 2, T + ph + 20 + k * 14, s, { size: 13 }); });
    });
    legend(svg, spec, W, H);
  }

  function line(svg, spec, W, H) {
    var L = 56, R = 16, T = 24, B = spec.series.length > 1 ? 56 : 40, pw = W - L - R, ph = H - T - B, pal = palette();
    var all = [].concat.apply([], spec.series.map(function (s) { return s.values; }));
    var ax = spec.axis || {};
    var lo = ax.min !== undefined ? ax.min : Math.min(0, Math.min.apply(null, all));
    var hi = ax.max !== undefined ? ax.max : niceMax(Math.max.apply(null, all)), range = hi - lo || 1;
    var n = spec.categories.length, step = pw / n;
    spec.series.forEach(function (s, j) {
      var pts = s.values.map(function (v, i) { return (L + (i + 0.5) * step) + ',' + (T + ph - (v - lo) / range * ph); });
      el('polyline', { points: pts.join(' '), fill: 'none', stroke: pal[j % 5], 'stroke-width': 3 }, svg);
      s.values.forEach(function (v, i) { el('circle', { cx: L + (i + 0.5) * step, cy: T + ph - (v - lo) / range * ph, r: 4, fill: pal[j % 5] }, svg); });
    });
    spec.categories.forEach(function (c, i) { txt(svg, L + (i + 0.5) * step, T + ph + 20, c, { size: 13 }); });
    legend(svg, spec, W, H);
  }

  function pie(svg, spec, W, H) {
    var cx = W / 2, cy = H / 2 - 10, r = Math.min(W, H) / 2 - 40, v = spec.series[0].values;
    var sum = v.reduce(function (a, b) { return a + b; }, 0) || 1, a0 = -Math.PI / 2, pal = palette();
    v.forEach(function (x, i) {
      var a1 = a0 + x / sum * Math.PI * 2, large = a1 - a0 > Math.PI ? 1 : 0;
      var d = 'M' + cx + ',' + cy + ' L' + (cx + r * Math.cos(a0)) + ',' + (cy + r * Math.sin(a0)) +
        ' A' + r + ',' + r + ' 0 ' + large + ' 1 ' + (cx + r * Math.cos(a1)) + ',' + (cy + r * Math.sin(a1)) + ' Z';
      el('path', { d: d, fill: spec.highlight === i ? css('--emphasis') : pal[i % 5], stroke: '#fff', 'stroke-width': 2 }, svg);
      var am = (a0 + a1) / 2;
      txt(svg, cx + r * 0.62 * Math.cos(am), cy + r * 0.62 * Math.sin(am) + 5, fmt(x), { size: 14, fill: '#fff', bold: true });
      a0 = a1;
    });
    var x = 40;
    spec.categories.forEach(function (c, i) {
      el('rect', { x: x, y: H - 18, width: 12, height: 12, fill: pal[i % 5] }, svg);
      txt(svg, x + 18, H - 7, c, { anchor: 'start', size: 13 });
      x += 30 + c.length * 14;
    });
  }

  function draw(host) {
    var spec = JSON.parse(host.dataset.chart);
    ctx = host;
    host.querySelectorAll('svg').forEach(function (s) { s.remove(); });
    var W = host.clientWidth || 600, H = host.clientHeight || 360;
    var svg = el('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, style: 'position:absolute;left:0;top:0' }, host);
    svg.setAttribute('font-family', "'BIZ UDPGothic','Yu Gothic','Meiryo',sans-serif");
    if (spec.type === 'line') line(svg, spec, W, H);
    else if (spec.type === 'pie') pie(svg, spec, W, H);
    else columns(svg, spec, W, H, spec.type === 'barh');
  }

  // 矢印の向きと色（矢じりの CSS 用）。スライドを後から差し込んだときは window.__arrows(root) を呼ぶ
  function arrows(root) {
    (root || document).querySelectorAll('.pp-line[data-arrow]').forEach(function (l) {
      var horizontal = l.offsetWidth >= l.offsetHeight;
      l.classList.add(horizontal ? 'ah' : 'av');
      if (l.dataset.dir === 'rev') l.classList.add('rv');
      l.style.setProperty('--ac', getComputedStyle(l).backgroundColor);
    });
  }
  window.__arrows = arrows;
  window.__chartPreview = draw;
  var run = function () { document.querySelectorAll('.pp-chart').forEach(draw); arrows(document); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
