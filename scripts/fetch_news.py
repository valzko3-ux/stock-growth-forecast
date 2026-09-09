"""
Holt aktuelle Schlagzeilen aus oeffentlichen, kostenlosen Finanz-RSS-Feeds
(MarketWatch, Nasdaq, Investing.com, Federal Reserve), taggt sie ueber eine
einfache Schluesselwort-Heuristik mit betroffenen Sektoren/Megatrends und
verknuepft sie mit den aktuell staerksten Long-Kandidaten ("Gewinner") sowie
volatilitaetsarmen Titeln aus demselben Sektor ("krisenfeste Werte") aus
data/predictions.json.

WICHTIG: Es findet keine Live-Ueberwachung von Politiker-/Trader-Tweets statt
(X-API kostenpflichtig, Scraping verletzt die Nutzungsbedingungen von X) --
siehe README, Abschnitt "Bekannte Grenzen". Die Sektor-Zuordnung hier ist eine
transparente Schluesselwort-Heuristik, keine redaktionelle Einzelfallpruefung.

Wird von .github/workflows/update.yml nach fetch_and_score.py ausgefuehrt,
damit predictions.json aktuell ist. Lokal:  python scripts/fetch_news.py
"""

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from universe import CATEGORIES

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PREDICTIONS_PATH = DATA_DIR / "predictions.json"
NEWS_PATH = DATA_DIR / "news.json"

FEEDS = [
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://www.nasdaq.com/feed/rssoutbound?category=Markets",
    "https://www.investing.com/rss/news_25.rss",
    "https://www.federalreserve.gov/feeds/press_all.xml",
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuantSignalsNewsBot/1.0"
NEWS_HORIZON = 5  # Tage, fuer die Gewinner/Defensiv-Zuordnung herangezogen wird
MAX_ITEMS = 8

SECTOR_KEYWORDS = {
    "technologie": ["tech stock", "software", "cloud comput", "iphone", "app store", "semiconductor", "chip maker", "chip stock", "big tech"],
    "gesundheit": ["fda approv", "drug trial", "vaccine", "biotech", "pharma", "health insurer", "medicare", "medicaid"],
    "finanzen": ["fed rate", "fed chair", "fomc", "monetary policy", "interest rate", "rate cut", "rate hike",
                 "ecb rate", "european central bank", "inflation data", "inflation report", "bank earnings",
                 "treasury yield", "recession fear"],
    "zyklischer_konsum": ["retail sales", "consumer spending", "housing starts", "auto sales", "e-commerce"],
    "basiskonsum": ["grocery", "food price", "consumer staples"],
    "industrie": ["manufacturing pmi", "factory output", "industrial production", "supply chain", "tariff", "trade war"],
    "energie": ["opec", "crude oil", "oil price", "natural gas price", "gas prices", "energy stock", "pipeline"],
    "versorger": ["power grid", "electricity price", "utility stock", "utilities sector"],
    "telekommunikation": ["telecom", "5g network", "broadband", "spectrum auction"],
    "grundstoffe": ["commodity price", "commodities", "copper price", "gold price", "mining stock", "metals price"],
    "immobilien": ["mortgage rate", "housing market", "real estate", "home sales"],
    "ki": ["artificial intelligence", "openai", "chatgpt", "ai model", "ai chip", "generative ai", "nvidia"],
    "cybersecurity": ["cyberattack", "ransomware", "data breach", "cybersecurity"],
    "e_mobility": ["electric vehicle", "ev sales", "ev maker", "battery plant", "charging network", " ev "],
}


def fetch_feed(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"  Feed nicht erreichbar ({url}): {exc}")
        return []
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        print(f"  Feed nicht parsebar ({url}): {exc}")
        return []

    items = []
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title, link, pub = None, None, None
        for child in node:
            ctag = child.tag.split("}")[-1]
            if ctag == "title" and not title:
                title = (child.text or "").strip()
            elif ctag == "link" and not link:
                link = (child.text or child.get("href") or "").strip()
            elif ctag in ("pubDate", "published", "updated") and not pub:
                pub = (child.text or "").strip()
        if title:
            items.append({"title": title, "link": link or "", "pub": pub or ""})
    return items


def match_categories(title: str):
    t = f" {title.lower()} "
    return [cat for cat, keywords in SECTOR_KEYWORDS.items() if any(kw in t for kw in keywords)]


def pick_stocks(predictions: dict, cat_key: str, horizon: int, direction=None, sort_by_low_vol=False, limit=3):
    cat = predictions.get("categories", {}).get(cat_key)
    if not cat:
        return []
    stocks = cat.get("horizons", {}).get(str(horizon), [])
    if direction:
        stocks = [s for s in stocks if s.get("direction") == direction]
    stocks = sorted(stocks, key=(lambda s: s.get("vol20", 999)) if sort_by_low_vol else (lambda s: s.get("score", 0)), reverse=not sort_by_low_vol)
    return [{"ticker": s["ticker"], "name": s["name"]} for s in stocks[:limit]]


def dedupe(items):
    out, seen = [], set()
    for it in items:
        if it["ticker"] not in seen:
            out.append(it)
            seen.add(it["ticker"])
    return out


def main():
    predictions = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8")) if PREDICTIONS_PATH.exists() else {}

    raw_items = []
    for url in FEEDS:
        raw_items.extend(fetch_feed(url))
    print(f"{len(raw_items)} Roh-Schlagzeilen von {len(FEEDS)} Feeds geladen.")

    seen_titles, pinned = set(), []
    for it in raw_items:
        norm = re.sub(r"\s+", " ", it["title"].lower()).strip()
        if not norm or norm in seen_titles:
            continue
        cats = match_categories(it["title"])
        if not cats:
            continue
        seen_titles.add(norm)

        winners, defensive = [], []
        for c in cats:
            winners.extend(pick_stocks(predictions, c, NEWS_HORIZON, direction="long", limit=3))
            defensive.extend(pick_stocks(predictions, c, NEWS_HORIZON, sort_by_low_vol=True, limit=2))

        pinned.append({
            "title": it["title"],
            "link": it["link"],
            "published": it["pub"],
            "categories": [CATEGORIES[c]["label"] for c in cats if c in CATEGORIES],
            "winners": dedupe(winners)[:4],
            "defensive": dedupe(defensive)[:3],
        })
        if len(pinned) >= MAX_ITEMS:
            break

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "horizon_used": NEWS_HORIZON,
        "items": pinned,
        "method_note": (
            "Schlagzeilen stammen aus öffentlichen RSS-Feeds (MarketWatch, Nasdaq, "
            "Investing.com, Federal Reserve). Die Sektor-Zuordnung sowie die Auswahl "
            "von 'Gewinnern' und 'krisenfesten Werten' basiert auf einer einfachen "
            "Schlüsselwort-Heuristik kombiniert mit den aktuellen, rein algorithmischen "
            "Sektor-Scores dieser App — keine redaktionelle oder fundamentale "
            "Einzelfallprüfung und keine Anlageberatung."
        ),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(pinned)} News-Items geschrieben nach {NEWS_PATH}")


if __name__ == "__main__":
    main()
