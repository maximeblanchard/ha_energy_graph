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
      this._period = 'day'; // 'day', '7d', 'month', 'year', 'custom'
      this._selectedDate = null;
      this._selectedEnd = null;
      this._selectedMonth = null;
      this._selectedYear = null;
      this._selectedStart = null;
      try {
        this._optionsOpen = localStorage.getItem('ha_eg_card_opt_open') === '1';
      } catch (e) {
        this._optionsOpen = false;
      }
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
      if (this._config.period && ['day', '7d', 'month', 'year', 'custom'].includes(this._config.period)) {
        this._period = this._config.period;
      }
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
          period: this._period || 'day',
        };
        if (this._config.entry_id) {
          payload.entry_id = this._config.entry_id;
        }
        if (this._period === '7d') {
          if (this._selectedEnd) payload.end = this._selectedEnd;
        } else if (this._period === 'month') {
          if (this._selectedMonth) payload.month = this._selectedMonth;
        } else if (this._period === 'year') {
          if (this._selectedYear) payload.year = this._selectedYear;
        } else if (this._period === 'custom') {
          if (this._selectedStart) payload.start = this._selectedStart;
          if (this._selectedEnd) payload.end = this._selectedEnd;
        } else {
          if (this._selectedDate) payload.date = this._selectedDate;
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
        .period-badge-btn {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, rgba(127,127,127,0.25));
          border-radius: 9999px;
          padding: 5px 14px;
          font-size: 0.95rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .period-badge-btn:hover, .nav-btn:not(:disabled):hover {
          border-color: var(--primary-color, #03a9f4);
        }
        .period-badge-btn .badge-arrow {
          font-size: 0.65rem;
          opacity: 0.7;
          transition: transform 0.2s ease;
        }
        .period-badge-btn.open .badge-arrow {
          transform: rotate(180deg);
        }
        .opt-panel {
          background: var(--secondary-background-color, rgba(127,127,127,0.08));
          border: 1px solid var(--divider-color, rgba(127,127,127,0.2));
          border-radius: 10px;
          padding: 10px 14px;
          margin-bottom: 14px;
        }
        .opt-row {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 8px;
          flex-wrap: wrap;
        }
        .opt-row:last-of-type {
          margin-bottom: 4px;
        }
        .opt-lbl {
          font-size: 0.82rem;
          font-weight: 600;
          opacity: 0.85;
          min-width: 70px;
        }
        .pills {
          display: inline-flex;
          gap: 6px;
          flex-wrap: wrap;
        }
        .pill {
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, rgba(127,127,127,0.25));
          border-radius: 9999px;
          padding: 3px 10px;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .pill:hover {
          border-color: var(--primary-color, #03a9f4);
        }
        .pill.active {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border-color: var(--primary-color, #03a9f4);
          font-weight: 600;
        }
        .date-ctrls {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          flex-wrap: wrap;
          font-size: 0.85rem;
        }
        .btn-apply {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border: none;
          border-radius: 6px;
          padding: 3px 10px;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
        }
        .btn-hide-opt {
          display: block;
          margin-left: auto;
          background: transparent;
          border: none;
          color: var(--secondary-text-color, #888);
          font-size: 0.75rem;
          cursor: pointer;
          padding: 2px 4px;
        }
        .btn-hide-opt:hover {
          color: var(--primary-text-color);
          text-decoration: underline;
        }
        .gear-btn {
          font-size: 1rem;
          padding: 4px 8px;
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
        .pie-svg {
          display: block;
          width: 100%;
          max-width: 560px;
          height: auto;
          margin: 0 auto;
          overflow: visible;
        }
        .pie-slice, .pie-lbl {
          transition: transform 0.18s ease, opacity 0.15s;
        }
        .pie-slice {
          cursor: pointer;
        }
        .pie-slice:hover {
          opacity: 0.88;
        }
        .pie-lbl {
          font-weight: 700;
          pointer-events: none;
        }
        .pie-lbl tspan.u {
          font-weight: 400;
          opacity: 0.9;
        }
        .pie-lbl.p {
          font-weight: 500;
        }
        .pie-out {
          fill: var(--primary-text-color, #222);
          font-weight: 700;
          cursor: pointer;
        }
        .pie-out tspan.p {
          font-weight: 400;
          opacity: 0.8;
        }
        .pie-out.on {
          font-weight: 800;
        }
        .pie-lead {
          fill: none;
          stroke: var(--secondary-text-color, #888);
          stroke-width: 1.2;
          opacity: 0.6;
        }
        .pie-lead.on {
          stroke-width: 2.2;
          opacity: 1;
        }
        .pie-list {
          max-width: 520px;
          margin: 12px auto 0;
        }
        .pie-row {
          display: grid;
          grid-template-columns: 14px minmax(0, 1fr) auto 3.8em;
          align-items: center;
          gap: 10px;
          padding: 7px 8px;
          border-radius: 8px;
          font-size: 0.95rem;
          cursor: pointer;
        }
        .pie-row + .pie-row {
          border-top: 1px solid var(--divider-color, rgba(127, 127, 127, 0.15));
        }
        .pie-row.on {
          background: var(--secondary-background-color, rgba(127, 127, 127, 0.14));
        }
        .pie-row i {
          width: 14px;
          height: 14px;
          border-radius: 3px;
        }
        .pie-row .nm {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .pie-row .kw, .pie-row .pc {
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
        .pie-row .kw {
          opacity: 0.8;
        }
        .pie-row .pc {
          font-weight: 600;
        }
        @media (max-width: 500px) {
          ha-card {
            padding: 10px;
          }
          .pie-row {
            padding: 6px 4px;
            gap: 8px;
          }
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

      // Sélecteur d'onglets (Tout, Évolution/Aires, Camembert)
      const tabs = mk('div', 'tabs', null, header);
      const bBoth = mk('button', `tab-btn ${this._view === 'both' ? 'active' : ''}`, 'Tout', tabs);
      const bArea = mk('button', `tab-btn ${this._view === 'area' ? 'active' : ''}`, this._period === 'day' ? 'Aires' : 'Évolution', tabs);
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

      // Barre de navigation temporelle compacte
      const nav = mk('div', 'nav-bar', null, card);
      const bPrev = mk('button', 'nav-btn', '◀', nav);
      bPrev.title = 'Période précédente';
      bPrev.onclick = () => { this._stepPeriod(-1); };

      const isCurrent = this._data && (this._data.is_current !== undefined ? this._data.is_current : this._data.is_today);
      let periodLabel = "Aujourd'hui";
      if (this._period === 'day') {
        periodLabel = this._data.is_today ? "Aujourd'hui" : this._formatDateFR(this._data.date);
      } else if (this._period === '7d') {
        periodLabel = isCurrent ? "7 derniers jours" : `7j au ${this._formatShortDate(this._data.end_date)}`;
      } else if (this._period === 'month') {
        periodLabel = this._formatMonthFR(this._data.date || this._data.start_date);
      } else if (this._period === 'year') {
        periodLabel = `Année ${(this._data.date || this._data.start_date || '').slice(0, 4)}`;
      } else if (this._period === 'custom') {
        periodLabel = `${this._formatShortDate(this._data.start_date)} – ${this._formatShortDate(this._data.end_date)}`;
      }

      const bToggle = mk('button', `period-badge-btn ${this._optionsOpen ? 'open' : ''}`, null, nav);
      mk('span', 'badge-cal', '📅', bToggle);
      mk('span', 'badge-txt', periodLabel, bToggle);
      mk('span', 'badge-arrow', '▼', bToggle);
      bToggle.title = 'Changer de période ou afficher/masquer les options';
      bToggle.onclick = () => {
        this._optionsOpen = !this._optionsOpen;
        try { localStorage.setItem('ha_eg_card_opt_open', this._optionsOpen ? '1' : '0'); } catch(e) {}
        this._render();
      };

      const bNext = mk('button', 'nav-btn', '▶', nav);
      bNext.title = 'Période suivante';
      bNext.disabled = isCurrent;
      bNext.onclick = () => { this._stepPeriod(1); };

      if (!isCurrent) {
        const bToday = mk('button', 'today-btn', this._period === 'day' ? "Aujourd'hui" : "Actuel", nav);
        bToday.title = "Revenir à la période actuelle";
        bToday.onclick = () => {
          this._resetToCurrent();
          this._loadData();
        };
      }

      const bGear = mk('button', 'nav-btn gear-btn', '⚙', nav);
      bGear.title = "Options d'affichage et sélection de période";
      bGear.onclick = () => {
        this._optionsOpen = !this._optionsOpen;
        try { localStorage.setItem('ha_eg_card_opt_open', this._optionsOpen ? '1' : '0'); } catch(e) {}
        this._render();
      };

      // Panneau d'options rétractable
      if (this._optionsOpen) {
        const optPanel = mk('div', 'opt-panel', null, card);

        // Ligne 1 : Choix de la période
        const rowP = mk('div', 'opt-row', null, optPanel);
        mk('span', 'opt-lbl', 'Période :', rowP);
        const pillsP = mk('div', 'pills', null, rowP);
        const periods = [
          ['day', 'Jour'],
          ['7d', '7 jours'],
          ['month', 'Mois'],
          ['year', 'Année'],
          ['custom', 'Personnalisé']
        ];
        periods.forEach(([k, label]) => {
          const pBtn = mk('button', `pill ${this._period === k ? 'active' : ''}`, label, pillsP);
          pBtn.onclick = () => {
            this._period = k;
            this._resetToCurrent();
            this._loadData();
          };
        });

        // Ligne 2 : Sélecteur de date adapté
        const rowD = mk('div', 'opt-row', null, optPanel);
        mk('span', 'opt-lbl', 'Sélecteur :', rowD);
        const dCtrl = mk('div', 'date-ctrls', null, rowD);

        if (this._period === 'day') {
          const inp = mk('input', 'date-input', null, dCtrl);
          inp.type = 'date';
          inp.value = this._data.date;
          inp.max = this._data.today;
          inp.onchange = () => {
            if (inp.value) { this._selectedDate = inp.value; this._loadData(); }
          };
        } else if (this._period === '7d') {
          mk('span', null, 'Fin le :', dCtrl);
          const inp = mk('input', 'date-input', null, dCtrl);
          inp.type = 'date';
          inp.value = this._data.end_date || this._data.today;
          inp.max = this._data.today;
          inp.onchange = () => {
            if (inp.value) { this._selectedEnd = inp.value; this._loadData(); }
          };
        } else if (this._period === 'month') {
          const inp = mk('input', 'date-input', null, dCtrl);
          inp.type = 'month';
          const curM = (this._data.date || this._data.start_date || this._data.today).slice(0, 7);
          inp.value = curM;
          inp.max = this._data.today.slice(0, 7);
          inp.onchange = () => {
            if (inp.value) { this._selectedMonth = inp.value; this._loadData(); }
          };
        } else if (this._period === 'year') {
          const inp = mk('input', 'date-input', null, dCtrl);
          inp.type = 'number';
          inp.min = '2020';
          inp.max = this._data.today.slice(0, 4);
          inp.value = (this._data.date || this._data.start_date || this._data.today).slice(0, 4);
          inp.style.width = '85px';
          inp.onchange = () => {
            if (inp.value) { this._selectedYear = inp.value; this._loadData(); }
          };
        } else if (this._period === 'custom') {
          mk('span', null, 'Du', dCtrl);
          const sInp = mk('input', 'date-input', null, dCtrl);
          sInp.type = 'date';
          sInp.value = this._data.start_date || this._data.today;
          sInp.max = this._data.today;

          mk('span', null, 'au', dCtrl);
          const eInp = mk('input', 'date-input', null, dCtrl);
          eInp.type = 'date';
          eInp.value = this._data.end_date || this._data.today;
          eInp.max = this._data.today;

          const bApply = mk('button', 'btn-apply', 'OK', dCtrl);
          bApply.onclick = () => {
            if (sInp.value && eInp.value) {
              this._selectedStart = sInp.value;
              this._selectedEnd = eInp.value;
              this._loadData();
            }
          };
        }

        const bHide = mk('button', 'btn-hide-opt', 'Masquer les options ✕', optPanel);
        bHide.onclick = () => {
          this._optionsOpen = false;
          try { localStorage.setItem('ha_eg_card_opt_open', '0'); } catch(e) {}
          this._render();
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

      // 2. Vue Aires empilées (si Jour) ou Colonnes empilées (si multi-jours)
      if (this._view === 'both' || this._view === 'area') {
        if (this._period === 'day') {
          this._renderArea(card);
        } else {
          this._renderBars(card);
        }
      }
    }


    _stepPeriod(dir) {
      if (!this._data) return;
      const today = this._data.today;
      if (this._period === 'day') {
        const cur = this._data.date || today;
        const [y, m, d] = cur.split('-').map(Number);
        const dt = new Date(Date.UTC(y, m - 1, d));
        dt.setUTCDate(dt.getUTCDate() + dir);
        let nStr = dt.toISOString().split('T')[0];
        if (nStr > today) nStr = today;
        this._selectedDate = nStr;
      } else if (this._period === '7d') {
        const cur = this._data.end_date || today;
        const [y, m, d] = cur.split('-').map(Number);
        const dt = new Date(Date.UTC(y, m - 1, d));
        dt.setUTCDate(dt.getUTCDate() + dir * 7);
        let nStr = dt.toISOString().split('T')[0];
        if (nStr > today) nStr = today;
        this._selectedEnd = nStr;
      } else if (this._period === 'month') {
        const cur = (this._data.date || this._data.start_date || today).slice(0, 7);
        let [y, m] = cur.split('-').map(Number);
        m += dir;
        if (m < 1) { m = 12; y--; } else if (m > 12) { m = 1; y++; }
        let nStr = `${y}-${pad(m)}`;
        if (nStr > today.slice(0, 7)) nStr = today.slice(0, 7);
        this._selectedMonth = nStr;
      } else if (this._period === 'year') {
        const cur = (this._data.date || this._data.start_date || today).slice(0, 4);
        let y = parseInt(cur, 10) + dir;
        const maxYear = parseInt(today.slice(0, 4), 10);
        if (y > maxYear) y = maxYear;
        this._selectedYear = y;
      } else if (this._period === 'custom') {
        const s = this._data.start_date || today;
        const e = this._data.end_date || today;
        const dtS = new Date(s);
        const dtE = new Date(e);
        const spanDays = Math.max(1, Math.round((dtE - dtS) / 86400000) + 1);
        dtS.setDate(dtS.getDate() + dir * spanDays);
        dtE.setDate(dtE.getDate() + dir * spanDays);
        const cap = new Date(today);
        if (dtE > cap) dtE.setTime(cap.getTime());
        this._selectedStart = dtS.toISOString().split('T')[0];
        this._selectedEnd = dtE.toISOString().split('T')[0];
      }
      this._loadData();
    }

    _resetToCurrent() {
      this._selectedDate = null;
      this._selectedEnd = null;
      this._selectedMonth = null;
      this._selectedYear = null;
      this._selectedStart = null;
    }

    _formatDateFR(iso) {
      if (!iso) return '';
      const [y, m, d] = iso.split('-').map(Number);
      const MOIS = ["", "janv.", "févr.", "mars", "avril", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
      return `${d} ${MOIS[m] || ''} ${y}`;
    }

    _formatMonthFR(iso) {
      if (!iso) return '';
      const [y, m] = iso.slice(0, 7).split('-').map(Number);
      const MOIS = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];
      return `${MOIS[m] || ''} ${y}`;
    }

    _formatShortDate(iso) {
      if (!iso) return '';
      const parts = iso.split('-');
      if (parts.length >= 3) return `${parseInt(parts[2], 10)}/${parseInt(parts[1], 10)}`;
      return iso;
    }

    _renderBars(container) {
      const areaData = this._data.area;
      if (!areaData || !areaData.layers) return;

      const sec = mk('div', 'area-section', null, container);
      mk('div', 'area-title', areaData.title || 'Consommation par appareil', sec);

      const layers = areaData.layers.filter(l => !this._S.hidden[l.name] && l.wh && l.wh.some(v => v > 0));
      const n = areaData.n || (layers[0] ? layers[0].wh.length : 0);
      const labels = areaData.bucket_labels || [];

      const leg = mk('div', 'leg', null, sec);
      areaData.layers.forEach((L) => {
        const sp = mk('span', null, null, leg);
        const on = !this._S.hidden[L.name];
        sp.className = on ? '' : 'off';
        const sw = mk('i', null, null, sp);
        sw.style.background = L.color;
        mk('span', null, L.name, sp);
        sp.onclick = () => {
          this._S.hidden[L.name] = !this._S.hidden[L.name];
          sec.remove();
          this._renderBars(container);
        };
      });

      if (n <= 0 || !layers.length) {
        mk('div', 'hint', 'Pas de données de consommation pour cette période.', sec);
        return;
      }

      const wrap = mk('div', 'wrap', null, sec);
      const tip = mk('div', 'tip', null, wrap);

      const W = 900, H = 340;
      const ml = 65, mr = 20, mt = 20, mb = 45;
      const pw = W - ml - mr, ph = H - mt - mb;

      const sv = sk('svg', { viewBox: `0 0 ${W} ${H}`, style: 'width:100%;height:auto;display:block;' }, wrap);

      const cols = [];
      const colTotals = [];
      for (let i = 0; i < n; i++) {
        const vals = layers.map(l => (l.wh[i] || 0) / 1000);
        cols.push(vals);
        colTotals.push(vals.reduce((a, b) => a + b, 0));
      }

      let maxVal = Math.max(...colTotals, 1);
      function niceMax(v) {
        if (v <= 0) return 1;
        const exp = Math.pow(10, Math.floor(Math.log10(v)));
        for (const m of [1, 2, 2.5, 5, 10]) {
          if (v <= m * exp) return m * exp;
        }
        return 10 * exp;
      }
      const top = niceMax(maxVal);

      function py(v) {
        return mt + ph - (v / top) * ph;
      }

      for (let k = 0; k <= 5; k++) {
        const v = (top * k) / 5;
        const y = py(v);
        sk('line', { class: 'gl', x1: ml, x2: ml + pw, y1: y.toFixed(1), y2: y.toFixed(1) }, sv);
        const t = sk('text', { class: 'ax', x: ml - 8, y: (y + 4).toFixed(1), 'text-anchor': 'end' }, sv);
        t.textContent = `${v % 1 === 0 ? v : v.toFixed(1)} kWh`;
      }

      const slotW = pw / n;
      const barW = Math.min(Math.max(slotW * 0.72, 3), 44);

      const gBars = sk('g', {}, sv);
      for (let i = 0; i < n; i++) {
        const cx = ml + (i + 0.5) * slotW;
        let cum = 0;
        layers.forEach((l, li) => {
          const val = cols[i][li];
          if (val <= 0) return;
          const y0 = py(cum);
          const y1 = py(cum + val);
          const h = Math.max(y0 - y1, 1);
          sk('rect', {
            x: (cx - barW / 2).toFixed(1),
            y: y1.toFixed(1),
            width: barW.toFixed(1),
            height: h.toFixed(1),
            fill: l.color,
            rx: 2
          }, gBars);
          cum += val;
        });
      }

      const stepLbl = n > 25 ? (n <= 35 ? 2 : Math.ceil(n / 15)) : 1;
      for (let i = 0; i < n; i += stepLbl) {
        const cx = ml + (i + 0.5) * slotW;
        const lbl = labels[i] || String(i + 1);
        const t = sk('text', { class: 'ax', x: cx.toFixed(1), y: (mt + ph + 22).toFixed(1), 'text-anchor': 'middle' }, sv);
        t.textContent = lbl;
      }

      const gHover = sk('g', {}, sv);
      for (let i = 0; i < n; i++) {
        const cx = ml + (i + 0.5) * slotW;
        const hRect = sk('rect', {
          x: (cx - slotW / 2).toFixed(1),
          y: mt.toFixed(1),
          width: slotW.toFixed(1),
          height: ph.toFixed(1),
          fill: 'transparent',
          style: 'cursor:pointer;'
        }, gHover);

        hRect.onmouseenter = (e) => {
          hRect.setAttribute('fill', 'rgba(127,127,127,0.15)');
          tip.style.display = 'block';
          tip.innerHTML = '';
          const lbl = labels[i] || String(i + 1);
          const tot = colTotals[i];
          const titleDiv = mk('div', null, null, tip);
          titleDiv.style.fontWeight = 'bold';
          titleDiv.style.marginBottom = '4px';
          titleDiv.textContent = `${lbl} — Total : ${tot.toFixed(2)} kWh`;

          const ranked = layers.map((l, li) => ({ name: l.name, color: l.color, val: cols[i][li] }))
            .filter(x => x.val >= 0.005)
            .sort((a, b) => b.val - a.val);

          ranked.forEach(r => {
            const row = mk('div', null, null, tip);
            const lSpan = mk('span', null, null, row);
            const dot = mk('i', null, null, lSpan);
            dot.style.display = 'inline-block';
            dot.style.width = '8px';
            dot.style.height = '8px';
            dot.style.borderRadius = '2px';
            dot.style.background = r.color;
            dot.style.marginRight = '6px';
            lSpan.appendChild(document.createTextNode(r.name));

            const pct = tot > 0 ? (r.val / tot * 100).toFixed(1) : '0';
            const rSpan = mk('span', null, `${r.val.toFixed(2)} kWh (${pct}%)`, row);
            rSpan.style.fontWeight = '500';
          });

          const bRect = wrap.getBoundingClientRect();
          const posX = e.clientX - bRect.left;
          if (posX > bRect.width / 2) {
            tip.style.left = 'auto';
            tip.style.right = `${bRect.width - posX + 10}px`;
          } else {
            tip.style.right = 'auto';
            tip.style.left = `${posX + 10}px`;
          }
          tip.style.top = '10px';
        };

        hRect.onmouseleave = () => {
          hRect.setAttribute('fill', 'transparent');
          tip.style.display = 'none';
        };
      }
    }

    _renderPie(container) {
      const pieData = this._data.pie;
      if (!pieData || !pieData.slices) return;

      const sec = mk('div', 'pie-section', null, container);
      mk('div', 'pie-title', pieData.title, sec);

      const slices = (pieData.slices || []).slice().sort((a, b) => (b.wh || 0) - (a.wh || 0));
      const total = pieData.total;
      const W = 460;

      if (total <= 0 || !slices.length) {
        const sv0 = sk('svg', { viewBox: `0 0 ${W} 120`, class: 'pie-svg' }, sec);
        sk('text', {
          x: W / 2, y: 60, 'text-anchor': 'middle', class: 'ax', 'font-size': '16'
        }, sv0).textContent = 'Pas de données d’énergie';
        return;
      }

      const kwhOf = (s) => (s.wh / 1000).toFixed(2);
      const pct = (s) => {
        const v = Number(s.percent);
        return isFinite(v) ? v.toFixed(1) : String(s.percent);
      };
      // Texte blanc ou noir selon la couleur de la part (meilleur contraste, sans contour)
      const textOn = (color) => {
        const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(color).trim());
        if (!m) return '#fff';
        const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        const L = 0.2126 * lin(parseInt(m[1], 16)) + 0.7152 * lin(parseInt(m[2], 16)) + 0.0722 * lin(parseInt(m[3], 16));
        return (1.05 / (L + 0.05)) * 1.2 >= (L + 0.05) / 0.05 ? '#fff' : '#111';
      };

      // Angles de chaque part
      const TAU = Math.PI * 2;
      const wedges = [];
      let ang = -Math.PI / 2;
      slices.forEach((s) => {
        const frac = s.wh / total;
        const full = frac >= 0.999;
        wedges.push({ a0: ang, a1: ang + frac * TAU, mid: ang + frac * Math.PI, frac, full });
        if (!full) ang += frac * TAU;
      });

      // Cherche si « kWh + % » tient dans la part (rectangle entièrement dans le secteur).
      // Retourne la position et la taille du texte, ou null s'il n'y a pas la place.
      const fitInside = (w, s, R) => {
        const kwh = kwhOf(s), pc = pct(s);
        const theta = w.a1 - w.a0;
        for (const fs of [18, 16, 14, 12.5]) {
          const fs2 = fs * 0.8;
          const bw = Math.max((kwh.length * 0.58 + 1.65) * fs, (pc.length + 2) * 0.58 * fs2) + 6;
          const bh = fs + fs2 * 1.1 + 6;
          const cand = w.full ? [0] : [0.62, 0.7, 0.78, 0.54, 0.84, 0.46];
          for (const k of cand) {
            const x = R * k * Math.cos(w.mid), y = R * k * Math.sin(w.mid);
            let ok = true;
            for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
              const px = x + sx * bw / 2, py = y + sy * bh / 2;
              const rr = Math.hypot(px, py);
              if (rr > R - 5) { ok = false; break; }
              if (!w.full) {
                let d = Math.atan2(py, px) - w.a0;
                d = ((d % TAU) + TAU) % TAU;
                const m = 3 / Math.max(rr, 1);
                if (d < m || d > theta - m) { ok = false; break; }
              }
            }
            if (ok) return { fs, fs2, x, y, bh };
          }
        }
        return null;
      };

      // Largeur des étiquettes extérieures (kWh sur une ligne, % dessous)
      const outW = slices.reduce((m, s) => Math.max(
        m, kwhOf(s).length * 0.58 * 13, (pct(s).length + 2) * 0.58 * 11
      ), 0) + 4;
      const padOut = outW + 16;
      const MAXR = 200;

      // Mise en page : le camembert prend toute la largeur ; on ne réserve de la place
      // sur un côté que s'il faut une étiquette extérieure de ce côté.
      let needL = false, needR = false, R = 150, cx = W / 2, plan = [];
      for (let it = 0; it < 4; it++) {
        const padL = needL ? padOut : 8, padR = needR ? padOut : 8;
        const avail = W - padL - padR;
        R = Math.min(MAXR, avail / 2);
        cx = padL + avail / 2;
        plan = wedges.map((w, i) => fitInside(w, slices[i], R));
        let nl = false, nr = false;
        plan.forEach((p, i) => {
          if (!p) { if (Math.cos(wedges[i].mid) >= 0) nr = true; else nl = true; }
        });
        if ((!nl || needL) && (!nr || needR)) break;
        needL = needL || nl;
        needR = needR || nr;
      }
      const cy = R + 26;
      const H = Math.round(2 * R + 52);

      const sv = sk('svg', { viewBox: `0 0 ${W} ${H}`, class: 'pie-svg' }, sec);
      const gSlices = sk('g', {}, sv);
      const gLead = sk('g', {}, sv);
      const gLabels = sk('g', {}, sv);
      const list = mk('div', 'pie-list', null, sec);

      const items = [];
      const outs = [];
      let selected = -1;
      const select = (i) => {
        selected = selected === i ? -1 : i;
        items.forEach((it, k) => {
          const on = k === selected;
          const tr = on ? `translate(${it.dx}px, ${it.dy}px)` : '';
          it.path.style.transform = tr;
          it.labels.forEach((l) => { l.style.transform = tr; });
          if (it.out) it.out.classList.toggle('on', on);
          if (it.lead) it.lead.classList.toggle('on', on);
          it.row.classList.toggle('on', on);
        });
      };

      slices.forEach((s, i) => {
        const w = wedges[i];
        const kwh = kwhOf(s);
        const tip = `${s.name} : ${kwh} kWh (${s.percent} %)`;
        const c = Math.cos(w.mid), sn = Math.sin(w.mid);

        let path;
        if (w.full) {
          path = sk('circle', { cx, cy, r: R, fill: s.color }, gSlices);
        } else {
          const x0 = cx + R * Math.cos(w.a0);
          const y0 = cy + R * Math.sin(w.a0);
          const x1 = cx + R * Math.cos(w.a1);
          const y1 = cy + R * Math.sin(w.a1);
          const large = w.a1 - w.a0 > Math.PI ? 1 : 0;
          path = sk('path', {
            d: `M${cx.toFixed(1)},${cy.toFixed(1)} L${x0.toFixed(1)},${y0.toFixed(1)} A${R.toFixed(1)},${R.toFixed(1)} 0 ${large} 1 ${x1.toFixed(1)},${y1.toFixed(1)} Z`,
            fill: s.color
          }, gSlices);
        }
        path.setAttribute('class', 'pie-slice');
        sk('title', {}, path).textContent = tip;

        // Étiquette dans la part (kWh + %) quand il y a la place
        const labels = [];
        const fit = plan[i];
        if (fit) {
          const fill = textOn(s.color);
          const b1 = cy + fit.y - fit.bh / 2 + 3 + 0.8 * fit.fs;
          const b2 = b1 + 0.2 * fit.fs + fit.fs2;
          const x = (cx + fit.x).toFixed(1);
          const t1 = sk('text', {
            x, y: b1.toFixed(1), 'text-anchor': 'middle', class: 'pie-lbl', fill, 'font-size': fit.fs
          }, gLabels);
          t1.appendChild(document.createTextNode(kwh));
          const u = sk('tspan', { class: 'u', 'font-size': (fit.fs * 0.72).toFixed(1), dx: 2 }, t1);
          u.appendChild(document.createTextNode('kWh'));
          const t2 = sk('text', {
            x, y: b2.toFixed(1), 'text-anchor': 'middle', class: 'pie-lbl p', fill, 'font-size': fit.fs2.toFixed(1)
          }, gLabels);
          t2.textContent = `${pct(s)} %`;
          labels.push(t1, t2);
        } else {
          outs.push({ i, s, c, sn, right: c >= 0, y: cy + (R + 8) * sn });
        }

        // Ligne du tableau (toutes les valeurs)
        const row = mk('div', 'pie-row', null, list);
        const sw = mk('i', null, null, row);
        sw.style.background = s.color;
        mk('span', 'nm', s.name, row);
        mk('span', 'kw', `${kwh} kWh`, row);
        mk('span', 'pc', `${pct(s)} %`, row);
        row.title = tip;

        items.push({
          path, labels, row, out: null, lead: null,
          dx: (c * 8).toFixed(1),
          dy: (sn * 8).toFixed(1)
        });
        path.addEventListener('click', () => select(i));
        row.addEventListener('click', () => select(i));
      });

      // Étiquettes extérieures, seulement pour les parts trop petites : une colonne de chaque
      // côté, décalées verticalement pour ne pas se chevaucher, reliées à leur part par un trait.
      // Si une colonne est trop chargée, on garde uniquement le kWh (le % reste dans le tableau).
      [false, true].forEach((right) => {
        const arr = outs.filter((o) => o.right === right).sort((a, b) => a.y - b.y);
        if (!arr.length) return;
        const two = arr.length * 27 <= H - 28;
        const gap = two ? 27 : 15;
        const ymin = two ? 16 : 10, ymax = H - (two ? 16 : 8);
        arr.forEach((o, k) => { o.ly = Math.max(o.y, k ? arr[k - 1].ly + gap : ymin); });
        for (let k = arr.length - 1; k >= 0; k--) {
          const lim = k === arr.length - 1 ? ymax : arr[k + 1].ly - gap;
          if (arr[k].ly > lim) arr[k].ly = lim;
        }
        const xcol = right ? cx + R + 12 : cx - R - 12;
        arr.forEach((o) => {
          const p0 = [cx + R * o.c, cy + R * o.sn];
          const p1 = [cx + (R + 8) * o.c, cy + (R + 8) * o.sn];
          const p2 = [xcol + (right ? -3 : 3), two ? o.ly - 4 : o.ly];
          const lead = sk('path', {
            d: `M${p0[0].toFixed(1)},${p0[1].toFixed(1)} L${p1[0].toFixed(1)},${p1[1].toFixed(1)} L${p2[0].toFixed(1)},${p2[1].toFixed(1)}`,
            class: 'pie-lead'
          }, gLead);
          const t = sk('text', {
            x: xcol.toFixed(1),
            y: (two ? o.ly - 1 : o.ly + 4.5).toFixed(1),
            'text-anchor': right ? 'start' : 'end',
            class: 'pie-out',
            'font-size': 13
          }, gLabels);
          t.appendChild(document.createTextNode(kwhOf(o.s)));
          if (two) {
            const p = sk('tspan', { class: 'p', x: xcol.toFixed(1), dy: 12.5, 'font-size': 11 }, t);
            p.appendChild(document.createTextNode(`${pct(o.s)} %`));
          }
          sk('title', {}, t).textContent = `${o.s.name} : ${kwhOf(o.s)} kWh (${o.s.percent} %)`;
          t.addEventListener('click', () => select(o.i));
          items[o.i].out = t;
          items[o.i].lead = lead;
        });
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
