# Rechercheergebnisse

Ergebnisse konkreter Suchläufe mit `danibo.py`. Preise und Verfügbarkeit sind
Momentaufnahmen — vor einer Buchung auf danibo.dk gegenprüfen.

Die Berichte werden als GitHub Pages veröffentlicht:
**<https://dgrieser.github.io/danibo/>**

## Fanø, Herbst 2026

Suchauftrag: Unterkunft auf Fanø für 2 Erwachsene und 2 Kinder (8 und 11 Jahre),
Nichtraucher, möglichst ein Haus, Wunschzeitraum 19.10. – 1.11.2026.

Der Wunschzeitraum ist nicht buchbar: Danibo vermietet auf Fanø in dieser Saison
ausschließlich samstags bis samstags. Es gibt vier Samstag-zu-Samstag-Varianten,
die dafür in Frage kommen — jede hat einen eigenen vollständigen Bericht, und
bei jedem Objekt stehen seine Preise in den jeweils anderen Zeiträumen.

| Zeitraum | Nächte | Objekte | ab | Abdeckung |
| --- | --- | --- | --- | --- |
| Sa 17.10. – Sa 31.10. | 14 | 53 | 768 € | ohne 1.11. |
| Sa 17.10. – Sa 07.11. | 21 | 39 | 1.093 € | **vollständig** |
| Sa 24.10. – Sa 31.10. | 7 | 115 | 380 € | ohne 19.–23.10. und 1.11. |
| Sa 24.10. – Sa 07.11. | 14 | 81 | 705 € | ohne 19.–23.10. |

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `fanoe-<anreise>_<abreise>.html` | Ein Bericht je Zeitraum: alle Treffer nach Preis sortiert, mit Fotos, Ausstattung, Lage und Nichtraucher-Status. Filter für Häuser / Nichtraucher / Pool & Aktivitätsraum, Sortierung nach Preis, Fläche, Strandnähe und Bewertung. |
| `data/<anreise>_<abreise>.json` | Rohdaten je Zeitraum, inklusive Beschreibungstexten und Preisen der anderen Zeiträume. |
| `assets/photos/` | Fotos, geteilt von allen Berichten — die Zeiträume überlappen stark, deshalb liegt jedes Bild nur einmal hier. |
| `reports.json` | Manifest, aus dem die Pages-Übersicht gebaut wird. **Generiert** — nicht von Hand ändern. |

## Neu erzeugen

```sh
# 1. Daten holen (ein Suchlauf je Zeitraum, Fotos werden geteilt)
python3 tools/fetch_report_data.py 2026-10-17:2026-10-31 2026-10-17:2026-11-07 \
    2026-10-24:2026-10-31 2026-10-24:2026-11-07

# 2. Berichte und Manifest bauen
python3 tools/build_report.py

# 3. Pages-Site bauen und lokal ansehen
python3 tools/build_site.py && python3 -m http.server -d _site
```

Schritt 1 ist der einzige, der ins Netz geht; `danibo.py` cacht Antworten, ein
zweiter Lauf ist also billig. Schritt 2 und 3 arbeiten rein lokal.

Ein neuer Zeitraum braucht nur einen weiteren `anreise:abreise`-Parameter in
Schritt 1 — Bericht, Manifest und Übersicht ergeben sich daraus. `build_site.py`
bricht ab, wenn eine HTML-Datei hier liegt, die nicht im Manifest steht, oder
umgekehrt.

## Zwei Eigenheiten der Danibo-Daten

- Nicht jedes Ausstattungsmerkmal ist gepflegt. „Grill“, „Terrasse“ und
  „eingezäunt“ sind fast überall leer, obwohl die Beschreibungstexte sie nennen.
  Ein fehlendes Merkmal heißt also nicht zwingend „nicht vorhanden“.
- Einzelne Golfstien-Objekte sind bei Danibo als `House` typisiert, tragen aber
  „lejl.“ (dänisch *lejlighed* = Wohnung) in der Adresse und heißen im
  Beschreibungstext Ferienwohnung. In den Berichten stehen sie als Wohnung.
