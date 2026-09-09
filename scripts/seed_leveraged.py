"""
Einmaliges Skript zur Erzeugung von data/leveraged_products.json.

WICHTIG: Dies ist KEINE Live-Verifizierung. Es gibt keine kostenlose API, die
pro Aktie garantiert bestaetigt, ob HSBC/SG/UBS/Vontobel/Citi aktuell ein
Hebelprodukt (Turbo/Optionsschein/Zertifikat) im Angebot haben. Diese Datei
markiert lediglich, fuer welche (liquiden, bekannten) Basiswerte Emittenten
erfahrungsgemaess Hebelprodukte anbieten - mit Datumsstempel und Hinweis.

Bitte in unregelmaessigen Abstaenden manuell pruefen/aktualisieren, z.B. über
die Produktsuchen von hsbc-zertifikate.de, sg-zertifikate.de, keyinvest-de.ubs.com,
vontobel-zertifikate.de oder citifirst.com.
"""

import json
from datetime import date
from pathlib import Path

from universe import all_tickers

STANDARD_ISSUERS = ["HSBC", "Société Générale", "UBS", "Vontobel", "Citi"]

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "leveraged_products.json"


def main():
    today = date.today().isoformat()
    out = {}
    for t in all_tickers():
        out[t] = {
            "handelbar_hebel": True,
            "issuers_typisch": STANDARD_ISSUERS,
            "produkttypen": ["Turbo/Knock-Out (Call & Put)", "Optionsschein (Call & Put)", "Faktor-Zertifikat (Long & Short)"],
            "konfidenz": "mittel",
            "stand": today,
            "hinweis": ("Basierend auf allgemeiner Markterfahrung für diesen liquiden, "
                        "bekannten Basiswert. Für Long- wie Short-Positionen existieren bei "
                        "diesen Emittenten in der Regel sowohl Call- als auch Put-Varianten. "
                        "Keine Live-Verifizierung — bitte vor Handel Verfügbarkeit, WKN und "
                        "Knock-Out-Schwelle direkt bei Trade Republic bzw. beim Emittenten prüfen."),
        }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(out)} Einträge geschrieben nach {OUT_PATH}")


if __name__ == "__main__":
    main()
