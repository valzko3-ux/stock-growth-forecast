# 📈 QUANT SIGNALS — Aktien-Wachstumsprognosen

Mobile-first Web-App mit algorithmischen Wachstumsprognosen für 14 Sektoren &
Megatrends, ausgerichtet auf über **Trade Republic (Lang & Schwarz Exchange)**
handelbare Aktien. Läuft komplett kostenlos auf **GitHub Pages** und
aktualisiert sich selbstständig über **GitHub Actions**.

**Live:** `https://<DEIN-GITHUB-NAME>.github.io/stock-growth-forecast/` (Link
ist aktiv, sobald GitHub Pages aktiviert ist — siehe unten).

---

## Wie es funktioniert

```
scripts/fetch_and_score.py  (läuft alle 6h via GitHub Actions)
        │
        ├─ lädt 2 Jahre Kursdaten für ~240 Aktien (yfinance)
        ├─ berechnet RSI, MACD, SMA20/50/200, Momentum, Volatilität
        ├─ bewertet jede Aktie pro Sektor & pro Zeithorizont (1–30 Tage)
        ├─ prüft fällige Prognosen der Vergangenheit gegen echte Kurse
        │  und justiert die Gewichtung automatisch nach (Self-Correction)
        └─ schreibt data/predictions.json + data/backtest.json
                    │
                    └─ index.html / app.js liest diese JSON-Dateien
                       und rendert die Oberfläche (kein Server nötig)
```

Es gibt **keinen Backend-Server** — GitHub Pages liefert nur statische
Dateien. Die "Automatisierung" passiert dadurch, dass GitHub Actions die
JSON-Dateien periodisch neu berechnet und ins Repository committet.

### Selbstlern-Modell (Self-Correction)

Jede Top-5-Empfehlung wird mit Einstiegskurs und Datum gespeichert
(`data/backtest.json`, Feld `open_signals`). Sobald der jeweilige
Zeithorizont abgelaufen ist, vergleicht das Skript den damaligen Kurs mit dem
aktuellen Kurs, wertet die Prognose als richtig (> +0,2 %) oder falsch, und
passt bei ausreichender Datenbasis (≥10 ausgewertete Signale je
Horizont-Gruppe) die Gewichtung von Momentum / Technik / Trend / Stabilität
automatisch an. Alle Anpassungen inkl. Begründung stehen in
`weight_adjustments_log`.

---

## Bekannte Grenzen (bitte lesen)

Ein paar Punkte, bei denen die App bewusst **nicht** das technisch
Unmögliche oder rechtlich Riskante vorgibt:

- **Kein Live-Scan von X/Twitter-Politikern.** Die X-API ist kostenpflichtig,
  Scraping verletzt deren Nutzungsbedingungen. Aktuell fließt daher **kein**
  Politiker-/Trader-Sentiment in die Bewertung ein — nur technische
  Indikatoren. Eine spätere, saubere Erweiterung wäre der Anschluss an
  offizielle US-Kongress-Handelsoffenlegungen (kostenlos, legal).
- **Hebelprodukt-Verfügbarkeit ist nicht live verifiziert.**
  `data/leveraged_products.json` ist eine kuratierte, manuell erzeugte Liste
  mit Datumsstempel (`scripts/seed_leveraged.py`) — keine Live-Abfrage bei
  HSBC/SG/UBS/Vontobel/Citi. Vor jedem Handel unbedingt die tatsächliche
  Verfügbarkeit beim Emittenten bzw. bei Trade Republic prüfen.
- **Aktien-Universum ist kuratiert, nicht live gegen Trade Republic
  abgeglichen** (`scripts/universe.py`, ca. 240 liquide US-/EU-Titel).
  Grundsätzlich sollten alle enthaltenen Titel über die LS Exchange handelbar
  sein, eine Garantie gibt es aber nicht.
- **Keine Anlageberatung.** Alles ist rein algorithmisch aus historischen
  Kursdaten abgeleitet (siehe Disclaimer in der App).

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
   Source: **Deploy from a branch** → Branch: **main**, Ordner **/ (root)**
   → Save. Nach 1–2 Minuten ist die Seite live unter
   `https://<DEIN-GITHUB-NAME>.github.io/stock-growth-forecast/`.

3. **Workflow-Schreibrechte sicherstellen** (nötig, damit der Automatik-Job
   die neuen Daten zurück ins Repo committen darf):
   Repository → **Settings → Actions → General** → Abschnitt "Workflow
   permissions" → **Read and write permissions** auswählen → Save.

4. **Ersten Lauf manuell anstoßen** (optional, sonst startet er automatisch
   zur nächsten geraden 6h-Marke):
   Repository → **Actions** → Workflow "Update stock forecasts" →
   **Run workflow**.

Das war's — ab jetzt aktualisiert sich die Seite automatisch 4× täglich ganz
ohne dein Zutun.

---

## Lokale Entwicklung

```bash
cd scripts
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python seed_leveraged.py        # einmalig, erzeugt data/leveraged_products.json
python fetch_and_score.py       # erzeugt data/predictions.json + backtest.json

cd ..
python -m http.server 8000      # Seite lokal unter http://localhost:8000 ansehen
```

## Erweitern

- **Weitere Aktien/Sektoren:** `scripts/universe.py` — `CATEGORIES`-Dict
  erweitern, Anzeigename in `NAMES` ergänzen.
- **Hebelprodukt-Liste pflegen:** `data/leveraged_products.json` manuell
  bearbeiten oder `python scripts/seed_leveraged.py` erneut laufen lassen
  (überschreibt die ganze Datei mit dem Standard-Eintrag für alle Ticker).
- **Scoring-Gewichtung/-Logik:** `scripts/fetch_and_score.py`,
  Funktionen `score_category` und `DEFAULT_WEIGHTS`.

---

## ⚠️ Haftungsausschluss

Alle Inhalte dieser Anwendung werden vollautomatisch und rein algorithmisch
erzeugt. Es handelt sich **nicht** um eine Anlageberatung, Finanzanalyse oder
Kauf-/Verkaufsempfehlung. Der Handel mit Aktien und insbesondere mit
Hebelprodukten ist mit erheblichen Risiken bis zum Totalverlust des
eingesetzten Kapitals verbunden. Historische Trefferquoten sind kein
Indikator für zukünftige Ergebnisse.

## Lizenz

MIT
