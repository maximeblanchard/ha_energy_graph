/**
 * Carte Lovelace native pour Home Assistant : Graphique d'énergie (ha_energy_graph)
 * Camembert et Aires empilées interactifs (zoom, lissage, échelle racine carrée, infobulles).
 */
(function () {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';

  function mk(tag, cls, text, parent) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }

  function sk(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    if (attrs) {
      for (const k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k)) {
          e.setAttribute(k, attrs[k]);
        }
      }
    }
    if (parent) parent.appendChild(e);
    return e;
  }

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function hm(t) {
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60);
    return pad(h % 24) + ':' + pad(m);
  }
  function f1(x) { return x.toFixed(1); }

  class HaEnergyGraphCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._config = {};
      this._view = 'both'; // 'both', 'area', 'pie'
      this._selectedDate = null;
      this._data = null;
      this._hass = null;
      this._loading = false;
      this._isZoomed = false;
      this._refreshTimer = null;

      // État du graphique en aires
      this._S = {
        res: 5,
        scale: 'lin',
        group: false,
        sm: 10,
        t0: 0,
        t1: 86400,
        hidden: {},
      };
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._initialized) {
        this._initialized = true;
        this._loadData();
        this._startAutoRefresh();
      }
    }

    setConfig(config) {
      this._config = Object.assign(
        {
          view: 'both',
          title: null,
          entry_id: null,
        },
        config
      );
      this._view = this._config.view || 'both';
      if (this._initialized) {
        this._loadData();
      }
    }

    getCardSize() {
      return this._view === 'both' ? 9 : 5;
    }

    connectedCallback() {
      this._startAutoRefresh();
    }

    disconnectedCallback() {
      if (this._refreshTimer) {
        clearTimeout(this._refreshTimer);
        this._refreshTimer = null;
      }
    }

    _startAutoRefresh() {
      if (this._refreshTimer) clearTimeout(this._refreshTimer);
      const scheduleNext = () => {
        // Rafraîchit toutes les 5 min + 45s (après calcul des stats du recorder)
        const ms = 300000 - (Date.now() % 300000) + 45000;
        this._refreshTimer = setTimeout(() => {
          if (!this._isZoomed && (!this._selectedDate || (this._data && this._data.is_today))) {
            this._loadData(true);
          }
          scheduleNext();
        }, ms);
      };
      scheduleNext();
    }

    async _loadData(silent = false) {
      if (!this._hass) return;
      if (!silent) {
        this._loading = true;
        this._render();
      }
      try {
        const payload = {
          type: 'ha_energy_graph/data',
        };
        if (this._config.entry_id) {
          payload.entry_id = this._config.entry_id;
        }
        if (this._selectedDate) {
          payload.date = this._selectedDate;
        }
        const res = await this._hass.callWS(payload);
        this._data = res;
        if (!this._isZoomed && res.area && res.area.day_seconds) {
          this._S.t0 = 0;
          this._S.t1 = res.area.day_seconds;
        }
      } catch (err) {
        console.error('Erreur lors du chargement des données ha_energy_graph:', err);
      } finally {
        this._loading = false;
        this._render();
      }
    }

    _render() {
      const root = this.shadowRoot;
      root.innerHTML = '';

      const style = document.createElement('style');
      style.textContent = `
        :host {
          display: block;
        }
        ha-card {
          padding: 16px;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          color: var(--primary-text-color, #222);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, none);
          font-family: var(--paper-font-body1_-_font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif);
          overflow: hidden;
        }
        .header-bar {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          margin-bottom: 12px;
        }
        .card-title {
          font-size: 1.25rem;
          font-weight: 500;
          color: var(--primary-text-color);
          margin: 0;
        }
        .tabs {
          display: inline-flex;
          background: var(--secondary-background-color, rgba(127,127,127,0.1));
          border-radius: 8px;
          padding: 2px;
        }
        .tab-btn {
          border: none;
          background: transparent;
          color: var(--secondary-text-color);
          padding: 4px 10px;
          font-size: 0.85rem;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s;
        }
        .tab-btn.active {
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          font-weight: 500;
          box-shadow: 0 1px 3px rgba(0,0,0,0.15);
        }
        .nav-bar {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          align-items: center;
          justify-content: center;
          margin-bottom: 16px;
        }
        .nav-btn {
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, rgba(127,127,127,0.2));
          border-radius: 6px;
          padding: 4px 10px;
          cursor: pointer;
          font-size: 1rem;
        }
        .nav-btn:disabled {
          opacity: 0.35;
          cursor: not-allowed;
        }
        .date-input {
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, rgba(127,127,127,0.2));
          border-radius: 6px;
          padding: 4px 8px;
          font-size: 0.95rem;
          font-family: inherit;
        }
        .today-btn {
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #fff);
          border: none;
          border-radius: 6px;
          padding: 4px 10px;
          cursor: pointer;
          font-size: 0.85rem;
          font-weight: 500;
        }
        .pie-section {
          margin-bottom: 24px;
        }
        .pie-title {
          text-align: center;
          font-size: 1rem;
          font-weight: 500;
          margin-bottom: 8px;
        }
        .pie-legend {
          display: flex;
          flex-wrap: wrap;
          gap: 6px 14px;
          justify-content: center;
          margin-top: 10px;
          font-size: 0.85rem;
        }
        .pie-legend span {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .pie-legend i {
          width: 12px;
          height: 12px;
          border-radius: 2px;
        }
        .area-section {
          position: relative;
        }
        .area-title {
          text-align: center;
          font-size: 1rem;
          font-weight: 500;
          margin-bottom: 6px;
        }
        .ctl {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          align-items: center;
          justify-content: center;
          margin-bottom: 10px;
          font-size: 0.82rem;
        }
        .ctl button, .ctl select {
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, rgba(127,127,127,0.25));
          border-radius: 6px;
          padding: 3px 8px;
          font-size: 0.82rem;
          font-family: inherit;
          cursor: pointer;
        }
        .ctl button.on {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border-color: var(--primary-color, #03a9f4);
        }
        .leg {
          display: flex;
          flex-wrap: wrap;
          gap: 6px 12px;
          justify-content: center;
          margin: 6px 0;
          font-size: 0.82rem;
        }
        .leg span {
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 5px;
          user-select: none;
        }
        .leg i {
          width: 12px;
          height: 12px;
          border-radius: 2px;
        }
        .leg .off {
          opacity: 0.35;
          text-decoration: line-through;
        }
        .wrap {
          position: relative;
          width: 100%;
        }
        .tip {
          position: absolute;
          top: 10px;
          left: 0;
          pointer-events: none;
          display: none;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 6px;
          padding: 6px 8px;
          font-size: 0.8rem;
          box-shadow: 0 2px 8px rgba(0,0,0,0.25);
          z-index: 10;
          min-width: 150px;
        }
        .tip div {
          display: flex;
          justify-content: space-between;
          gap: 12px;
        }
        .hint {
          opacity: 0.6;
          font-size: 0.75rem;
          text-align: center;
          margin-top: 6px;
        }
        .ax {
          fill: var(--primary-text-color, #222);
          font-size: 11px;
        }
        .gl {
          stroke: var(--divider-color, rgba(127,127,127,0.2));
          stroke-width: 1;
        }
        .sel {
          fill: rgba(3, 169, 244, 0.25);
          stroke: rgba(3, 169, 244, 0.8);
        }
        .spinner {
          text-align: center;
          padding: 30px;
          color: var(--secondary-text-color);
        }
        .error-msg {
          color: var(--error-color, #f44336);
          text-align: center;
          font-size: 0.85rem;
          margin-top: 4px;
        }
      `;
      root.appendChild(style);

      const card = mk('ha-card', null, null, root);

      // Header Bar
      const header = mk('div', 'header-bar', null, card);
      const titleText = this._config.title || (this._data ? this._data.title : "Graphique d'énergie");
      mk('h2', 'card-title', titleText, header);

      // Sélecteur d'onglets (Tout, Aires, Camembert)
      const tabs = mk('div', 'tabs', null, header);
      const bBoth = mk('button', `tab-btn ${this._view === 'both' ? 'active' : ''}`, 'Tout', tabs);
      const bArea = mk('button', `tab-btn ${this._view === 'area' ? 'active' : ''}`, 'Aires', tabs);
      const bPie = mk('button', `tab-btn ${this._view === 'pie' ? 'active' : ''}`, 'Camembert', tabs);

      bBoth.onclick = () => { this._view = 'both'; this._render(); };
      bArea.onclick = () => { this._view = 'area'; this._render(); };
      bPie.onclick = () => { this._view = 'pie'; this._render(); };

      if (!this._data && this._loading) {
        mk('div', 'spinner', 'Chargement des données d’énergie...', card);
        return;
      }
      if (!this._data) {
        mk('div', 'spinner', 'Aucune donnée disponible.', card);
        return;
      }

      // Barre de navigation temporelle
      const nav = mk('div', 'nav-bar', null, card);
      const bPrev = mk('button', 'nav-btn', '◀', nav);
      bPrev.title = 'Jour précédent';
      bPrev.onclick = () => {
        const d = new Date(this._data.date);
        d.setDate(d.getDate() - 1);
        this._selectedDate = d.toISOString().split('T')[0];
        this._loadData();
      };

      const dateInp = mk('input', 'date-input', null, nav);
      dateInp.type = 'date';
      dateInp.value = this._data.date;
      dateInp.max = this._data.today;
      dateInp.onchange = () => {
        if (dateInp.value) {
          this._selectedDate = dateInp.value;
          this._loadData();
        }
      };

      const bNext = mk('button', 'nav-btn', '▶', nav);
      bNext.title = 'Jour suivant';
      bNext.disabled = this._data.date >= this._data.today;
      bNext.onclick = () => {
        const d = new Date(this._data.date);
        d.setDate(d.getDate() + 1);
        this._selectedDate = d.toISOString().split('T')[0];
        this._loadData();
      };

      if (!this._data.is_today) {
        const bToday = mk('button', 'today-btn', "Aujourd'hui", nav);
        bToday.onclick = () => {
          this._selectedDate = this._data.today;
          this._loadData();
        };
      }

      if (this._data.error) {
        mk(
          'div',
          'error-msg',
          '⚠️ La somme des appareils suivis dépasse le capteur total du logement.',
          card
        );
      }

      // 1. Vue Camembert
      if (this._view === 'both' || this._view === 'pie') {
        this._renderPie(card);
      }

      // 2. Vue Aires empilées
      if (this._view === 'both' || this._view === 'area') {
        this._renderArea(card);
      }
    }

    _renderPie(container) {
      const pieData = this._data.pie;
      if (!pieData || !pieData.slices) return;

      const sec = mk('div', 'pie-section', null, container);
      mk('div', 'pie-title', pieData.title, sec);

      const slices = pieData.slices;
      const total = pieData.total;
      const width = 600, height = 340;
      const radius = 120;
      const cx = width / 2, cy = height / 2 - 10;

      const sv = sk('svg', {
        viewBox: `0 0 ${width} ${height}`,
        style: 'width:100%;height:auto;max-height:300px;display:block;margin:0 auto;'
      }, sec);

      if (total <= 0) {
        sk('text', {
          x: cx, y: cy, 'text-anchor': 'middle', class: 'ax', 'font-size': '16'
        }, sv).textContent = 'Pas de données d’énergie';
        return;
      }

      let angle = -Math.PI / 2;
      slices.forEach((s) => {
        const frac = s.wh / total;
        const tip = `${s.name} : ${(s.wh / 1000).toFixed(2)} kWh (${s.percent} %)`;

        if (frac >= 0.999) {
          const c = sk('circle', {
            cx, cy, r: radius, fill: s.color, stroke: 'var(--card-background-color, #fff)', 'stroke-width': '1.5'
          }, sv);
          sk('title', {}, c).textContent = tip;
        } else {
          const a1 = angle + frac * 2 * Math.PI;
          const x0 = cx + radius * Math.cos(angle);
          const y0 = cy + radius * Math.sin(angle);
          const x1 = cx + radius * Math.cos(a1);
          const y1 = cy + radius * Math.sin(a1);
          const large = a1 - angle > Math.PI ? 1 : 0;
          const path = sk('path', {
            d: `M${cx},${cy} L${x0.toFixed(1)},${y0.toFixed(1)} A${radius},${radius} 0 ${large} 1 ${x1.toFixed(1)},${y1.toFixed(1)} Z`,
            fill: s.color,
            stroke: 'var(--card-background-color, #fff)',
            'stroke-width': '1.5',
            style: 'transition: opacity 0.15s; cursor: pointer;'
          }, sv);
          sk('title', {}, path).textContent = tip;
          path.onmouseenter = () => { path.style.opacity = '0.8'; };
          path.onmouseleave = () => { path.style.opacity = '1'; };

          // Label text si tranche suffisamment grande (> 5%)
          if (frac > 0.05) {
            const mid = angle + frac * Math.PI;
            const lx = cx + (radius + 18) * Math.cos(mid);
            const ly = cy + (radius + 18) * Math.sin(mid) + 4;
            const anchor = Math.cos(mid) >= 0 ? 'start' : 'end';
            sk('text', {
              x: lx.toFixed(1),
              y: ly.toFixed(1),
              'text-anchor': anchor,
              class: 'ax',
              'font-size': '11'
            }, sv).textContent = `${(s.wh / 1000).toFixed(2)} kWh`;
          }
          angle = a1;
        }
      });

      // Légende
      const leg = mk('div', 'pie-legend', null, sec);
      slices.forEach((s) => {
        const item = mk('span', null, null, leg);
        const icon = mk('i', null, null, item);
        icon.style.background = s.color;
        item.appendChild(document.createTextNode(`${s.name} ${s.percent} %`));
      });
    }

    _renderArea(container) {
      const areaData = this._data.area;
      if (!areaData || !areaData.layers) return;

      const sec = mk('div', 'area-section', null, container);
      mk('div', 'area-title', areaData.title, sec);

      const ctl = mk('div', 'ctl', null, sec);
      const minRes = Math.max(1, Math.round(areaData.bucket_s / 60));
      const RES = [5, 10, 15, 30, 60].filter((r) => r >= minRes);
      const SMOOTH = [[0, 'Aucun'], [10, 'Léger'], [20, 'Moyen'], [40, 'Fort']];

      mk('span', null, 'Résolution', ctl);
      const selRes = mk('select', null, null, ctl);
      RES.forEach((r) => {
        mk('option', null, r === 60 ? '1 h' : r + ' min', selRes).value = String(r);
      });
      selRes.value = String(this._S.res);
      selRes.onchange = () => {
        this._S.res = parseInt(selRes.value, 10);
        drawArea();
      };

      mk('span', null, 'Lissage', ctl);
      const selSm = mk('select', null, null, ctl);
      SMOOTH.forEach((o) => {
        mk('option', null, o[1], selSm).value = String(o[0]);
      });
      selSm.value = String(this._S.sm);
      selSm.onchange = () => {
        this._S.sm = parseInt(selSm.value, 10);
        drawArea();
      };

      const bLin = mk('button', null, 'Linéaire', ctl);
      const bSqrt = mk('button', null, 'Compressée (√)', ctl);
      bSqrt.title = 'Échelle compressée (racine carrée) : met en valeur les veilles face aux gros pics';
      bLin.onclick = () => { this._S.scale = 'lin'; drawArea(); };
      bSqrt.onclick = () => { this._S.scale = 'sqrt'; drawArea(); };

      const bGrp = mk('button', null, 'Par catégorie', ctl);
      bGrp.onclick = () => {
        this._S.group = !this._S.group;
        buildLegend();
        drawArea();
      };

      const bLeft = mk('button', null, '←', ctl);
      const bOut = mk('button', null, '−', ctl);
      const bIn = mk('button', null, '+', ctl);
      const bRight = mk('button', null, '→', ctl);
      const bReset = mk('button', null, 'Tout afficher', ctl);
      bLeft.title = 'Décaler vers le début de journée';
      bRight.title = 'Décaler vers la fin de journée';
      bOut.title = 'Dézoomer';
      bIn.title = 'Zoomer';

      const leg = mk('div', 'leg', null, sec);
      const wrap = mk('div', 'wrap', null, sec);
      const sv = sk('svg', {}, wrap);
      const tip = mk('div', 'tip', null, wrap);
      mk(
        'div',
        'hint',
        'Glissez sur le graphique pour zoomer · double-clic : tout afficher · Ctrl + molette : zoom · cliquez sur la légende pour masquer un appareil',
        sec
      );

      const layersFor = (group) => {
        if (!group) return areaData.layers;
        const order = [], map = {};
        areaData.layers.forEach((L) => {
          const key = L.cat || '_';
          if (!map[key]) {
            const c = (areaData.cats && areaData.cats[key]) || [L.name, L.color];
            map[key] = { name: c[0], color: c[1], cat: key, w: new Array(areaData.n).fill(0) };
            order.push(key);
          }
          for (let k = 0; k < areaData.n; k++) {
            map[key].w[k] += L.w[k];
          }
        });
        return order.map((k) => map[k]);
      };

      let currentLayers = layersFor(this._S.group);

      const buildLegend = () => {
        leg.innerHTML = '';
        currentLayers = layersFor(this._S.group);
        currentLayers.forEach((L, i) => {
          const s = mk('span', this._S.hidden[i] ? 'off' : null, null, leg);
          mk('i', null, null, s).style.background = L.color;
          mk('b', null, L.name, s).style.fontWeight = 'normal';
          s.onclick = () => {
            if (this._S.hidden[i]) {
              delete this._S.hidden[i];
              s.className = '';
            } else {
              this._S.hidden[i] = true;
              s.className = 'off';
            }
            drawArea();
          };
        });
      };
      buildLegend();

      // Maths d'interpolation & échelle
      const niceScale = (m) => {
        if (m <= 0) return { top: 100, step: 20 };
        const e = Math.pow(10, Math.floor(Math.log10(m)));
        const ms = [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10];
        for (let i = 0; i < ms.length; i++) {
          const s = ms[i] * e;
          if (m / s <= 6) return { top: Math.ceil(m / s - 1e-9) * s, step: s };
        }
        return { top: 10 * e, step: 2 * e };
      };

      const smoothArr = (a, hw) => {
        if (hw <= 0 || a.length < 2) return a.slice();
        const out = [], n = a.length;
        for (let i = 0; i < n; i++) {
          let num = 0, den = 0;
          for (let k = -hw; k <= hw; k++) {
            const j = i + k;
            if (j >= 0 && j < n) {
              const w = hw + 1 - Math.abs(k);
              num += w * a[j];
              den += w;
            }
          }
          out.push(num / den);
        }
        return out;
      };

      const monoSamples = (xs, ys, sub) => {
        const n = xs.length, ox = [], oy = [], d = [], m = [];
        if (n < 2) return { x: xs.slice(), y: ys.slice() };
        for (let i = 0; i < n - 1; i++) {
          const dx = xs[i + 1] - xs[i];
          d.push(dx === 0 ? 0 : (ys[i + 1] - ys[i]) / dx);
        }
        m[0] = d[0];
        m[n - 1] = d[n - 2];
        for (let i = 1; i < n - 1; i++) {
          m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
        }
        for (let i = 0; i < n - 1; i++) {
          if (d[i] === 0) {
            m[i] = 0;
            m[i + 1] = 0;
            continue;
          }
          const a = m[i] / d[i], b = m[i + 1] / d[i], s = a * a + b * b;
          if (s > 9) {
            const q = 3 / Math.sqrt(s);
            m[i] = q * a * d[i];
            m[i + 1] = q * b * d[i];
          }
        }
        for (let i = 0; i < n - 1; i++) {
          const h = xs[i + 1] - xs[i];
          for (let j = 0; j < sub; j++) {
            const t = j / sub, t2 = t * t, t3 = t2 * t;
            const y = (2 * t3 - 3 * t2 + 1) * ys[i] +
                      (t3 - 2 * t2 + t) * h * m[i] +
                      (-2 * t3 + 3 * t2) * ys[i + 1] +
                      (t3 - t2) * h * m[i + 1];
            ox.push(xs[i] + t * h);
            oy.push(Math.max(0, y));
          }
        }
        ox.push(xs[n - 1]);
        oy.push(ys[n - 1]);
        return { x: ox, y: oy };
      };

      const groups = () => {
        const k = Math.max(1, Math.round(this._S.res * 60 / areaData.bucket_s)), out = [];
        for (let g = 0; g < areaData.n; g += k) {
          const e = Math.min(g + k, areaData.n), c = e - g, v = [];
          for (let li = 0; li < currentLayers.length; li++) {
            const w = currentLayers[li].w;
            let s = 0;
            for (let i = g; i < e; i++) s += w[i];
            v.push(s / c);
          }
          out.push({
            t0: g * areaData.bucket_s,
            t1: e * areaData.bucket_s,
            tc: ((g + e) / 2) * areaData.bucket_s,
            v: v,
            s: []
          });
        }
        return out;
      };

      const clampRange = (a, b) => {
        let span = b - a;
        if (span > areaData.day_seconds) span = areaData.day_seconds;
        if (span < 1800) span = 1800;
        if (a < 0) a = 0;
        b = a + span;
        if (b > areaData.day_seconds) {
          b = areaData.day_seconds;
          a = b - span;
        }
        return [Math.max(0, a), b];
      };

      const zoomTo = (a, b) => {
        const r = clampRange(a, b);
        this._S.t0 = r[0];
        this._S.t1 = r[1];
        this._isZoomed = this._S.t0 > 0 || this._S.t1 < areaData.day_seconds;
        drawArea();
      };

      bIn.onclick = () => {
        const c = (this._S.t0 + this._S.t1) / 2, h = (this._S.t1 - this._S.t0) / 4;
        zoomTo(c - h, c + h);
      };
      bOut.onclick = () => {
        const c = (this._S.t0 + this._S.t1) / 2, h = this._S.t1 - this._S.t0;
        zoomTo(c - h, c + h);
      };
      bLeft.onclick = () => {
        const q = (this._S.t1 - this._S.t0) / 4;
        zoomTo(this._S.t0 - q, this._S.t1 - q);
      };
      bRight.onclick = () => {
        const q = (this._S.t1 - this._S.t0) / 4;
        zoomTo(this._S.t0 + q, this._S.t1 + q);
      };
      bReset.onclick = () => {
        zoomTo(0, areaData.day_seconds);
      };

      const drawArea = () => {
        bLin.className = this._S.scale === 'lin' ? 'on' : '';
        bSqrt.className = this._S.scale === 'sqrt' ? 'on' : '';
        bGrp.className = this._S.group ? 'on' : '';

        const W = Math.max(300, Math.floor(wrap.clientWidth || 600));
        const H = W < 500 ? 300 : 400;
        const ml = 54, mr = 14, mt = 10, mb = 30;
        const pw = W - ml - mr, ph = H - mt - mb;

        sv.setAttribute('viewBox', `0 0 ${W} ${H}`);
        sv.setAttribute('width', W);
        sv.setAttribute('height', H);
        sv.innerHTML = '';
        tip.style.display = 'none';

        const G = groups(), vis = [];
        currentLayers.forEach((L, li) => {
          if (!this._S.hidden[li]) vis.push(li);
        });

        const hw = this._S.sm > 0 ? Math.max(1, Math.round(this._S.sm / this._S.res)) : 0;
        vis.forEach((li) => {
          const sm = smoothArr(G.map((g) => g.v[li]), hw);
          G.forEach((g, gi) => { g.s[li] = sm[gi]; });
        });

        const span = this._S.t1 - this._S.t0;
        let lo = 0, hi = G.length - 1;
        for (let i = 0; i < G.length; i++) {
          if (G[i].t1 > this._S.t0) { lo = Math.max(0, i - 1); break; }
        }
        for (let i = G.length - 1; i >= 0; i--) {
          if (G[i].t0 < this._S.t1) { hi = Math.min(G.length - 1, i + 1); break; }
        }

        const sl = G.slice(lo, hi + 1);
        const sub = Math.max(1, Math.min(24, Math.ceil(pw / Math.max(1, span / (this._S.res * 60)) / 4)));
        let smp = [], sx = [];
        if (sl.length) {
          let xsl = sl.map((g) => g.tc);
          if (sl.length === 1) xsl = [sl[0].t0, sl[0].t1];
          smp = vis.map((li) => {
            let ys = sl.map((g) => g.s[li]);
            if (sl.length === 1) ys = [ys[0], ys[0]];
            return monoSamples(xsl, ys, sub);
          });
          sx = smp.length ? smp[0].x : xsl;
        }

        const cum = [new Array(sx.length).fill(0)];
        smp.forEach((s, k) => {
          const c = [];
          for (let q = 0; q < sx.length; q++) {
            c.push(cum[k][q] + s.y[q]);
          }
          cum.push(c);
        });

        let ymax = 0;
        const topc = cum[cum.length - 1] || [];
        for (let j = 0; j < sx.length; j++) {
          if (sx[j] >= this._S.t0 && sx[j] <= this._S.t1) {
            ymax = Math.max(ymax, topc[j]);
          }
        }

        const sc = niceScale(ymax * 1.03);
        const top = sc.top;

        const X = (t) => ml + ((t - this._S.t0) / span) * pw;
        const F = (v) => {
          v = Math.max(v, 0) / top;
          return this._S.scale === 'sqrt' ? Math.sqrt(v) : v;
        };
        const Y = (v) => mt + ph - F(v) * ph;

        // Axe Y
        const ticks = [];
        if (this._S.scale === 'lin') {
          for (let v = 0; v <= top + 1e-9; v += sc.step) ticks.push(v);
        } else {
          const cand = [0];
          for (let e = 1; e <= top; e *= 10) {
            [1, 2, 5].forEach((mm) => { if (mm * e <= top) cand.push(mm * e); });
          }
          let lastY = 1e9;
          cand.forEach((c) => {
            const y = Y(c);
            if (lastY - y >= 20 || c === 0) { ticks.push(c); lastY = y; }
          });
        }

        ticks.forEach((tv) => {
          const y = Y(tv);
          sk('line', { x1: ml, x2: ml + pw, y1: y, y2: y, class: 'gl' }, sv);
          sk('text', {
            x: ml - 6, y: y + 4, 'text-anchor': 'end', class: 'ax'
          }, sv).textContent = Math.round(tv * 10) / 10 + ' W';
        });

        // Axe X
        const steps = [600, 900, 1800, 3600, 7200, 10800, 21600];
        let xsStep = 21600;
        for (let i = 0; i < steps.length; i++) {
          if (span / steps[i] <= 10) { xsStep = steps[i]; break; }
        }
        for (let t = Math.ceil(this._S.t0 / xsStep) * xsStep; t <= this._S.t1 + 1e-6; t += xsStep) {
          const x = X(t);
          sk('line', { x1: x, x2: x, y1: mt + ph, y2: mt + ph + 4, class: 'gl' }, sv);
          sk('text', {
            x: x, y: mt + ph + 18, 'text-anchor': 'middle', class: 'ax'
          }, sv).textContent = xsStep >= 3600 ? Math.round(t / 3600) + ' h' : hm(t);
        }

        // Couches
        const defs = sk('defs', {}, sv);
        const clipId = 'heg-card-clip-' + Math.random().toString(36).substr(2, 6);
        const clip = sk('clipPath', { id: clipId }, defs);
        sk('rect', { x: ml, y: mt, width: pw, height: ph }, clip);

        const gl = sk('g', { 'clip-path': `url(#${clipId})` }, sv);

        if (!G.length) {
          sk('text', {
            x: ml + pw / 2, y: mt + ph / 2, 'text-anchor': 'middle', class: 'ax'
          }, sv).textContent = 'Pas encore de données';
        }

        vis.forEach((li, k) => {
          const yv = smp[k].y;
          let mx = 0;
          for (let j = 0; j < yv.length; j++) mx = Math.max(mx, yv[j]);
          if (mx < 0.05) return;

          const up = [], dn = [];
          for (let j = 0; j < sx.length; j++) up.push(`${f1(X(sx[j]))},${f1(Y(cum[k + 1][j]))}`);
          for (let j = sx.length - 1; j >= 0; j--) dn.push(`${f1(X(sx[j]))},${f1(Y(cum[k][j]))}`);

          const p = sk('path', {
            d: 'M' + up.join('L') + 'L' + dn.join('L') + 'Z',
            fill: currentLayers[li].color,
            'fill-opacity': '0.92',
            stroke: 'var(--card-background-color, #fff)',
            'stroke-width': '0.6'
          }, gl);
          sk('title', {}, p).textContent = currentLayers[li].name;
        });

        // Curseur & Zoom interactif
        const cross = sk('line', {
          y1: mt, y2: mt + ph, class: 'gl', 'stroke-width': '1.5', visibility: 'hidden'
        }, sv);
        cross.setAttribute('stroke', 'var(--primary-text-color, #222)');

        const ov = sk('rect', {
          x: ml, y: mt, width: pw, height: ph, fill: 'transparent', style: 'touch-action:none;cursor:crosshair'
        }, sv);
        const selr = sk('rect', { y: mt, height: ph, class: 'sel', visibility: 'hidden' }, sv);

        let drag = null;
        const px = (ev) => {
          const r = sv.getBoundingClientRect();
          return (ev.clientX - r.left) * (W / r.width);
        };
        const tOf = (p) => this._S.t0 + ((p - ml) / pw) * span;

        const showTip = (ev) => {
          const tt = tOf(px(ev));
          let g = null;
          for (let q = 0; q < G.length; q++) {
            if (tt >= G[q].t0 && tt < G[q].t1) { g = G[q]; break; }
          }
          if (!g) {
            tip.style.display = 'none';
            cross.setAttribute('visibility', 'hidden');
            return;
          }
          const cx = X(g.tc);
          cross.setAttribute('x1', cx);
          cross.setAttribute('x2', cx);
          cross.setAttribute('visibility', 'visible');

          tip.innerHTML = '';
          mk('div', null, `${hm(g.t0)} – ${hm(g.t1)}`, tip).style.fontWeight = 'bold';

          const rows = [];
          let tot = 0;
          vis.forEach((li) => {
            tot += g.s[li];
            if (g.s[li] >= 0.5) rows.push([li, g.s[li]]);
          });
          rows.sort((a, b) => b[1] - a[1]);
          rows.forEach((r) => {
            const line = mk('div', null, null, tip);
            const nm = mk('span', null, null, line);
            const sw = mk('i', null, null, nm);
            sw.style.cssText = `display:inline-block;width:10px;height:10px;margin-right:6px;border-radius:2px;background:${currentLayers[r[0]].color};`;
            nm.appendChild(document.createTextNode(currentLayers[r[0]].name));
            mk('span', null, `${Math.round(r[1])} W`, line);
          });

          const last = mk('div', null, null, tip);
          last.style.cssText = 'border-top:1px solid var(--divider-color, #ddd);margin-top:4px;padding-top:4px;font-weight:bold;';
          mk('span', null, 'Total', last);
          mk('span', null, `${Math.round(tot)} W`, last);

          tip.style.display = 'block';
          const r2 = sv.getBoundingClientRect();
          const xpx = cx * (r2.width / W);
          let left = xpx + 14;
          if (left + tip.offsetWidth > wrap.clientWidth) {
            left = xpx - tip.offsetWidth - 14;
          }
          tip.style.left = `${Math.max(0, left)}px`;
        };

        ov.addEventListener('pointerdown', (ev) => {
          if (ev.pointerType === 'mouse' && ev.button !== 0) return;
          drag = { x0: px(ev) };
          try { ov.setPointerCapture(ev.pointerId); } catch (err) { /* ignore */ }
        });

        ov.addEventListener('pointermove', (ev) => {
          if (drag) {
            const p = px(ev);
            const a = Math.max(ml, Math.min(p, drag.x0));
            const b = Math.min(ml + pw, Math.max(p, drag.x0));
            selr.setAttribute('x', a);
            selr.setAttribute('width', Math.max(0, b - a));
            selr.setAttribute('visibility', 'visible');
            tip.style.display = 'none';
          } else {
            showTip(ev);
          }
        });

        ov.addEventListener('pointerup', (ev) => {
          if (!drag) return;
          const p = px(ev), x0 = drag.x0;
          drag = null;
          selr.setAttribute('visibility', 'hidden');
          if (Math.abs(p - x0) > 8) {
            zoomTo(tOf(Math.min(p, x0)), tOf(Math.max(p, x0)));
          }
        });

        ov.addEventListener('pointerleave', () => {
          if (!drag) {
            tip.style.display = 'none';
            cross.setAttribute('visibility', 'hidden');
          }
        });

        ov.addEventListener('dblclick', () => {
          zoomTo(0, areaData.day_seconds);
        });

        ov.addEventListener('wheel', (ev) => {
          if (!(ev.ctrlKey || ev.metaKey)) return;
          ev.preventDefault();
          const tt = tOf(px(ev));
          const f = ev.deltaY < 0 ? 0.8 : 1.25;
          zoomTo(tt - (tt - this._S.t0) * f, tt + (this._S.t1 - tt) * f);
        }, { passive: false });
      };

      drawArea();
    }
  }

  // Déclaration du custom card pour Home Assistant
  // Le script est chargé très tôt (add_extra_js_url), avant que le frontend de HA installe son
  // polyfill de registre « scoped ». Une définition faite avant ne serait pas visible par
  // customElements.get() (et HA afficherait « Custom element doesn't exist »). On attend donc
  // que l'application soit définie, puis on enregistre la carte dans le registre courant.
  const CARD_TAG = 'ha-energy-graph-card';
  const registerCard = () => {
    const registry = window.customElements;
    if (!registry.get(CARD_TAG)) registry.define(CARD_TAG, HaEnergyGraphCard);
  };
  if (window.customElements.get('home-assistant')) {
    registerCard();
  } else {
    window.customElements.whenDefined('home-assistant').then(registerCard);
    setTimeout(registerCard, 15000); // filet de sécurité, sans effet si déjà défini
  }

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'ha-energy-graph-card',
    name: "Graphique d'énergie",
    description: "Aires empilées et camembert interactifs de la consommation du jour",
    preview: false,
    documentationURL: 'https://github.com/maximeblanchard/ha_energy_graph'
  });
})();