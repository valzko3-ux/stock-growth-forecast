# Reine pandas/numpy-Implementierung gaengiger technischer Indikatoren.
# Bewusst ohne externe TA-Bibliothek, um Abhaengigkeiten fuer den
# GitHub-Actions-Runner minimal zu halten.

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window, min_periods=max(2, window // 2)).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def pct_return(close: pd.Series, lookback: int) -> float:
    if len(close) <= lookback:
        return 0.0
    a, b = close.iloc[-1], close.iloc[-1 - lookback]
    if b == 0 or pd.isna(b) or pd.isna(a):
        return 0.0
    return float((a / b - 1) * 100)


def annualized_volatility(close: pd.Series, window: int = 20) -> float:
    rets = close.pct_change().dropna().tail(window)
    if len(rets) < 5:
        return 0.0
    return float(rets.std() * np.sqrt(252) * 100)
