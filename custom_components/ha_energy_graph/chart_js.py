"""JavaScript du graphique interactif (généré depuis chart.js)."""

CHART_JS = r'''(function () {
  'use strict';
  var root = document.getElementById('area-root');
  if (!root || typeof D === 'undefined') { return; }
  var NS = 'http://www.w3.org/2000/svg';

  function lsGet(k, d) { try { var v = localStorage.getItem('heg_' + k); return v === null ? d : v; } catch (e) { return d; } }
  function lsSet(k, v) { try { localStorage.setItem('heg_' + k, v); } catch (e) { /* ignore */ } }
  function mk(tag, cls, text, parent) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text) { e.textContent = text; }
    if (parent) { parent.appendChild(e); }
    return e;
  }
  function sk(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) { if (Object.prototype.hasOwnProperty.call(attrs, k)) { e.setAttribute(k, attrs[k]); } }
    if (parent) { parent.appendChild(e); }
    return e;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function hm(t) { var h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60); return pad(h % 24) + ':' + pad(m); }
  function f1(x) { return x.toFixed(1); }

  var LAY = D.layers;
  var minRes = Math.max(1, Math.round(D.bucket_s / 60));
  var RES = [5, 10, 15, 30, 60].filter(function (r) { return r >= minRes; });
  var SMOOTH = [[0, 'Aucun'], [10, 'Léger'], [20, 'Moyen'], [40, 'Fort']];
  var S = {
    res: parseInt(lsGet('res', '5'), 10),
    scale: lsGet('scale2', 'lin'),
    group: lsGet('grp', '0') === '1',
    sm: parseInt(lsGet('sm', '10'), 10),
    t0: 0, t1: D.day_seconds, hidden: {}
  };
  if (RES.indexOf(S.res) < 0) { S.res = RES[0]; }
  if (S.scale !== 'lin' && S.scale !== 'sqrt') { S.scale = 'lin'; }
  if ([0, 10, 20, 40].indexOf(S.sm) < 0) { S.sm = 10; }
  window.__zoomed = false;

  // ---------- structure ----------
  var box = mk('div', 'ac', null, root);
  mk('h3', null, D.title, box);
  var ctl = mk('div', 'ctl', null, box);

  mk('span', null, 'Résolution', ctl);
  var selRes = mk('select', null, null, ctl);
  RES.forEach(function (r) { mk('option', null, r === 60 ? '1 h' : r + ' min', selRes).value = String(r); });
  selRes.value = String(S.res);
  selRes.onchange = function () { S.res = parseInt(selRes.value, 10); lsSet('res', S.res); draw(); };

  mk('span', null, 'Lissage', ctl);
  var selSm = mk('select', null, null, ctl);
  SMOOTH.forEach(function (o) { mk('option', null, o[1], selSm).value = String(o[0]); });
  selSm.value = String(S.sm);
  selSm.onchange = function () { S.sm = parseInt(selSm.value, 10); lsSet('sm', S.sm); draw(); };

  var bLin = mk('button', null, 'Linéaire', ctl);
  var bSqrt = mk('button', null, 'Compressée (√)', ctl);
  bSqrt.title = 'Échelle en racine carrée : les petites consommations deviennent lisibles face aux pics (les épaisseurs ne sont plus proportionnelles)';
  function setScale(s) { S.scale = s; lsSet('scale2', s); draw(); }
  bLin.onclick = function () { setScale('lin'); };
  bSqrt.onclick = function () { setScale('sqrt'); };
  var bGrp = mk('button', null, 'Par catégorie', ctl);
  bGrp.title = 'Regrouper les appareils par catégorie : moins de couches, donc plus lisible';
  bGrp.onclick = function () {
    S.group = !S.group; lsSet('grp', S.group ? '1' : '0');
    LAY = layersFor(S.group); buildLegend(); draw();
  };

  var bLeft = mk('button', null, '←', ctl);
  var bOut = mk('button', null, '−', ctl);
  var bIn = mk('button', null, '+', ctl);
  var bRight = mk('button', null, '→', ctl);
  var bReset = mk('button', null, 'Tout afficher', ctl);
  bLeft.title = 'Décaler vers le début de la journée';
  bRight.title = 'Décaler vers la fin de la journée';
  bOut.title = 'Dézoomer'; bIn.title = 'Zoomer';

  var leg = mk('div', 'leg', null, box);
  var wrap = mk('div', 'wrap', null, box);
  var sv = sk('svg', {}, wrap);
  var tip = mk('div', 'tip', null, wrap);
  mk('div', 'hint', 'Glissez sur le graphique pour zoomer · double-clic : tout afficher · Ctrl + molette : zoom · cliquez sur la légende pour masquer un appareil', box);

  function layersFor(group) {
    if (!group) { return D.layers; }
    var order = [], map = {};
    D.layers.forEach(function (L) {
      var key = L.cat || '_';
      if (!map[key]) {
        var c = (D.cats && D.cats[key]) || [L.name, L.color];
        map[key] = { name: c[0], color: c[1], cat: key, w: [] };
        for (var i = 0; i < D.n; i++) { map[key].w.push(0); }
        order.push(key);
      }
      for (var k = 0; k < D.n; k++) { map[key].w[k] += L.w[k]; }
    });
    return order.map(function (k) { return map[k]; });
  }
  function buildLegend() {
    leg.innerHTML = '';
    S.hidden = {};
    LAY.forEach(function (L, i) {
      var s = mk('span', null, null, leg);
      mk('i', null, null, s).style.background = L.color;
      mk('b', null, L.name, s).style.fontWeight = 'normal';
      s.onclick = function () {
        if (S.hidden[i]) { delete S.hidden[i]; s.className = ''; } else { S.hidden[i] = true; s.className = 'off'; }
        draw();
      };
    });
  }
  LAY = layersFor(S.group);
  buildLegend();

  // ---------- maths ----------
  function niceScale(m) {
    if (m <= 0) { return { top: 100, step: 20 }; }
    var e = Math.pow(10, Math.floor(Math.log10(m)));
    var ms = [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10];
    for (var i = 0; i < ms.length; i++) {
      var s = ms[i] * e;
      if (m / s <= 6) { return { top: Math.ceil(m / s - 1e-9) * s, step: s }; }
    }
    return { top: 10 * e, step: 2 * e };
  }

  // moyenne glissante triangulaire (conserve l'énergie, bords renormalisés)
  function smoothArr(a, hw) {
    if (hw <= 0 || a.length < 2) { return a.slice(); }
    var out = [], n = a.length, i, k;
    for (i = 0; i < n; i++) {
      var num = 0, den = 0;
      for (k = -hw; k <= hw; k++) {
        var j = i + k;
        if (j >= 0 && j < n) { var w = hw + 1 - Math.abs(k); num += w * a[j]; den += w; }
      }
      out.push(num / den);
    }
    return out;
  }

  // interpolation cubique monotone (Fritsch-Carlson), échantillonnée : jamais de dépassement
  function monoSamples(xs, ys, sub) {
    var n = xs.length, ox = [], oy = [], d = [], m = [], i, j;
    if (n < 2) { return { x: xs.slice(), y: ys.slice() }; }
    for (i = 0; i < n - 1; i++) { var dx = xs[i + 1] - xs[i]; d.push(dx === 0 ? 0 : (ys[i + 1] - ys[i]) / dx); }
    m[0] = d[0]; m[n - 1] = d[n - 2];
    for (i = 1; i < n - 1; i++) { m[i] = (d[i - 1] * d[i] <= 0) ? 0 : (d[i - 1] + d[i]) / 2; }
    for (i = 0; i < n - 1; i++) {
      if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
      var a = m[i] / d[i], b = m[i + 1] / d[i], s = a * a + b * b;
      if (s > 9) { var q = 3 / Math.sqrt(s); m[i] = q * a * d[i]; m[i + 1] = q * b * d[i]; }
    }
    for (i = 0; i < n - 1; i++) {
      var h = xs[i + 1] - xs[i];
      for (j = 0; j < sub; j++) {
        var t = j / sub, t2 = t * t, t3 = t2 * t;
        var y = (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i] +
                (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1];
        ox.push(xs[i] + t * h); oy.push(Math.max(0, y));
      }
    }
    ox.push(xs[n - 1]); oy.push(ys[n - 1]);
    return { x: ox, y: oy };
  }

  function groups() {
    var k = Math.max(1, Math.round(S.res * 60 / D.bucket_s)), out = [];
    for (var g = 0; g < D.n; g += k) {
      var e = Math.min(g + k, D.n), c = e - g, v = [];
      for (var li = 0; li < LAY.length; li++) {
        var w = LAY[li].w, s = 0;
        for (var i = g; i < e; i++) { s += w[i]; }
        v.push(s / c);
      }
      out.push({ t0: g * D.bucket_s, t1: e * D.bucket_s, tc: (g + e) / 2 * D.bucket_s, v: v, s: [] });
    }
    return out;
  }

  // ---------- zoom ----------
  function clampRange(a, b) {
    var span = b - a;
    if (span > D.day_seconds) { span = D.day_seconds; }
    if (span < 1800) { span = 1800; }
    if (a < 0) { a = 0; }
    b = a + span;
    if (b > D.day_seconds) { b = D.day_seconds; a = b - span; }
    return [Math.max(0, a), b];
  }
  function zoomTo(a, b) {
    var r = clampRange(a, b);
    S.t0 = r[0]; S.t1 = r[1];
    window.__zoomed = (S.t0 > 0 || S.t1 < D.day_seconds);
    draw();
  }
  bIn.onclick = function () { var c = (S.t0 + S.t1) / 2, h = (S.t1 - S.t0) / 4; zoomTo(c - h, c + h); };
  bOut.onclick = function () { var c = (S.t0 + S.t1) / 2, h = (S.t1 - S.t0); zoomTo(c - h, c + h); };
  bLeft.onclick = function () { var q = (S.t1 - S.t0) / 4; zoomTo(S.t0 - q, S.t1 - q); };
  bRight.onclick = function () { var q = (S.t1 - S.t0) / 4; zoomTo(S.t0 + q, S.t1 + q); };
  bReset.onclick = function () { zoomTo(0, D.day_seconds); };

  // ---------- dessin ----------
  function draw() {
    bLin.className = S.scale === 'lin' ? 'on' : '';
    bSqrt.className = S.scale === 'sqrt' ? 'on' : '';
    bGrp.className = S.group ? 'on' : '';
    var W = Math.max(320, Math.floor(wrap.clientWidth)), H = W < 560 ? 340 : 440;
    var ml = 58, mr = 14, mt = 10, mb = 30, pw = W - ml - mr, ph = H - mt - mb;
    sv.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    sv.setAttribute('width', W); sv.setAttribute('height', H);
    while (sv.firstChild) { sv.removeChild(sv.firstChild); }
    tip.style.display = 'none';

    var G = groups(), vis = [], i, j;
    LAY.forEach(function (L, li) { if (!S.hidden[li]) { vis.push(li); } });
    var hw = S.sm > 0 ? Math.max(1, Math.round(S.sm / S.res)) : 0;
    vis.forEach(function (li) {
      var sm = smoothArr(G.map(function (g) { return g.v[li]; }), hw);
      G.forEach(function (g, gi) { g.s[li] = sm[gi]; });
    });

    var span = S.t1 - S.t0;
    var lo = 0, hi = G.length - 1;
    for (i = 0; i < G.length; i++) { if (G[i].t1 > S.t0) { lo = Math.max(0, i - 1); break; } }
    for (i = G.length - 1; i >= 0; i--) { if (G[i].t0 < S.t1) { hi = Math.min(G.length - 1, i + 1); break; } }
    var sl = G.slice(lo, hi + 1);
    var sub = Math.max(1, Math.min(24, Math.ceil(pw / Math.max(1, span / (S.res * 60)) / 4)));
    var smp = [], sx = [];
    if (sl.length) {
      var xsl = sl.map(function (g) { return g.tc; });
      if (sl.length === 1) { xsl = [sl[0].t0, sl[0].t1]; }
      smp = vis.map(function (li) {
        var ys = sl.map(function (g) { return g.s[li]; });
        if (sl.length === 1) { ys = [ys[0], ys[0]]; }
        return monoSamples(xsl, ys, sub);
      });
      sx = smp.length ? smp[0].x : xsl;
    }
    var cum = [], z = [];
    for (j = 0; j < sx.length; j++) { z.push(0); }
    cum.push(z);
    smp.forEach(function (s, k) {
      var c = [];
      for (var q = 0; q < sx.length; q++) { c.push(cum[k][q] + s.y[q]); }
      cum.push(c);
    });
    var ymax = 0, topc = cum[cum.length - 1];
    for (j = 0; j < sx.length; j++) { if (sx[j] >= S.t0 && sx[j] <= S.t1) { ymax = Math.max(ymax, topc[j]); } }
    var sc = niceScale(ymax * 1.03), top = sc.top;
    function X(t) { return ml + (t - S.t0) / span * pw; }
    function F(v) { v = Math.max(v, 0) / top; return S.scale === 'sqrt' ? Math.sqrt(v) : v; }
    function Y(v) { return mt + ph - F(v) * ph; }

    // axe Y
    var ticks = [], v;
    if (S.scale === 'lin') {
      for (v = 0; v <= top + 1e-9; v += sc.step) { ticks.push(v); }
    } else {
      var cand = [0], e;
      for (e = 1; e <= top; e *= 10) { [1, 2, 5].forEach(function (mm) { if (mm * e <= top) { cand.push(mm * e); } }); }
      var lastY = 1e9;
      cand.forEach(function (c) { var y = Y(c); if (lastY - y >= 22 || c === 0) { ticks.push(c); lastY = y; } });
    }
    ticks.forEach(function (tv) {
      var y = Y(tv);
      sk('line', { x1: ml, x2: ml + pw, y1: y, y2: y, 'class': 'gl' }, sv);
      sk('text', { x: ml - 8, y: y + 4, 'text-anchor': 'end', 'class': 'ax' }, sv).textContent = (Math.round(tv * 10) / 10) + ' W';
    });

    // axe X
    var steps = [600, 900, 1800, 3600, 7200, 10800, 21600], xs = 21600;
    for (i = 0; i < steps.length; i++) { if (span / steps[i] <= 10) { xs = steps[i]; break; } }
    for (var t = Math.ceil(S.t0 / xs) * xs; t <= S.t1 + 1e-6; t += xs) {
      var x = X(t);
      sk('line', { x1: x, x2: x, y1: mt + ph, y2: mt + ph + 4, 'class': 'gl' }, sv);
      sk('text', { x: x, y: mt + ph + 18, 'text-anchor': 'middle', 'class': 'ax' }, sv).textContent =
        xs >= 3600 ? (Math.round(t / 3600)) + ' h' : hm(t);
    }

    // couches (clippées à la zone de tracé)
    var defs = sk('defs', {}, sv);
    sk('rect', { x: ml, y: mt, width: pw, height: ph }, sk('clipPath', { id: 'heg-clip' }, defs));
    var gl = sk('g', { 'clip-path': 'url(#heg-clip)' }, sv);
    if (!G.length) {
      sk('text', { x: ml + pw / 2, y: mt + ph / 2, 'text-anchor': 'middle', 'class': 'ax' }, sv).textContent = 'Pas encore de données';
    }
    vis.forEach(function (li, k) {
      var yv = smp[k].y, mx = 0;
      for (j = 0; j < yv.length; j++) { mx = Math.max(mx, yv[j]); }
      if (mx < 0.05) { return; }
      var up = [], dn = [];
      for (j = 0; j < sx.length; j++) { up.push(f1(X(sx[j])) + ',' + f1(Y(cum[k + 1][j]))); }
      for (j = sx.length - 1; j >= 0; j--) { dn.push(f1(X(sx[j])) + ',' + f1(Y(cum[k][j]))); }
      var p = sk('path', {
        d: 'M' + up.join('L') + 'L' + dn.join('L') + 'Z',
        fill: LAY[li].color, 'fill-opacity': '0.93', stroke: 'var(--c-bg)', 'stroke-width': '0.6'
      }, gl);
      sk('title', {}, p).textContent = LAY[li].name;
    });

    // interaction
    var cross = sk('line', { y1: mt, y2: mt + ph, 'class': 'gl', 'stroke-width': '1.5', visibility: 'hidden' }, sv);
    cross.setAttribute('stroke', 'var(--c-text)');
    var ov = sk('rect', { x: ml, y: mt, width: pw, height: ph, fill: 'transparent', style: 'touch-action:pan-y;cursor:crosshair' }, sv);
    var selr = sk('rect', { y: mt, height: ph, 'class': 'sel', visibility: 'hidden' }, sv);
    var drag = null;

    function px(ev) { var r = sv.getBoundingClientRect(); return (ev.clientX - r.left) * (W / r.width); }
    function tOf(p) { return S.t0 + (p - ml) / pw * span; }

    function showTip(ev) {
      var tt = tOf(px(ev)), g = null;
      for (var q = 0; q < G.length; q++) { if (tt >= G[q].t0 && tt < G[q].t1) { g = G[q]; break; } }
      if (!g) { tip.style.display = 'none'; cross.setAttribute('visibility', 'hidden'); return; }
      var cx = X(g.tc);
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('visibility', 'visible');
      tip.innerHTML = '';
      mk('div', null, hm(g.t0) + ' – ' + hm(g.t1), tip).style.fontWeight = 'bold';
      var rows = [], tot = 0;
      vis.forEach(function (li) { tot += g.s[li]; if (g.s[li] >= 0.5) { rows.push([li, g.s[li]]); } });
      rows.sort(function (a, b) { return b[1] - a[1]; });
      rows.forEach(function (r) {
        var line = mk('div', null, null, tip), nm = mk('span', null, null, line), sw = mk('i', null, null, nm);
        sw.style.cssText = 'display:inline-block;width:10px;height:10px;margin-right:6px;border-radius:2px;background:' + LAY[r[0]].color;
        nm.appendChild(document.createTextNode(LAY[r[0]].name));
        mk('span', null, Math.round(r[1]) + ' W', line);
      });
      var last = mk('div', null, null, tip);
      last.style.cssText = 'border-top:1px solid var(--c-grid);margin-top:4px;padding-top:4px;font-weight:bold';
      mk('span', null, 'Total', last); mk('span', null, Math.round(tot) + ' W', last);
      tip.style.display = 'block';
      var r2 = sv.getBoundingClientRect(), xpx = cx * (r2.width / W), left = xpx + 14;
      if (left + tip.offsetWidth > wrap.clientWidth) { left = xpx - tip.offsetWidth - 14; }
      tip.style.left = Math.max(0, left) + 'px';
    }

    ov.addEventListener('pointerdown', function (ev) {
      if (ev.pointerType === 'mouse' && ev.button !== 0) { return; }
      drag = { x0: px(ev) };
      try { ov.setPointerCapture(ev.pointerId); } catch (err) { /* ignore */ }
    });
    ov.addEventListener('pointermove', function (ev) {
      if (drag) {
        var p = px(ev), a = Math.max(ml, Math.min(p, drag.x0)), b = Math.min(ml + pw, Math.max(p, drag.x0));
        selr.setAttribute('x', a); selr.setAttribute('width', Math.max(0, b - a)); selr.setAttribute('visibility', 'visible');
        tip.style.display = 'none';
      } else { showTip(ev); }
    });
    ov.addEventListener('pointerup', function (ev) {
      if (!drag) { return; }
      var p = px(ev), x0 = drag.x0; drag = null;
      selr.setAttribute('visibility', 'hidden');
      if (Math.abs(p - x0) > 8) { zoomTo(tOf(Math.min(p, x0)), tOf(Math.max(p, x0))); }
    });
    ov.addEventListener('pointerleave', function () { if (!drag) { tip.style.display = 'none'; cross.setAttribute('visibility', 'hidden'); } });
    ov.addEventListener('dblclick', function () { zoomTo(0, D.day_seconds); });
    ov.addEventListener('wheel', function (ev) {
      if (!(ev.ctrlKey || ev.metaKey)) { return; }
      ev.preventDefault();
      var tt = tOf(px(ev)), f = ev.deltaY < 0 ? 0.8 : 1.25;
      zoomTo(tt - (tt - S.t0) * f, tt + (S.t1 - tt) * f);
    }, { passive: false });
  }

  var rt = null;
  window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(draw, 150); });
  draw();
})();
'''
