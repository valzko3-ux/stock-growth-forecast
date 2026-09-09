# 📈 QUANT SIGNALS — Long/Short-Prognosen für Trade Republic

Mobile-first Web-App mit algorithmischen **Long- und Short-Signalen** für 14
Sektoren & Megatrends plus freier Aktien-Suche über das komplette überwachte
Universum, ausgerichtet auf über **Trade Republic (Lang & Schwarz Exchange)**
handelbare, hebelbare Aktien. Läuft komplett kostenlos auf **GitHub Pages**
und aktualisiert sich 2× täglich selbstständig über **GitHub Actions**.

**Live:** https://valzko3-ux.github.io/stock-growth-forecast/

---

## Features

- **14 einklappbare Sektor-/Megatrend-Listen** (Top 5 je Kategorie), Slider für
  den Prognose-Zeithorizont (1–30 Tage), alles standardmäßig eingeklappt.
- **Long UND Short** — jede Aktie wird individuell in die wahrscheinlichere
  Richtung eingeordnet (nicht nur "Kaufen"-Listen).
- **🔥 Top Deal** — Badge für die mit Abstand überzeugendsten Einzelsignale.
- **💎 High-Probability Deals** — sektorübergreifendes Board der stärksten
  Signale aller 14 Kategorien für den gewählten Zeithorizont.
- **🔥 Sektor-Performance des Tages** — Radar-Widget mit der relativen
  technischen Stärke/Schwäche jedes Sektors.
- **📌 Pinned Impact News** — echte Schlagzeilen aus öffentlichen RSS-Feeds,
  per Schlüsselwort-Heuristik mit betroffenen Sektoren, "Gewinnern" und
  "krisenfesten Werten" verknüpft.
- **🔍 Aktien-Suche** — durchsucht das komplette überwachte Universum
  (~240 Titel, nicht nur die Top-5-Listen) nach Ticker/Name und liefert
  dieselbe Long/Short-Einschätzung samt Begründung.
- **Info-Modal je Aktie** mit RSI/MACD/SMA, Momentum, Volatilität und
  einer Klartext-Begründung der Richtung.
- **💼 Portfolio-Tracker** (eigener Tab, Daten nur in `localStorage` des
  Browsers): Startkapital, Trade-Eingabe (Aktie/Richtung/Ergebnis in €),
  Vermögensverlauf als Chart, Meilenstein-Fortschritt (10k/20k/50k/100k) und
  eine Hochrechnung, wann diese bei aktueller Performance erreicht werden.
- **🧠 Selbstlern-Modell** — vergangene Signale werden gegen echte Kurse
  geprüft, die Trefferquote angezeigt und die Gewichtung automatisch justiert.
- Persistenter Disclaimer (Footer + Bottom-Bar).

---

## Wie es funktioniert

```
scripts/fetch_and_score.py   (läuft 2×/Tag: 07:30 & 15:30 Europe/Berlin)
        │
        ├─ lädt 2 Jahre Kursdaten für ~240 Aktien (yfinance)
        ├─ berechnet RSI, MACD, SMA20/50/200, Momentum, Volatilität
        ├─ berechnet je Aktie einen signierten Konviktions-Score (-100..+100)
        │  -> Vorzeichen = Richtung (Long/Short), Betrag = Signalstärke
        ├─ leitet daraus eine volatilitäts-skalierte %-Prognose für den
        │  exakt gewählten Zeithorizont ab (Formel siehe unten)
        ├─ prüft fällige Prognosen der Vergangenheit gegen echte Kurse
        │  und justiert die Gewichtung automatisch nach (Self-Correction)
        └─ schreibt data/predictions.json, data/backtest.json, data/universe.json

scripts/fetch_news.py        (läuft direkt danach, selber Workflow-Lauf)
        └─ lädt RSS-Schlagzeilen, taggt Sektoren per Keyword-Heuristik,
           verknüpft mit den aktuellen Top-Signalen -> data/news.json

                    │
                    └─ index.html / app.js liest diese JSON-Dateien
                       und rendert die Oberfläche (kein Server nötig)
```

Es gibt **keinen Backend-Server** — GitHub Pages liefert nur statische
Dateien. Die "Automatisierung" passiert dadurch, dass GitHub Actions die
JSON-Dateien periodisch neu berechnet und ins Repository committet.

### Wie Richtung & Prognose-% berechnet werden

Für jede Aktie/jeden Horizont wird ein **signierter Konviktions-Score**
(-100 bis +100) aus drei Komponenten gebildet, deren Gewichtung sich pro
Zeithorizont-Bucket (kurz/mittel/lang) selbstständig anpasst (siehe
Self-Correction):

- **Momentum** — jüngste Kursrendite (5T/20T/60T, je nach Horizont)
- **Technik** — RSI-Mean-Reversion-Tilt + MACD-Richtung
- **Trend** — Kurs vs. SMA20/SMA50/SMA200

Das Vorzeichen ergibt die Richtung (**Long** bei positivem, **Short** bei
negativem Score), der Betrag die angezeigte Signalstärke (0–100). Die
konkrete **%-Prognose** ist eine volatilitäts-skalierte Erwartungswert-
Schätzung: `Konviktion × annualisierte 20-Tage-Volatilität × √Zeithorizont ×
0,85`, gedeckelt auf einen mit dem Horizont wachsenden Maximalwert. Das ist
eine transparente, rein algorithmische Formel — **keine Kursziel-Garantie**.

### Selbstlern-Modell (Self-Correction)

Jede Top-5-Empfehlung wird mit Einstiegskurs, Richtung und Datum gespeichert
(`data/backtest.json`, Feld `open_signals`). Sobald der jeweilige
Zeithorizont abgelaufen ist, vergleicht das Skript den damaligen Kurs mit dem
aktuellen Kurs, wertet die Prognose als richtig (Long: > +0,2 %, Short:
< −0,2 %) oder falsch, und passt bei ausreichender Datenbasis (≥10
ausgewertete Signale je Horizont-Gruppe) die Gewichtung von Momentum/Technik/
Trend automatisch an. Alle Anpassungen inkl. Begründung stehen in
`weight_adjustments_log`.

### Zeitplan (DST-sicher)

Cron kennt keine Sommerzeit. Damit die Pipeline wirklich exakt um **07:30**
und **15:30 Uhr Europe/Berlin** läuft (nicht nur im Winter oder nur im
Sommer), feuert der GitHub-Actions-Cron in zwei breiten UTC-Fenstern alle
10 Minuten; `scripts/should_run.py` lässt den eigentlichen Job aber nur genau
zur Zielzeit durch (echte Zeitzonen-Berechnung via `zoneinfo`). Ein manueller
Trigger (`workflow_dispatch`) läuft immer sofort.

---

## Bekannte Grenzen (bitte lesen)

Ein paar Punkte, bei denen die App bewusst **nicht** das technisch
Unmögliche oder rechtlich Riskante vorgibt:

- **Kein Live-Scan von X/Twitter-Politikern/Tradern/Krypto-Whales.** Die
  X-API ist kostenpflichtig, automatisiertes Scraping verletzt deren
  Nutzungsbedingungen. Es fließt daher **kein** Politiker-/Trader-Sentiment
  in die Bewertung ein — nur technische Indikatoren und öffentliche
  RSS-Nachrichten. Eine spätere, saubere Erweiterung wäre der Anschluss an
  offizielle US-Kongress-Handelsoffenlegungen (kostenlos, legal, z. B. über
  die Daten der US-STOCK-Act-Meldepflicht).
- **Pinned Impact News sind eine Heuristik, keine Redaktion.** Die
  Sektor-Zuordnung sowie "Gewinner"/"krisenfeste Werte" basieren auf
  Schlüsselwort-Matching (`scripts/fetch_news.py`, `SECTOR_KEYWORDS`) plus den
  aktuellen App-eigenen Scores — keine fundamentale Einzelfallprüfung.
- **Hebelprodukt-Verfügbarkeit ist nicht live verifiziert.**
  `data/leveraged_products.json` ist eine kuratierte, manuell erzeugte Liste
  mit Datumsstempel (`scripts/seed_leveraged.py`) — keine Live-Abfrage bei
  HSBC/SG/UBS/Vontobel/Citi. Vor jedem Handel unbedingt die tatsächliche
  Verfügbarkeit, WKN und Knock-Out-Schwelle beim Emittenten bzw. bei Trade
  Republic prüfen.
- **Aktien-Universum ist kuratiert, nicht live gegen Trade Republic
  abgeglichen** (`scripts/universe.py`, ca. 240 liquide US-/EU-Titel). Auch
  die Suchfunktion durchsucht nur dieses kuratierte Universum, nicht den
  gesamten Markt. Grundsätzlich sollten alle enthaltenen Titel über die LS
  Exchange handelbar sein, eine Garantie gibt es aber nicht.
- **Die %-Prognose ist eine algorithmische Schätzung, kein Kursziel** (siehe
  Formel oben) — sie kann falsch liegen, auch bei hoher angezeigter
  Signalstärke.
- **Keine Anlageberatung.** Alles ist rein algorithmisch aus historischen
  Kursdaten und öffentlichen Nachrichtenfeeds abgeleitet (siehe Disclaimer
  in der App).

---

## Einrichtung von Grund auf (falls du das Repo neu aufsetzen willst)

1. **Repository erstellen** (falls nicht schon geschehen) und diesen Ordner
   hochladen:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<DEIN-GITHUB-NAME>/stock-growth-forecast.git
   git push -u origin main
   ```

2. **GitHub Pages aktivieren:**
   Repository → **Settings → Pages** → unter "Build and deployment" →
   Source: **Deploy from a branch** → Branch: **main** (bzw. **master**),
   Ordner **/ (root)** → Save. Nach 1–2 Minuten ist die Seite live unter
   `https://<DEIN-GITHUB-NAME>.github.io/stock-growth-forecast/`.

3. **Workflow-Schreibrechte sicherstellen** (nötig, damit der Automatik-Job
   die neuen Daten zurück ins Repo committen darf):
   Repository → **Settings → Actions → General** → Abschnitt "Workflow
   permissions" → **Read and write permissions** auswählen → Save.

4. **Ersten Lauf manuell anstoßen** (optional, sonst startet er automatisch
   zur nächsten 07:30/15:30-Europe/Berlin-Marke):
   Repository → **Actions** → Workflow "Update stock forecasts" →
   **Run workflow**.

Das war's — ab jetzt aktualisiert sich die Seite automatisch 2× täglich ganz
ohne dein Zutun.

---

## Lokale Entwicklung

```bash
cd scripts
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python seed_leveraged.py        # einmalig, erzeugt data/leveraged_products.json
python fetch_and_score.py       # erzeugt predictions.json + backtest.json + universe.json
python fetch_news.py            # erzeugt data/news.json (braucht predictions.json)

cd ..
python -m http.server 8000      # Seite lokal unter http://localhost:8000 ansehen
```

## Erweitern

- **Weitere Aktien/Sektoren:** `scripts/universe.py` — `CATEGORIES`-Dict
  erweitern, Anzeigename in `NAMES` ergänzen.
- **Hebelprodukt-Liste pflegen:** `data/leveraged_products.json` manuell
  bearbeiten oder `python scripts/seed_leveraged.py` erneut laufen lassen
  (überschreibt die ganze Datei mit dem Standard-Eintrag für alle Ticker).
- **Scoring-Gewichtung/-Logik:** `scripts/fetch_and_score.py` —
  `conviction_score`, `forecast_pct`, `DEFAULT_WEIGHTS`.
- **News-Quellen/Keywords:** `scripts/fetch_news.py` — `FEEDS`,
  `SECTOR_KEYWORDS`.

---

## ⚠️ Haftungsausschluss

Alle Inhalte dieser Anwendung — inklusive Long/Short-Richtung, %-Prognosen,
Scores und "Top Deal"-Signale — werden vollautomatisch und rein algorithmisch
erzeugt. Es handelt sich **nicht** um eine Anlageberatung, Finanzanalyse oder
Kauf-/Verkaufsempfehlung. Der Handel mit Aktien und insbesondere mit
Hebelprodukten ist mit erheblichen Risiken bis zum Totalverlust des
eingesetzten Kapitals verbunden. Historische Trefferquoten sind kein
Indikator für zukünftige Ergebnisse.

## Lizenz

MIT
