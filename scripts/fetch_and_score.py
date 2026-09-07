"""
Hauptpipeline: Kursdaten laden, technische Indikatoren berechnen, Aktien pro
Sektor/Megatrend und Zeithorizont bewerten, Top-5-Listen erzeugen, vergangene
Signale gegen die Realitaet pruefen (Self-Correction) und Gewichte nachjustieren.

Wird von .github/workflows/update.yml automatisch alle 6 Stunden ausgefuehrt.
Kann auch lokal gestartet werden:  python scripts/fetch_and_score.py
"""

import copy
import json
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

HORIZONS = [1, 3, 5, 10, 15, 20, 25, 30]

DEFAULT_WEIGHTS = {
    "short": {"momentum": 0.30, "technical": 0.30, "trend": 0.20, "stability": 0.20},
    "medium": {"momentum": 0.30, "technical": 0.25, "trend": 0.25, "stability": 0.20},
    "long": {"momentum": 0.30, "technical": 0.15, "trend": 0.35, "stability": 0.20},
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


def rank_percentile(values):
    s = pd.Series(values)
    if s.nunique() <= 1:
        return [50.0] * len(values)
    return (s.rank(pct=True) * 100).tolist()


def score_category(metrics_by_ticker: dict, horizon: int, weights: dict):
    bucket = bucket_for_horizon(horizon)
    w = weights[bucket]
    tickers = list(metrics_by_ticker.keys())
    if not tickers:
        return []

    def momentum_value(m):
        if bucket == "short":
            return 0.7 * m["ret5"] + 0.3 * m["ret20"]
        if bucket == "medium":
            return 0.4 * m["ret5"] + 0.6 * m["ret20"]
        return 0.3 * m["ret20"] + 0.4 * m["ret60"] + 0.3 * m["ret120"]

    def technical_value(m):
        rsi_score = max(0.0, min(100.0, 100 - abs(m["rsi14"] - 60) * 1.5))
        if m["macd"] > m["macd_signal"] and m["macd_hist"] > m["macd_hist_prev"]:
            macd_score = 100
        elif m["macd"] > m["macd_signal"]:
            macd_score = 60
        else:
            macd_score = 20
        return 0.5 * rsi_score + 0.5 * macd_score

    def trend_value(m):
        s = 0
        s += 40 if m["price"] > m["sma20"] else 0
        s += 30 if m["price"] > m["sma50"] else 0
        s += 30 if m["price"] > m["sma200"] else 0
        return s

    def stability_value(m):
        return max(0.0, 100 - m["vol20"])

    momentum_pct = rank_percentile([momentum_value(metrics_by_ticker[t]) for t in tickers])
    technical_pct = rank_percentile([technical_value(metrics_by_ticker[t]) for t in tickers])
    trend_pct = rank_percentile([trend_value(metrics_by_ticker[t]) for t in tickers])
    stability_pct = rank_percentile([stability_value(metrics_by_ticker[t]) for t in tickers])

    results = []
    for i, t in enumerate(tickers):
        m = metrics_by_ticker[t]
        score = (w["momentum"] * momentum_pct[i] + w["technical"] * technical_pct[i]
                 + w["trend"] * trend_pct[i] + w["stability"] * stability_pct[i])
        macd_bull = m["macd"] > m["macd_signal"] and m["macd_hist"] > m["macd_hist_prev"]
        results.append({"ticker": t, "score": round(score, 1), "metrics": m, "macd_bull": macd_bull})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def build_reasoning(m: dict, macd_bull: bool, horizon: int) -> list:
    lines = []
    if m["ret20"] > 0:
        lines.append(f"Aufwärtstrend: {m['ret20']:+.1f}% in den letzten 20 Handelstagen.")
    else:
        lines.append(f"Konsolidierung: {m['ret20']:+.1f}% in den letzten 20 Handelstagen — mögliches antizyklisches Setup.")
    if m["rsi14"] > 70:
        lines.append(f"RSI(14) bei {m['rsi14']:.0f} — überkauft, kurzfristig erhöhtes Rückschlagsrisiko.")
    elif m["rsi14"] < 30:
        lines.append(f"RSI(14) bei {m['rsi14']:.0f} — überverkauft, mögliche technische Gegenbewegung.")
    else:
        lines.append(f"RSI(14) bei {m['rsi14']:.0f} — neutral bis bullisch, Spielraum nach oben vorhanden.")
    if macd_bull:
        lines.append("MACD-Linie notiert über der Signallinie und das Histogramm weitet sich aus (bullisches Momentum).")
    else:
        lines.append("MACD zeigt aktuell kein frisches Kaufsignal — Chartstruktur wird weiter beobachtet.")
    if m["price"] > m["sma50"] > m["sma200"]:
        lines.append("Kurs notiert über SMA50 und SMA200 — intakter mittelfristiger Aufwärtstrend.")
    elif m["price"] > m["sma20"]:
        lines.append("Kurs notiert über dem SMA20 — kurzfristiges Momentum vorhanden.")
    else:
        lines.append("Kurs unter wichtigen gleitenden Durchschnitten — eher antizyklische Chance.")
    lines.append(f"Annualisierte 20-Tage-Volatilität: {m['vol20']:.0f}%.")
    lines.append(f"Bewertung für Zeithorizont {horizon} Tag(e), gewichtet aus Momentum, Technik, Trend und Stabilität.")
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
            newly_evaluated.append({
                **sig, "exit_price": round(exit_price, 2),
                "realized_return_pct": round(realized, 2),
                "correct": bool(realized > 0.2),
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
            shift = 0.03
            w["momentum"] = max(0.10, w["momentum"] - shift)
            w["trend"] = min(0.60, w["trend"] + shift / 2)
            w["stability"] = min(0.60, w["stability"] + shift / 2)
            reason = f"Trefferquote {bucket}-Horizont niedrig ({hit:.0%}) -> Momentum-Gewicht gesenkt, Trend/Stabilität erhöht"
        elif hit > 0.62:
            shift = 0.03
            w["trend"] = max(0.10, w["trend"] - shift / 2)
            w["stability"] = max(0.10, w["stability"] - shift / 2)
            w["momentum"] = min(0.60, w["momentum"] + shift)
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
            ranked = score_category(cat_metrics, h, weights)[:5]
            stocks_out = []
            for idx, entry in enumerate(ranked):
                t, m = entry["ticker"], entry["metrics"]
                is_top_deal = (idx == 0 and entry["score"] >= 88 and 45 <= m["rsi14"] <= 72 and entry["macd_bull"])
                lev = leveraged.get(t, {"handelbar_hebel": False})
                stocks_out.append({
                    "ticker": t, "name": NAMES.get(t, t), "rank": idx + 1,
                    "score": entry["score"], "top_deal": is_top_deal,
                    "price": round(m["price"], 2), "rsi14": round(m["rsi14"], 1),
                    "macd_hist": round(m["macd_hist"], 3),
                    "sma20": round(m["sma20"], 2), "sma50": round(m["sma50"], 2), "sma200": round(m["sma200"], 2),
                    "ret5": round(m["ret5"], 2), "ret20": round(m["ret20"], 2), "ret60": round(m["ret60"], 2),
                    "vol20": round(m["vol20"], 1),
                    "reasoning": build_reasoning(m, entry["macd_bull"], h),
                    "trade_republic_hebel": lev,
                })
                key = (t, cat_key, h, today_iso)
                if key not in existing_keys:
                    backtest_state["open_signals"].append({
                        "ticker": t, "category": cat_key, "horizon_days": h,
                        "entry_date": today_iso, "entry_price": round(m["price"], 2),
                    })
                    existing_keys.add(key)
            cat_out["horizons"][str(h)] = stocks_out
        predictions["categories"][cat_key] = cat_out

    save_json(PREDICTIONS_PATH, predictions)
    save_json(BACKTEST_PATH, backtest_state)
    print(f"predictions.json und backtest.json geschrieben. "
          f"Trefferquote gesamt: {backtest_state['overall_hit_rate']}, "
          f"offene Signale: {len(backtest_state['open_signals'])}")


if __name__ == "__main__":
    main()
