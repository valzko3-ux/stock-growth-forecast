"""
Hauptpipeline: Kursdaten laden, technische Indikatoren berechnen, Aktien pro
Sektor/Megatrend und Zeithorizont in RICHTUNG (Long oder Short) und STAERKE
bewerten, Top-5-Listen erzeugen, vergangene Signale gegen die Realitaet
pruefen (Self-Correction) und Gewichte nachjustieren.

Wird von .github/workflows/update.yml automatisch 2x taeglich (07:30 / 15:30
Europe/Berlin, siehe scripts/should_run.py) ausgefuehrt. Kann auch lokal
gestartet werden:  python scripts/fetch_and_score.py
"""

import copy
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from indicators import annualized_volatility, atr, macd, pct_return, rsi, sma
from universe import CATEGORIES, NAMES, all_tickers

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PREDICTIONS_PATH = DATA_DIR / "predictions.json"
BACKTEST_PATH = DATA_DIR / "backtest.json"
LEVERAGED_PATH = DATA_DIR / "leveraged_products.json"
UNIVERSE_PATH = DATA_DIR / "universe.json"

HORIZONS = [1, 3, 5, 10, 15, 20, 25, 30]

# Gewichte fuer die *Konviktion* (signiert: positiv = Long-Bias, negativ =
# Short-Bias). momentum = juengste Kursbewegung, technical = RSI-Tilt+MACD,
# trend = Kurs vs. gleitende Durchschnitte. Der Self-Correction-Mechanismus
# unten justiert diese Gewichte automatisch anhand der bisherigen Trefferquote.
DEFAULT_WEIGHTS = {
    "short": {"momentum": 0.45, "technical": 0.35, "trend": 0.20},
    "medium": {"momentum": 0.40, "technical": 0.30, "trend": 0.30},
    "long": {"momentum": 0.30, "technical": 0.20, "trend": 0.50},
}

BUCKET_HORIZONS = {"short": [1, 3], "medium": [5, 10], "long": [15, 20, 25, 30]}


def bucket_for_horizon(h: int) -> str:
    if h <= 3:
        return "short"
    if h <= 10:
        return "medium"
    return "long"


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return copy.deepcopy(default)
    return copy.deepcopy(default)


def save_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def default_backtest_state():
    return {
        "last_updated": None,
        "overall_hit_rate": None,
        "total_evaluated": 0,
        "per_category": {},
        "weights": copy.deepcopy(DEFAULT_WEIGHTS),
        "weight_adjustments_log": [],
        "open_signals": [],
        "evaluated_history": [],
    }


def download_history(tickers):
    print(f"Lade Kursdaten fuer {len(tickers)} Ticker (2 Jahre, taeglich) ...")
    data = yf.download(
        tickers, period="2y", interval="1d", group_by="ticker",
        auto_adjust=True, threads=True, progress=False,
    )
    return data


def extract_frame(raw, ticker: str, n_tickers: int):
    try:
        df = raw.copy() if n_tickers == 1 else raw[ticker].copy()
    except Exception:
        return None
    if "Close" not in df.columns:
        return None
    df = df.dropna(subset=["Close"])
    return df if len(df) >= 30 else None


def compute_metrics(df: pd.DataFrame) -> dict:
    close, high, low = df["Close"], df["High"], df["Low"]
    macd_line, signal_line, hist = macd(close)
    sma200_window = min(200, max(20, len(close) - 1))
    m = {
        "price": float(close.iloc[-1]),
        "rsi14": float(rsi(close).iloc[-1]),
        "macd": float(macd_line.iloc[-1]),
        "macd_signal": float(signal_line.iloc[-1]),
        "macd_hist": float(hist.iloc[-1]),
        "macd_hist_prev": float(hist.iloc[-2]) if len(hist) > 1 else 0.0,
        "sma20": float(sma(close, 20).iloc[-1]),
        "sma50": float(sma(close, 50).iloc[-1]),
        "sma200": float(sma(close, sma200_window).iloc[-1]),
        "atr14": float(atr(high, low, close).iloc[-1]),
        "ret5": pct_return(close, 5),
        "ret20": pct_return(close, 20),
        "ret60": pct_return(close, 60),
        "ret120": pct_return(close, 120),
        "vol20": annualized_volatility(close, 20),
    }
    return m


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def macd_state(m: dict) -> str:
    if m["macd"] > m["macd_signal"] and m["macd_hist"] > m["macd_hist_prev"]:
        return "bull"
    if m["macd"] < m["macd_signal"] and m["macd_hist"] < m["macd_hist_prev"]:
        return "bear"
    if m["macd"] > m["macd_signal"]:
        return "bull_weak"
    if m["macd"] < m["macd_signal"]:
        return "bear_weak"
    return "neutral"


def momentum_signed(m: dict, bucket: str) -> float:
    """Gewichtete juengste Kursrendite in Prozent (Rohwert, kein Score)."""
    if bucket == "short":
        return 0.7 * m["ret5"] + 0.3 * m["ret20"]
    if bucket == "medium":
        return 0.4 * m["ret5"] + 0.6 * m["ret20"]
    return 0.3 * m["ret20"] + 0.4 * m["ret60"] + 0.3 * m["ret120"]


def technical_signed(m: dict) -> float:
    """RSI-Mean-Reversion-Tilt + MACD-Richtung -> Wert in [-100, 100]."""
    rsi_tilt = clamp(-(m["rsi14"] - 50) / 50 * 60, -60, 60)
    state = macd_state(m)
    macd_component = {"bull": 100, "bull_weak": 40, "neutral": 0, "bear_weak": -40, "bear": -100}[state]
    return 0.45 * rsi_tilt + 0.55 * macd_component


def trend_signed(m: dict) -> float:
    """Kurs vs. SMA20/50/200 als gestapeltes Trendsignal -> Wert in [-100, 100]."""
    s = 0
    s += 1 if m["price"] > m["sma20"] else -1
    s += 1 if m["price"] > m["sma50"] else -1
    s += 1 if m["price"] > m["sma200"] else -1
    return (s / 3.0) * 100


def stability_factor(m: dict) -> float:
    """Hohe Volatilitaet daempft die Konviktion, niedrige verstaerkt sie leicht."""
    return clamp(1.3 - m["vol20"] / 100.0, 0.55, 1.15)


def conviction_score(m: dict, horizon: int, weights: dict) -> float:
    """Signierter Konviktions-Score in [-100, 100]. Positiv = Long-Bias,
    negativ = Short-Bias. Betrag = Signalstaerke."""
    bucket = bucket_for_horizon(horizon)
    w = weights[bucket]
    total_w = w["momentum"] + w["technical"] + w["trend"]
    mom_norm = math.tanh(momentum_signed(m, bucket) / 15.0) * 100
    raw = (w["momentum"] * mom_norm + w["technical"] * technical_signed(m)
           + w["trend"] * trend_signed(m)) / total_w
    return clamp(raw * stability_factor(m), -100, 100)


def forecast_pct(m: dict, horizon_days: int, conviction: float) -> float:
    """Volatilitaets-skalierte Erwartungswert-Schaetzung fuer den gewaehlten
    Zeithorizont. Richtung & Konfidenz kommen aus `conviction` (-100..100),
    die Groessenordnung aus der annualisierten 20-Tage-Volatilitaet skaliert
    mit Wurzel(Zeit) (Standard-Diffusionsannahme). Explizit KEINE
    Kursziel-Garantie -- rein algorithmische Schaetzung, siehe Disclaimer."""
    daily_vol = m["vol20"] / (252 ** 0.5) / 100.0
    horizon_move = daily_vol * math.sqrt(horizon_days) * 100.0
    pct = (conviction / 100.0) * horizon_move * 0.85
    cap = 2.0 + horizon_days * 0.8
    return round(clamp(pct, -cap, cap), 1)


def build_reasoning(m: dict, direction: str, horizon: int) -> list:
    lines = []
    if direction == "long":
        if m["ret20"] > 0:
            lines.append(f"Aufwärtstrend: {m['ret20']:+.1f}% in den letzten 20 Handelstagen.")
        else:
            lines.append(f"Kurzfristige Schwäche ({m['ret20']:+.1f}% / 20T), übrige Faktoren sprechen aber für eine Gegenbewegung nach oben.")
        if m["rsi14"] > 70:
            lines.append(f"RSI(14) bei {m['rsi14']:.0f} — überkauft, kurzfristig erhöhtes Rückschlagsrisiko trotz Long-Signal.")
        elif m["rsi14"] < 35:
            lines.append(f"RSI(14) bei {m['rsi14']:.0f} — überverkauft, technische Gegenbewegung nach oben wahrscheinlich.")
        else:
            lines.append(f"RSI(14) bei {m['rsi14']:.0f} — neutral bis bullisch, Spielraum nach oben vorhanden.")
        state = macd_state(m)
        if state in ("bull", "bull_weak"):
            lines.append("MACD-Linie notiert über der Signallinie — bullisches Momentum.")
        else:
            lines.append("MACD noch nicht eindeutig bullisch — Einstieg mit erhöhter Vorsicht.")
        if m["price"] > m["sma50"] > m["sma200"]:
            lines.append("Kurs notiert über SMA50 und SMA200 — intakter mittelfristiger Aufwärtstrend (Widerstand: bisheriges Hoch).")
        elif m["price"] > m["sma20"]:
            lines.append("Kurs notiert über dem SMA20 — kurzfristiges Momentum vorhanden, SMA50 als nächste Hürde.")
        else:
            lines.append("Kurs unter wichtigen gleitenden Durchschnitten — eher antizyklische, riskantere Chance.")
    else:
        if m["ret20"] < 0:
            lines.append(f"Abwärtstrend: {m['ret20']:+.1f}% in den letzten 20 Handelstagen.")
        else:
            lines.append(f"Trotz kurzfristiger Stärke ({m['ret20']:+.1f}% / 20T) deuten die übrigen Faktoren auf eine Abwärtsbewegung hin.")
        if m["rsi14"] > 65:
            lines.append(f"RSI(14) bei {m['rsi14']:.0f} — überkauft, erhöhtes Risiko einer technischen Korrektur nach unten.")
        elif m["rsi14"] < 30:
            lines.append(f"RSI(14) bei {m['rsi14']:.0f} — bereits überverkauft, Short-Setup mit erhöhtem Gegenbewegungsrisiko.")
        else:
            lines.append(f"RSI(14) bei {m['rsi14']:.0f} — neutral bis bearisch.")
        state = macd_state(m)
        if state in ("bear", "bear_weak"):
            lines.append("MACD-Linie notiert unter der Signallinie — bearisches Momentum.")
        else:
            lines.append("MACD noch nicht eindeutig bearisch — Short-Einstieg mit erhöhter Vorsicht.")
        if m["price"] < m["sma50"] < m["sma200"]:
            lines.append("Kurs notiert unter SMA50 und SMA200 — intakter mittelfristiger Abwärtstrend (Unterstützung: bisheriges Tief).")
        elif m["price"] < m["sma20"]:
            lines.append("Kurs notiert unter dem SMA20 — kurzfristige Schwäche, SMA50 als nächste Unterstützung.")
        else:
            lines.append("Kurs über wichtigen gleitenden Durchschnitten — Short-Idee ist antizyklisch und riskanter.")

    lines.append(f"Annualisierte 20-Tage-Volatilität: {m['vol20']:.0f}% (fließt in die Prognosegröße ein).")
    lines.append(f"Konviktion & Prognose gewichtet aus Momentum, RSI/MACD und Trend für einen Zeithorizont von {horizon} Tag(en).")
    return lines


def update_backtest(state: dict, current_prices: dict) -> dict:
    today = date.today()
    still_open, newly_evaluated = [], []
    for sig in state["open_signals"]:
        maturity = date.fromisoformat(sig["entry_date"]) + timedelta(days=sig["horizon_days"])
        if today >= maturity:
            exit_price = current_prices.get(sig["ticker"])
            if exit_price is None:
                still_open.append(sig)
                continue
            realized = (exit_price / sig["entry_price"] - 1) * 100
            direction = sig.get("direction", "long")
            correct = (realized > 0.2) if direction == "long" else (realized < -0.2)
            newly_evaluated.append({
                **sig, "exit_price": round(exit_price, 2),
                "realized_return_pct": round(realized, 2),
                "correct": bool(correct),
                "evaluated_date": today.isoformat(),
            })
        else:
            still_open.append(sig)

    state["open_signals"] = still_open[-10000:]
    state["evaluated_history"] = (state.get("evaluated_history", []) + newly_evaluated)[-2000:]

    hist = state["evaluated_history"]
    state["overall_hit_rate"] = round(sum(1 for h in hist if h["correct"]) / len(hist), 3) if hist else None
    state["total_evaluated"] = len(hist)

    per_cat = {}
    for h in hist:
        c = per_cat.setdefault(h["category"], {"n": 0, "correct": 0})
        c["n"] += 1
        c["correct"] += 1 if h["correct"] else 0
    state["per_category"] = {c: {"n": v["n"], "hit_rate": round(v["correct"] / v["n"], 3)} for c, v in per_cat.items()}

    weights = state.get("weights") or copy.deepcopy(DEFAULT_WEIGHTS)
    log = state.get("weight_adjustments_log", [])
    for bucket, horizons in BUCKET_HORIZONS.items():
        recent = [h for h in hist if h["horizon_days"] in horizons][-40:]
        if len(recent) < 10:
            continue
        hit = sum(1 for h in recent if h["correct"]) / len(recent)
        w = weights[bucket]
        reason = None
        if hit < 0.45:
            shift = 0.04
            w["momentum"] = max(0.10, w["momentum"] - shift)
            w["trend"] = min(0.65, w["trend"] + shift)
            reason = f"Trefferquote {bucket}-Horizont niedrig ({hit:.0%}) -> Momentum-Gewicht gesenkt, Trend-Gewicht erhöht"
        elif hit > 0.62:
            shift = 0.04
            w["trend"] = max(0.10, w["trend"] - shift)
            w["momentum"] = min(0.65, w["momentum"] + shift)
            reason = f"Trefferquote {bucket}-Horizont hoch ({hit:.0%}) -> Momentum-Gewicht erhöht"
        if reason:
            total = sum(w.values())
            for k in w:
                w[k] = round(w[k] / total, 3)
            log.append({"date": today.isoformat(), "bucket": bucket, "hit_rate": round(hit, 3),
                        "reason": reason, "new_weights": dict(w)})

    state["weights"] = weights
    state["weight_adjustments_log"] = log[-300:]
    state["last_updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return state


def rank_stocks(metrics_by_ticker: dict, horizon: int, weights: dict):
    out = []
    for t, m in metrics_by_ticker.items():
        conv = conviction_score(m, horizon, weights)
        out.append({"ticker": t, "conviction": conv, "metrics": m})
    out.sort(key=lambda x: abs(x["conviction"]), reverse=True)
    return out


def is_top_deal(conv: float, m: dict, direction: str) -> bool:
    if abs(conv) < 88:
        return False
    state = macd_state(m)
    if direction == "long":
        return 45 <= m["rsi14"] <= 72 and state in ("bull", "bull_weak")
    return 28 <= m["rsi14"] <= 60 and state in ("bear", "bear_weak")


def build_stock_entry(t: str, m: dict, horizon: int, weights: dict, leveraged: dict, rank=None):
    """Baut das JSON-Objekt einer Aktie fuer einen Zeithorizont. Wird sowohl
    fuer die Top-5-Listen je Kategorie als auch fuer das komplette
    Such-Universum (data/universe.json) verwendet, damit beide Ansichten
    exakt dieselbe Bewertungslogik nutzen."""
    conv = conviction_score(m, horizon, weights)
    direction = "long" if conv >= 0 else "short"
    fpct = forecast_pct(m, horizon, conv)
    lev = leveraged.get(t, {"handelbar_hebel": False})
    entry = {
        "ticker": t, "name": NAMES.get(t, t),
        "score": round(abs(conv), 1), "direction": direction,
        "forecast_pct": fpct, "forecast_horizon_days": horizon,
        "top_deal": is_top_deal(conv, m, direction),
        "price": round(m["price"], 2), "rsi14": round(m["rsi14"], 1),
        "macd_hist": round(m["macd_hist"], 3),
        "sma20": round(m["sma20"], 2), "sma50": round(m["sma50"], 2), "sma200": round(m["sma200"], 2),
        "ret5": round(m["ret5"], 2), "ret20": round(m["ret20"], 2), "ret60": round(m["ret60"], 2),
        "vol20": round(m["vol20"], 1),
        "reasoning": build_reasoning(m, direction, horizon),
        "trade_republic_hebel": lev,
    }
    if rank is not None:
        entry["rank"] = rank
        entry["top_deal"] = rank == 1 and entry["top_deal"]
    return entry, conv


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tickers = all_tickers()
    raw = download_history(tickers)

    metrics_by_ticker, current_price = {}, {}
    for t in tickers:
        df = extract_frame(raw, t, len(tickers))
        if df is None:
            continue
        try:
            m = compute_metrics(df)
        except Exception as exc:
            print(f"  Überspringe {t}: {exc}")
            continue
        metrics_by_ticker[t] = m
        current_price[t] = m["price"]

    print(f"Erfolgreich verarbeitet: {len(metrics_by_ticker)}/{len(tickers)} Ticker")

    backtest_state = update_backtest(load_json(BACKTEST_PATH, default_backtest_state()), current_price)
    weights = backtest_state["weights"]
    leveraged = load_json(LEVERAGED_PATH, {})

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    predictions = {"generated_at": generated_at, "horizons": HORIZONS, "categories": {}}
    today_iso = date.today().isoformat()
    existing_keys = {(s["ticker"], s["category"], s["horizon_days"], s["entry_date"]) for s in backtest_state["open_signals"]}

    for cat_key, cat_def in CATEGORIES.items():
        cat_metrics = {t: metrics_by_ticker[t] for t in cat_def["tickers"] if t in metrics_by_ticker}
        cat_out = {"label": cat_def["label"], "type": cat_def["type"], "horizons": {}}
        for h in HORIZONS:
            ranked = rank_stocks(cat_metrics, h, weights)[:5]
            stocks_out = []
            for idx, ranked_entry in enumerate(ranked):
                t, m = ranked_entry["ticker"], ranked_entry["metrics"]
                stock_entry, conv = build_stock_entry(t, m, h, weights, leveraged, rank=idx + 1)
                stocks_out.append(stock_entry)
                direction = stock_entry["direction"]
                key = (t, cat_key, h, today_iso)
                if key not in existing_keys:
                    backtest_state["open_signals"].append({
                        "ticker": t, "category": cat_key, "horizon_days": h,
                        "entry_date": today_iso, "entry_price": round(m["price"], 2),
                        "direction": direction,
                    })
                    existing_keys.add(key)
            cat_out["horizons"][str(h)] = stocks_out
        predictions["categories"][cat_key] = cat_out

    save_json(PREDICTIONS_PATH, predictions)
    save_json(BACKTEST_PATH, backtest_state)
    print(f"predictions.json und backtest.json geschrieben. "
          f"Trefferquote gesamt: {backtest_state['overall_hit_rate']}, "
          f"offene Signale: {len(backtest_state['open_signals'])}")

    # -------- Such-Universum: ALLE ueberwachten Ticker, nicht nur Top-5 --------
    ticker_categories = {}
    for cat_key, cat_def in CATEGORIES.items():
        for t in cat_def["tickers"]:
            ticker_categories.setdefault(t, []).append({"key": cat_key, "label": cat_def["label"]})

    universe_out = {"generated_at": generated_at, "horizons": HORIZONS, "tickers": {}}
    for t, m in metrics_by_ticker.items():
        horizons_out = {}
        for h in HORIZONS:
            entry, _ = build_stock_entry(t, m, h, weights, leveraged)
            horizons_out[str(h)] = entry
        universe_out["tickers"][t] = {
            "ticker": t, "name": NAMES.get(t, t),
            "categories": ticker_categories.get(t, []),
            "horizons": horizons_out,
        }
    save_json(UNIVERSE_PATH, universe_out)
    print(f"universe.json geschrieben ({len(universe_out['tickers'])} Ticker, für die Suchfunktion).")


if __name__ == "__main__":
    main()
