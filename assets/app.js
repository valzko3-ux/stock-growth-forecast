(() => {
  "use strict";

  const HORIZONS = [1, 3, 5, 10, 15, 20, 25, 30];

  const CATEGORY_ORDER = {
    sectors: ["technologie", "gesundheit", "finanzen", "zyklischer_konsum", "basiskonsum",
              "industrie", "energie", "versorger", "telekommunikation", "grundstoffe", "immobilien"],
    megatrends: ["ki", "cybersecurity", "e_mobility"],
  };

  const ICONS = {
    technologie: "💻", gesundheit: "🏥", finanzen: "💰", zyklischer_konsum: "🛍️",
    basiskonsum: "🛒", industrie: "🏭", energie: "⚡", versorger: "🔌",
    telekommunikation: "📡", grundstoffe: "⛏️", immobilien: "🏢",
    ki: "🤖", cybersecurity: "🛡️", e_mobility: "🔋",
  };

  let predictions = null;
  let backtest = null;
  let horizonIndex = 2; // default -> HORIZONS[2] = 5 Tage
  const panelBodies = {}; // catKey -> element

  const $ = (sel) => document.querySelector(sel);

  function fmtPct(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toFixed(1)}%`;
  }

  function pctColorClass(v) {
    if (v === null || v === undefined) return "text-slate-400";
    return v >= 0 ? "text-neongreen" : "text-neonred";
  }

  function relevantMomentum(stock, horizonDays) {
    if (horizonDays <= 3) return { label: "5T", value: stock.ret5 };
    if (horizonDays <= 10) return { label: "20T", value: stock.ret20 };
    return { label: "60T", value: stock.ret60 };
  }

  async function loadData() {
    const bust = `?v=${Date.now()}`;
    const [predRes, backRes] = await Promise.all([
      fetch(`data/predictions.json${bust}`),
      fetch(`data/backtest.json${bust}`).catch(() => null),
    ]);
    if (!predRes.ok) throw new Error("predictions.json konnte nicht geladen werden");
    predictions = await predRes.json();
    backtest = backRes && backRes.ok ? await backRes.json() : null;
  }

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
        msg += `Die Gewichtung von Momentum, Technik, Trend und Stabilität wurde bisher noch nicht angepasst ` +
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

  function stockCard(stock, catKey) {
    const mom = relevantMomentum(stock, HORIZONS[horizonIndex]);
    const hebel = stock.trade_republic_hebel || {};
    const isTop = stock.top_deal;
    return `
      <div class="stock-card ${isTop ? "top-deal-card" : ""} p-3 flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <span class="text-slate-600 font-mono text-xs w-4 shrink-0">#${stock.rank}</span>
            <div class="min-w-0">
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="font-mono font-bold text-white text-sm">${stock.ticker}</span>
                ${isTop ? `<span class="badge-topdeal">🔥 TOP DEAL</span>` : ""}
              </div>
              <div class="text-[11px] text-slate-500 truncate">${stock.name}</div>
            </div>
          </div>
          <button class="info-btn shrink-0 w-7 h-7 rounded-full border border-border text-slate-400 hover:text-cyberlight hover:border-cyber/50 flex items-center justify-center text-xs"
                  data-ticker="${stock.ticker}" data-cat="${catKey}" aria-label="Begründung anzeigen">ⓘ</button>
        </div>

        <div class="flex items-center justify-between gap-2 text-xs">
          <div class="flex items-center gap-3">
            <span class="font-mono text-slate-300">${stock.price.toFixed(2)}</span>
            <span class="font-mono ${pctColorClass(mom.value)}">${mom.label}: ${fmtPct(mom.value)}</span>
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
    const catData = predictions.categories[catKey];
    const stocks = catData?.horizons?.[String(HORIZONS[horizonIndex])] || [];
    body.innerHTML = stocks.length
      ? stocks.map((s) => stockCard(s, catKey)).join("")
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

  function openModal(ticker, catKey) {
    const catData = predictions.categories[catKey];
    const stocks = catData?.horizons?.[String(HORIZONS[horizonIndex])] || [];
    const stock = stocks.find((s) => s.ticker === ticker);
    if (!stock) return;

    $("#modalTicker").textContent = stock.ticker;
    $("#modalName").textContent = `${stock.name} · ${catData.label}`;

    const hebel = stock.trade_republic_hebel || {};
    const reasoningHtml = (stock.reasoning || []).map((r) => `<div class="reasoning-item">${r}</div>`).join("");

    $("#modalBody").innerHTML = `
      <div>
        <h4 class="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">Score &amp; Begründung</h4>
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
        Rein algorithmisch generiert, keine Anlageberatung. Vergangene Kursbewegungen und Indikatoren sind kein
        verlässlicher Indikator für zukünftige Entwicklungen.
      </p>`;

    $("#modalBackdrop").classList.remove("hidden");
    $("#modalBackdrop").classList.add("flex");
  }

  function closeModal() {
    $("#modalBackdrop").classList.add("hidden");
    $("#modalBackdrop").classList.remove("flex");
  }

  function updateSliderFill() {
    const pct = (horizonIndex / (HORIZONS.length - 1)) * 100;
    $("#horizonSlider").style.setProperty("--fill", `${pct}%`);
  }

  function bindEvents() {
    const slider = $("#horizonSlider");
    slider.addEventListener("input", (e) => {
      horizonIndex = Number(e.target.value);
      $("#horizonLabel").textContent = `${HORIZONS[horizonIndex]} Tag${HORIZONS[horizonIndex] === 1 ? "" : "e"}`;
      updateSliderFill();
      renderAllPanels();
    });

    document.body.addEventListener("click", (e) => {
      const btn = e.target.closest(".info-btn");
      if (btn) openModal(btn.dataset.ticker, btn.dataset.cat);
    });

    $("#modalClose").addEventListener("click", closeModal);
    $("#modalBackdrop").addEventListener("click", (e) => {
      if (e.target.id === "modalBackdrop") closeModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeModal();
    });
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
    try {
      await loadData();
      renderHeader();
      buildAccordions();
      renderSelfCorrection();
    } catch (err) {
      console.error(err);
      showError("Daten konnten nicht geladen werden. Die automatische Aktualisierung läuft möglicherweise noch nicht (erster GitHub-Actions-Lauf ausstehend).");
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
