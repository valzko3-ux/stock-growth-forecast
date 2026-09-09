(() => {
  "use strict";

  const HORIZONS = [1, 3, 5, 10, 15, 20, 25, 30];
  const MILESTONES = [10000, 20000, 50000, 100000];
  const PORTFOLIO_KEY = "quantSignalsPortfolioV1";

  const CATEGORY_ORDER = {
    sectors: ["technologie", "gesundheit", "finanzen", "zyklischer_konsum", "basiskonsum",
              "industrie", "energie", "versorger", "telekommunikation", "grundstoffe", "immobilien"],
    megatrends: ["ki", "cybersecurity", "e_mobility"],
  };
  const ALL_CATEGORY_KEYS = [...CATEGORY_ORDER.sectors, ...CATEGORY_ORDER.megatrends];

  const ICONS = {
    technologie: "💻", gesundheit: "🏥", finanzen: "💰", zyklischer_konsum: "🛍️",
    basiskonsum: "🛒", industrie: "🏭", energie: "⚡", versorger: "🔌",
    telekommunikation: "📡", grundstoffe: "⛏️", immobilien: "🏢",
    ki: "🤖", cybersecurity: "🛡️", e_mobility: "🔋",
  };

  let predictions = null;
  let backtest = null;
  let news = null;
  let horizonIndex = 2; // default -> HORIZONS[2] = 5 Tage
  const panelBodies = {}; // catKey -> element

  let portfolio = { startCapital: 0, trades: [] };
  let selectedDir = "LONG";
  let equityChart = null;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  function fmtPct(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toFixed(1)}%`;
  }

  function fmtEur(v) {
    const sign = v > 0 ? "+" : v < 0 ? "−" : "";
    return `${sign}€${Math.abs(v).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function pctColorClass(v) {
    if (v === null || v === undefined) return "text-slate-400";
    return v >= 0 ? "text-neongreen" : "text-neonred";
  }

  // ============================================================
  // Datenladen
  // ============================================================
  async function loadData() {
    const bust = `?v=${Date.now()}`;
    const [predRes, backRes, newsRes] = await Promise.all([
      fetch(`data/predictions.json${bust}`),
      fetch(`data/backtest.json${bust}`).catch(() => null),
      fetch(`data/news.json${bust}`).catch(() => null),
    ]);
    if (!predRes.ok) throw new Error("predictions.json konnte nicht geladen werden");
    predictions = await predRes.json();
    backtest = backRes && backRes.ok ? await backRes.json() : null;
    news = newsRes && newsRes.ok ? await newsRes.json() : null;
  }

  function currentStocksOf(catKey) {
    const catData = predictions.categories[catKey];
    return catData?.horizons?.[String(HORIZONS[horizonIndex])] || [];
  }

  // ============================================================
  // Header / Self-Correction
  // ============================================================
  function renderHeader() {
    const ts = predictions?.generated_at ? new Date(predictions.generated_at) : null;
    $("#lastUpdated").textContent = ts
      ? `Aktualisiert: ${ts.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} UTC`
      : "Keine Daten";

    if (backtest && typeof backtest.overall_hit_rate === "number") {
      $("#hitRateBadge").classList.remove("hidden");
      $("#hitRateValue").textContent = `${Math.round(backtest.overall_hit_rate * 100)}%`;
    }
  }

  function renderSelfCorrection() {
    const panel = $("#selfCorrectionPanel");
    const text = $("#selfCorrectionText");
    if (!backtest) return;
    panel.classList.remove("hidden");

    const n = backtest.total_evaluated || 0;
    const open = backtest.open_signals?.length ?? 0;
    let msg;
    if (n === 0) {
      msg = `Noch keine ausgewerteten Signale — das Modell sammelt gerade die ersten Datenpunkte ` +
            `(${open} offene Prognosen laufen aktuell). Die Trefferquote erscheint hier, sobald die ersten ` +
            `Zeithorizonte abgelaufen sind.`;
    } else {
      const rate = Math.round((backtest.overall_hit_rate ?? 0) * 100);
      msg = `Bisherige Trefferquote: <strong class="text-white">${rate}%</strong> bei ${n} ausgewerteten Signalen ` +
            `(${open} weitere laufen aktuell). `;
      const lastLog = backtest.weight_adjustments_log?.at(-1);
      if (lastLog) {
        msg += `Letzte Selbstkorrektur am ${lastLog.date}: ${lastLog.reason}.`;
      } else {
        msg += `Die Gewichtung von Momentum, Technik und Trend wurde bisher noch nicht angepasst ` +
               `(zu wenige ausgewertete Signale pro Zeithorizont-Bucket).`;
      }
    }
    text.innerHTML = msg;
  }

  function scoreColor(score) {
    if (score >= 80) return "#00ffa3";
    if (score >= 60) return "#5eb1ff";
    if (score >= 40) return "#ffb800";
    return "#ff3b5c";
  }

  // ============================================================
  // Stock-Card / Accordions
  // ============================================================
  function directionPill(direction) {
    return direction === "short"
      ? `<span class="dir-pill dir-short">SHORT</span>`
      : `<span class="dir-pill dir-long">LONG</span>`;
  }

  function stockCard(stock, catKey, opts = {}) {
    const hebel = stock.trade_republic_hebel || {};
    const isTop = stock.top_deal;
    const showCategory = !!opts.showCategory;
    const catLabel = opts.categoryLabel || predictions.categories[catKey]?.label || "";
    const catAttr = opts.searchMode ? "__search__" : catKey;
    return `
      <div class="stock-card ${isTop ? "top-deal-card" : ""} ${opts.highConviction ? "hc-card" : ""} p-3 flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0">
            ${opts.showRank ? `<span class="text-slate-600 font-mono text-xs w-4 shrink-0">#${stock.rank}</span>` : ""}
            <div class="min-w-0">
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="font-mono font-bold text-white text-sm">${stock.ticker}</span>
                ${directionPill(stock.direction)}
                ${isTop ? `<span class="badge-topdeal">🔥 TOP DEAL</span>` : ""}
                ${opts.highConviction ? `<span class="badge-hc">💎 HIGH CONVICTION</span>` : ""}
              </div>
              <div class="text-[11px] text-slate-500 truncate">${stock.name}${showCategory ? ` · ${catLabel}` : ""}</div>
            </div>
          </div>
          <button class="info-btn shrink-0 w-7 h-7 rounded-full border border-border text-slate-400 hover:text-cyberlight hover:border-cyber/50 flex items-center justify-center text-xs"
                  data-ticker="${stock.ticker}" data-cat="${catAttr}" aria-label="Begründung anzeigen">ⓘ</button>
        </div>

        <div class="flex items-center justify-between gap-2 text-xs">
          <div class="flex items-center gap-3">
            <span class="font-mono text-slate-300">${stock.price.toFixed(2)}</span>
            <span class="font-mono font-semibold ${stock.direction === "short" ? "text-neonred" : "text-neongreen"}">${fmtPct(stock.forecast_pct)} / ${stock.forecast_horizon_days}T</span>
            <span class="text-slate-500">RSI ${stock.rsi14.toFixed(0)}</span>
          </div>
          ${hebel.handelbar_hebel ? `<span class="badge-tr">TR: Hebelbar</span>` : ""}
        </div>

        <div class="flex items-center gap-2">
          <div class="score-bar-track flex-1">
            <div class="score-bar-fill" style="width:${stock.score}%; background:linear-gradient(90deg, ${scoreColor(stock.score)}88, ${scoreColor(stock.score)})"></div>
          </div>
          <span class="font-mono text-[11px] text-slate-400 w-8 text-right">${stock.score.toFixed(0)}</span>
        </div>
      </div>`;
  }

  function buildAccordionShell(container, catKey, catDef) {
    const item = document.createElement("div");
    item.className = "accordion-item";
    item.innerHTML = `
      <button class="accordion-header" data-cat="${catKey}">
        <span class="flex items-center gap-2 min-w-0">
          <span class="text-lg shrink-0">${ICONS[catKey] || "📊"}</span>
          <span class="min-w-0">
            <span class="block text-sm font-semibold text-white truncate">${catDef.label}</span>
            <span class="block text-[10px] text-slate-500 uppercase tracking-wider">Top 5 · ${catDef.type === "megatrend" ? "Megatrend" : "Sektor"}</span>
          </span>
        </span>
        <svg class="accordion-chevron shrink-0" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <div class="accordion-panel">
        <div class="px-3 pb-3 space-y-2" data-panel-body="${catKey}"></div>
      </div>`;
    container.appendChild(item);
    panelBodies[catKey] = item.querySelector(`[data-panel-body="${catKey}"]`);
    wireAccordionToggle(item);
  }

  function wireAccordionToggle(item) {
    const header = item.querySelector(".accordion-header");
    const panel = item.querySelector(".accordion-panel");
    header.addEventListener("click", () => {
      const isOpen = item.classList.toggle("is-open");
      panel.style.maxHeight = isOpen ? `${panel.scrollHeight}px` : "0px";
    });
  }

  function updatePanelContent(catKey) {
    const body = panelBodies[catKey];
    if (!body) return;
    const stocks = currentStocksOf(catKey);
    body.innerHTML = stocks.length
      ? stocks.map((s) => stockCard(s, catKey, { showRank: true })).join("")
      : `<p class="text-xs text-slate-500 py-2">Keine Daten für diesen Zeithorizont verfügbar.</p>`;

    const item = body.closest(".accordion-item");
    if (item.classList.contains("is-open")) {
      const panel = item.querySelector(".accordion-panel");
      panel.style.maxHeight = `${panel.scrollHeight}px`;
    }
  }

  function renderAllPanels() {
    Object.keys(panelBodies).forEach(updatePanelContent);
  }

  function buildAccordions() {
    const sectorContainer = $("#sectorAccordions");
    const megaContainer = $("#megatrendAccordions");
    CATEGORY_ORDER.sectors.forEach((key) => {
      const def = predictions.categories[key];
      if (def) buildAccordionShell(sectorContainer, key, def);
    });
    CATEGORY_ORDER.megatrends.forEach((key) => {
      const def = predictions.categories[key];
      if (def) buildAccordionShell(megaContainer, key, def);
    });
    renderAllPanels();
  }

  // ============================================================
  // High-Probability Deals (sektorübergreifend)
  // ============================================================
  function renderHighConviction() {
    const board = $("#highConvictionBoard");
    const all = [];
    ALL_CATEGORY_KEYS.forEach((catKey) => {
      currentStocksOf(catKey).forEach((s) => all.push({ ...s, __cat: catKey }));
    });
    all.sort((a, b) => b.score - a.score);
    const top = all.slice(0, 5).filter((s) => s.score >= 55);

    if (!top.length) {
      board.innerHTML = `<div class="bg-panel border border-border rounded-2xl p-4 text-xs text-slate-500">
        Aktuell keine Signale mit ausreichend hoher Konviktion für diesen Zeithorizont.</div>`;
      return;
    }
    board.innerHTML = top.map((s) => stockCard(s, s.__cat, { showCategory: true, highConviction: true })).join("");
  }

  // ============================================================
  // Sektor-Performance-Radar
  // ============================================================
  function renderSectorRadar() {
    const el = $("#sectorRadar");
    const rows = ALL_CATEGORY_KEYS.map((catKey) => {
      const stocks = currentStocksOf(catKey);
      const net = stocks.length
        ? stocks.reduce((sum, s) => sum + (s.direction === "short" ? -s.score : s.score), 0) / stocks.length
        : 0;
      return { catKey, label: predictions.categories[catKey]?.label || catKey, net };
    });
    rows.sort((a, b) => b.net - a.net);
    const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.net)));

    el.innerHTML = rows.map((r) => {
      const pct = Math.min(100, (Math.abs(r.net) / maxAbs) * 100);
      const positive = r.net >= 0;
      return `
        <div class="flex items-center gap-2 text-xs">
          <span class="w-32 shrink-0 truncate text-slate-400">${ICONS[r.catKey] || "📊"} ${r.label}</span>
          <div class="radar-track flex-1">
            <div class="radar-fill ${positive ? "radar-pos" : "radar-neg"}" style="width:${pct}%"></div>
          </div>
          <span class="font-mono w-12 text-right ${positive ? "text-neongreen" : "text-neonred"}">${r.net >= 0 ? "+" : ""}${r.net.toFixed(0)}</span>
        </div>`;
    }).join("");
  }

  // ============================================================
  // Pinned Impact News
  // ============================================================
  function chip(t) {
    return `<span class="news-chip">${t.ticker}</span>`;
  }

  function renderNews() {
    const body = $("#newsPanelBody");
    if (!news || !news.items || !news.items.length) {
      body.innerHTML = `<p class="text-xs text-slate-500 py-2">Aktuell keine sektorrelevanten Eilmeldungen erkannt.</p>`;
      return;
    }
    body.innerHTML = news.items.map((item) => `
      <div class="news-card">
        <a href="${item.link || "#"}" target="_blank" rel="noopener noreferrer" class="text-sm font-semibold text-white hover:text-cyberlight leading-snug block mb-1.5">${item.title}</a>
        <div class="flex flex-wrap gap-1 mb-2">
          ${item.categories.map((c) => `<span class="news-cat-badge">${c}</span>`).join("")}
        </div>
        ${item.winners?.length ? `
          <div class="text-[11px] text-slate-400 mb-1"><span class="text-neongreen font-semibold">📈 Profiteure:</span> ${item.winners.map(chip).join(" ")}</div>` : ""}
        ${item.defensive?.length ? `
          <div class="text-[11px] text-slate-400"><span class="text-cyberlight font-semibold">🛡️ Krisenfest:</span> ${item.defensive.map(chip).join(" ")}</div>` : ""}
      </div>`).join("") +
      `<p class="text-[10px] text-slate-600 pt-1">${news.method_note || ""}</p>`;
  }

  // ============================================================
  // Modal
  // ============================================================
  function openModal(ticker, catKey) {
    const stock = currentStocksOf(catKey).find((s) => s.ticker === ticker);
    if (!stock) return;
    showModal(stock, predictions.categories[catKey].label);
  }

  async function openModalFromSearch(ticker) {
    const data = await ensureUniverseLoaded();
    const entry = data?.tickers?.[ticker];
    if (!entry) return;
    const stock = entry.horizons[String(HORIZONS[horizonIndex])];
    if (!stock) return;
    showModal(stock, entry.categories.map((c) => c.label).join(" · "));
  }

  function showModal(stock, categoryLabel) {
    $("#modalTicker").textContent = stock.ticker;
    $("#modalName").textContent = `${stock.name} · ${categoryLabel}`;

    const hebel = stock.trade_republic_hebel || {};
    const reasoningHtml = (stock.reasoning || []).map((r) => `<div class="reasoning-item">${r}</div>`).join("");
    const dirWord = stock.direction === "short" ? "SHORT" : "LONG";
    const dirColor = stock.direction === "short" ? "text-neonred" : "text-neongreen";

    $("#modalBody").innerHTML = `
      <div class="forecast-banner ${stock.direction === "short" ? "forecast-short" : "forecast-long"}">
        <span class="${dirColor} font-bold">${dirWord}</span>-Prognose für ${stock.forecast_horizon_days} Tag(e):
        <span class="font-mono font-bold ${dirColor}">${fmtPct(stock.forecast_pct)}</span>
      </div>

      <div>
        <h4 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Signalstärke &amp; Begründung</h4>
        <div class="flex items-center gap-2 mb-2">
          <div class="score-bar-track flex-1"><div class="score-bar-fill" style="width:${stock.score}%; background:${scoreColor(stock.score)}"></div></div>
          <span class="font-mono text-sm text-white">${stock.score.toFixed(0)}/100</span>
        </div>
        <div class="space-y-1.5">${reasoningHtml}</div>
      </div>

      <div>
        <h4 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Technische Indikatoren</h4>
        <div class="indicator-row"><span class="text-slate-400">Kurs</span><span class="font-mono text-white">${stock.price.toFixed(2)}</span></div>
        <div class="indicator-row"><span class="text-slate-400">RSI (14)</span><span class="font-mono text-white">${stock.rsi14.toFixed(1)}</span></div>
        <div class="indicator-row"><span class="text-slate-400">MACD-Histogramm</span><span class="font-mono ${pctColorClass(stock.macd_hist)}">${stock.macd_hist.toFixed(3)}</span></div>
        <div class="indicator-row"><span class="text-slate-400">SMA 20 / 50 / 200</span><span class="font-mono text-white">${stock.sma20.toFixed(1)} / ${stock.sma50.toFixed(1)} / ${stock.sma200.toFixed(1)}</span></div>
        <div class="indicator-row"><span class="text-slate-400">Momentum 5T / 20T / 60T</span><span class="font-mono ${pctColorClass(stock.ret20)}">${fmtPct(stock.ret5)} / ${fmtPct(stock.ret20)} / ${fmtPct(stock.ret60)}</span></div>
        <div class="indicator-row"><span class="text-slate-400">Volatilität (ann., 20T)</span><span class="font-mono text-white">${stock.vol20.toFixed(0)}%</span></div>
      </div>

      <div>
        <h4 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Trade Republic &amp; Hebelprodukte</h4>
        ${hebel.handelbar_hebel ? `
          <div class="text-xs text-slate-300 space-y-1">
            <p>Typische Emittenten: <span class="text-cyberlight">${(hebel.issuers_typisch || []).join(", ")}</span></p>
            <p>Produkttypen: ${(hebel.produkttypen || []).join(", ")}</p>
            <p class="text-slate-500">Stand: ${hebel.stand || "—"} · Konfidenz: ${hebel.konfidenz || "—"}</p>
            <p class="text-slate-500 italic">${hebel.hinweis || ""}</p>
          </div>` : `<p class="text-xs text-slate-500">Keine Hebelprodukt-Angabe hinterlegt.</p>`}
      </div>

      <p class="text-[10px] text-slate-600 border-t border-border pt-3">
        Rein algorithmisch generiert, keine Anlageberatung. Die Prognose ist eine volatilitäts-skalierte
        Erwartungswert-Schätzung (Konviktion × annualisierte Volatilität × √Zeit), keine Kursziel-Garantie.
        Vergangene Kursbewegungen und Indikatoren sind kein verlässlicher Indikator für zukünftige Entwicklungen.
      </p>`;

    $("#modalBackdrop").classList.remove("hidden");
    $("#modalBackdrop").classList.add("flex");
  }

  function closeModal() {
    $("#modalBackdrop").classList.add("hidden");
    $("#modalBackdrop").classList.remove("flex");
  }

  // ============================================================
  // Tabs
  // ============================================================
  function switchTab(tab) {
    $$(".tab-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === tab));
    $("#tab-signals").classList.toggle("hidden", tab !== "signals");
    $("#tab-portfolio").classList.toggle("hidden", tab !== "portfolio");
    if (tab === "portfolio") renderChart(); // Chart braucht sichtbares Canvas für korrekte Größe
  }

  // ============================================================
  // Portfolio / Performance-Tracker
  // ============================================================
  function loadPortfolio() {
    try {
      const raw = localStorage.getItem(PORTFOLIO_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        portfolio = { startCapital: Number(parsed.startCapital) || 0, trades: Array.isArray(parsed.trades) ? parsed.trades : [] };
      }
    } catch (e) {
      console.warn("Portfolio konnte nicht geladen werden", e);
    }
  }

  function savePortfolio() {
    try {
      localStorage.setItem(PORTFOLIO_KEY, JSON.stringify(portfolio));
    } catch (e) {
      console.warn("Portfolio konnte nicht gespeichert werden", e);
    }
  }

  function populateTickerDropdown() {
    const select = $("#tradeTicker");
    if (!predictions) return;
    const seen = new Map();
    ALL_CATEGORY_KEYS.forEach((catKey) => {
      Object.values(predictions.categories[catKey]?.horizons || {}).forEach((list) => {
        list.forEach((s) => seen.set(s.ticker, s.name));
      });
    });
    const sorted = Array.from(seen.entries()).sort((a, b) => a[0].localeCompare(b[0]));
    select.innerHTML = `<option value="">— Aktie wählen —</option>` +
      sorted.map(([ticker, name]) => `<option value="${ticker}">${ticker} — ${name}</option>`).join("");
  }

  function totalPnl() {
    return portfolio.trades.reduce((sum, t) => sum + t.result, 0);
  }

  function totalCapital() {
    return portfolio.startCapital + totalPnl();
  }

  function renderTotals() {
    $("#totalCapitalValue").textContent = `€${totalCapital().toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    const pnl = totalPnl();
    const pnlEl = $("#totalPnlValue");
    pnlEl.textContent = fmtEur(pnl);
    pnlEl.className = `text-lg font-bold font-mono ${pnl > 0 ? "text-neongreen" : pnl < 0 ? "text-neonred" : "text-slate-400"}`;
  }

  function sortedTrades() {
    return [...portfolio.trades].sort((a, b) => a.id - b.id);
  }

  function renderChart() {
    const canvas = $("#equityChart");
    const hint = $("#chartEmptyHint");
    const trades = sortedTrades();
    if (!trades.length) {
      hint.classList.remove("hidden");
      canvas.classList.add("hidden");
      if (equityChart) { equityChart.destroy(); equityChart = null; }
      return;
    }
    hint.classList.add("hidden");
    canvas.classList.remove("hidden");

    let running = portfolio.startCapital;
    const labels = ["Start"];
    const values = [running];
    trades.forEach((t, i) => {
      running += t.result;
      labels.push(`#${i + 1}`);
      values.push(running);
    });

    if (equityChart) {
      equityChart.data.labels = labels;
      equityChart.data.datasets[0].data = values;
      equityChart.update();
      return;
    }
    equityChart = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Gesamtkapital (€)",
          data: values,
          borderColor: "#2f8fff",
          backgroundColor: "rgba(47,143,255,0.12)",
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointBackgroundColor: "#00ffa3",
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#64748b", font: { size: 10 } }, grid: { color: "#1f2330" } },
          y: { ticks: { color: "#64748b", font: { size: 10 } }, grid: { color: "#1f2330" } },
        },
      },
    });
  }

  function renderMilestones() {
    const total = totalCapital();
    const el = $("#milestoneList");
    el.innerHTML = MILESTONES.map((m) => {
      const reached = total >= m;
      const pct = Math.min(100, Math.max(0, (total / m) * 100));
      const remaining = Math.max(0, m - total);
      return `
        <div>
          <div class="flex items-center justify-between text-xs mb-1">
            <span class="text-slate-300 font-semibold">${m.toLocaleString("de-DE")} €</span>
            ${reached
              ? `<span class="text-neongreen font-semibold">Erreicht ✅</span>`
              : `<span class="text-slate-500 font-mono">Noch ${(100 - pct).toFixed(0)}% · ${fmtEur(remaining).replace("+", "")}</span>`}
          </div>
          <div class="milestone-track"><div class="milestone-fill" style="width:${pct}%"></div></div>
        </div>`;
    }).join("");
  }

  function renderTimeProjection() {
    const el = $("#timeProjectionText");
    const trades = sortedTrades();
    if (trades.length < 2) {
      el.textContent = "Trage mindestens 2 Trades ein, um eine Hochrechnung zu sehen.";
      return;
    }
    const firstDate = new Date(trades[0].date);
    const lastDate = new Date(trades[trades.length - 1].date);
    const daySpan = Math.max(1, (lastDate - firstDate) / 86400000);
    const avgPerDay = totalPnl() / daySpan;
    const avgPerTrade = totalPnl() / trades.length;

    if (avgPerDay <= 0) {
      el.innerHTML = `Ø Ergebnis pro Trade: <strong class="text-white">${fmtEur(avgPerTrade)}</strong>. ` +
        `Bei der aktuellen (nicht positiven) Performance lässt sich kein Erreichungszeitpunkt für die Meilensteine hochrechnen.`;
      return;
    }
    const total = totalCapital();
    const lines = MILESTONES.filter((m) => m > total).map((m) => {
      const days = (m - total) / avgPerDay;
      const text = days > 60 ? `${(days / 7).toFixed(1)} Wochen` : `${Math.ceil(days)} Tage`;
      return `<div>→ <strong class="text-white">${m.toLocaleString("de-DE")} €</strong>: noch ca. ${text}</div>`;
    });
    el.innerHTML = `Ø Ergebnis/Tag: <strong class="text-white">${fmtEur(avgPerDay)}</strong> (Ø ${fmtEur(avgPerTrade)}/Trade, ` +
      `basierend auf ${trades.length} Trades über ${daySpan.toFixed(0)} Tage).<div class="mt-2 space-y-0.5">` +
      (lines.length ? lines.join("") : `<div>Alle Meilensteine bereits erreicht ✅</div>`) + `</div>`;
  }

  function renderHistory() {
    const el = $("#tradeHistory");
    if (!portfolio.trades.length) {
      el.innerHTML = `<p class="text-xs text-slate-600 px-1">Keine Trades vorhanden.</p>`;
      return;
    }
    const rows = [...portfolio.trades].sort((a, b) => b.id - a.id);
    el.innerHTML = rows.map((t) => `
      <div class="trade-row">
        <div class="flex items-center gap-2 min-w-0">
          <span class="dir-pill ${t.direction === "SHORT" ? "dir-short" : "dir-long"}">${t.direction}</span>
          <span class="font-mono text-sm text-white truncate">${t.ticker}</span>
          <span class="text-[10px] text-slate-600">${new Date(t.date).toLocaleDateString("de-DE")}</span>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span class="font-mono text-sm font-semibold ${t.result >= 0 ? "text-neongreen" : "text-neonred"}">${fmtEur(t.result)}</span>
          <button class="delete-trade-btn" data-id="${t.id}" aria-label="Trade löschen">🗑</button>
        </div>
      </div>`).join("");
  }

  function renderPortfolioAll() {
    renderTotals();
    renderMilestones();
    renderTimeProjection();
    renderHistory();
    renderChart();
  }

  function bindPortfolioEvents() {
    $("#startCapitalInput").addEventListener("input", (e) => {
      portfolio.startCapital = Number(e.target.value) || 0;
      savePortfolio();
      renderPortfolioAll();
    });

    $$(".dir-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedDir = btn.dataset.dir;
        $$(".dir-toggle").forEach((b) => b.classList.toggle("is-active", b === btn));
      });
    });

    $("#tradeForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const ticker = $("#tradeTicker").value;
      const resultRaw = $("#tradeResult").value;
      if (!ticker || resultRaw === "") return;
      portfolio.trades.push({
        id: Date.now(),
        ticker,
        direction: selectedDir,
        result: Number(resultRaw),
        date: new Date().toISOString(),
      });
      savePortfolio();
      $("#tradeResult").value = "";
      $("#tradeTicker").value = "";
      renderPortfolioAll();
    });

    $("#tradeHistory").addEventListener("click", (e) => {
      const btn = e.target.closest(".delete-trade-btn");
      if (!btn) return;
      const id = Number(btn.dataset.id);
      portfolio.trades = portfolio.trades.filter((t) => t.id !== id);
      savePortfolio();
      renderPortfolioAll();
    });
  }

  // ============================================================
  // Aktien-Suche (komplettes Universum, nicht nur Top-5 je Sektor)
  // ============================================================
  let universeData = null;
  let lastSearchQuery = "";

  async function ensureUniverseLoaded() {
    if (universeData) return universeData;
    try {
      const res = await fetch(`data/universe.json?v=${Date.now()}`);
      if (!res.ok) throw new Error("universe.json nicht gefunden");
      universeData = await res.json();
    } catch (e) {
      console.error(e);
      universeData = { tickers: {} };
    }
    return universeData;
  }

  function renderSearchResults() {
    const box = $("#searchResults");
    const q = lastSearchQuery.trim().toLowerCase();
    if (!q) { box.classList.add("hidden"); box.innerHTML = ""; return; }
    box.classList.remove("hidden");
    if (!universeData) { box.innerHTML = `<p class="text-xs text-slate-500 py-2 px-1">Suche…</p>`; return; }

    const h = String(HORIZONS[horizonIndex]);
    const matches = Object.values(universeData.tickers || {})
      .filter((e) => e.ticker.toLowerCase().includes(q) || e.name.toLowerCase().includes(q))
      .sort((a, b) => a.ticker.localeCompare(b.ticker))
      .slice(0, 8);

    if (!matches.length) {
      box.innerHTML = `<div class="bg-panel border border-border rounded-2xl p-4 text-xs text-slate-500">
        Keine passende Aktie im überwachten Universum gefunden (nur Trade-Republic-hebelbare Titel aus den
        14 Sektoren/Megatrends oben).</div>`;
      return;
    }
    box.innerHTML = matches.map((e) => {
      const stock = e.horizons[h];
      if (!stock) return "";
      return stockCard(stock, null, {
        showCategory: true, searchMode: true,
        categoryLabel: e.categories.map((c) => c.label).join(" · "),
      });
    }).join("");
  }

  async function handleSearchInput(value) {
    lastSearchQuery = value;
    if (!value.trim()) { renderSearchResults(); return; }
    renderSearchResults();
    await ensureUniverseLoaded();
    renderSearchResults();
  }

  // ============================================================
  // Sonstige Events / Init
  // ============================================================
  function updateSliderFill() {
    const pct = (horizonIndex / (HORIZONS.length - 1)) * 100;
    $("#horizonSlider").style.setProperty("--fill", `${pct}%`);
  }

  function renderHorizonDependent() {
    renderAllPanels();
    renderHighConviction();
    renderSectorRadar();
    if (lastSearchQuery.trim()) renderSearchResults();
  }

  function bindEvents() {
    const slider = $("#horizonSlider");
    slider.addEventListener("input", (e) => {
      horizonIndex = Number(e.target.value);
      $("#horizonLabel").textContent = `${HORIZONS[horizonIndex]} Tag${HORIZONS[horizonIndex] === 1 ? "" : "e"}`;
      updateSliderFill();
      renderHorizonDependent();
    });

    document.body.addEventListener("click", (e) => {
      const btn = e.target.closest(".info-btn");
      if (!btn) return;
      if (btn.dataset.cat === "__search__") {
        openModalFromSearch(btn.dataset.ticker);
      } else {
        openModal(btn.dataset.ticker, btn.dataset.cat);
      }
    });

    $("#stockSearchInput").addEventListener("input", (e) => handleSearchInput(e.target.value));

    $("#modalClose").addEventListener("click", closeModal);
    $("#modalBackdrop").addEventListener("click", (e) => {
      if (e.target.id === "modalBackdrop") closeModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeModal();
    });

    $$(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    // Statischer News-Akkordeon (nicht via buildAccordionShell erzeugt)
    $$(".accordion-item").forEach((item) => {
      if (item.querySelector('[data-cat="__news"]')) wireAccordionToggle(item);
    });

    bindPortfolioEvents();
  }

  function showError(message) {
    $("#sectorAccordions").innerHTML = `
      <div class="bg-panel border border-neonred/30 rounded-2xl p-4 text-sm text-red-300">
        ⚠️ ${message}
      </div>`;
  }

  async function init() {
    bindEvents();
    updateSliderFill();
    loadPortfolio();
    $("#startCapitalInput").value = portfolio.startCapital || "";
    try {
      await loadData();
      renderHeader();
      buildAccordions();
      renderHighConviction();
      renderSectorRadar();
      renderNews();
      renderSelfCorrection();
      populateTickerDropdown();
    } catch (err) {
      console.error(err);
      showError("Daten konnten nicht geladen werden. Die automatische Aktualisierung läuft möglicherweise noch nicht (erster GitHub-Actions-Lauf ausstehend).");
    }
    renderPortfolioAll();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
