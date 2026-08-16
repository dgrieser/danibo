# Rechercheergebnisse

Ergebnisse konkreter Suchläufe mit `danibo.py`. Preise und Verfügbarkeit sind
Momentaufnahmen — vor einer Buchung auf danibo.dk gegenprüfen.

## Fanø, Herbst 2026

Suchauftrag: Unterkunft auf Fanø für 2 Erwachsene und 2 Kinder (8 und 11 Jahre),
Nichtraucher, möglichst ein Haus, Wunschzeitraum 19.10. – 1.11.2026.

Der Wunschzeitraum ist nicht buchbar: Danibo vermietet auf Fanø in dieser Saison
ausschließlich samstags bis samstags. Ausgewertet ist deshalb **Sa 17.10. →
Sa 31.10.2026** (14 Nächte) — gleiche Länge, zwei Tage früher. Die drei anderen
in Frage kommenden Sa–Sa-Varianten sind im Bericht mit Objektzahl und Preis
gegenübergestellt, und bei jedem Objekt stehen die Preise der übrigen Wochen.

| Datei | Inhalt |
| --- | --- |
| `fanoe-2026-herbst.html` | Bericht: alle 53 Treffer nach Preis sortiert, mit Fotos, Ausstattung, Lage, Nichtraucher-Status und Links. Filter für Häuser / Nichtraucher / kinderfreundlich, Sortierung nach Preis, Fläche, Strandnähe und Bewertung. Eigenständige Datei, Bilder sind eingebettet. |
| `fanoe-2026-10-17_2026-10-31.json` | Rohdaten desselben Suchlaufs, inklusive Foto-URLs. |

Ergebnis: 53 buchbare Objekte, 30 Häuser und 23 Ferienwohnungen, 768 – 3.442 €
Gesamtpreis inklusive Endreinigung und Buchungsgebühr. 48 Objekte tragen das
Danibo-Merkmal „Nichtraucher“, „Rauchen erlaubt“ ist bei keinem gesetzt.

Reproduzierbar mit:

```sh
./danibo.py availability 5461 --from 2026-10-01 --to 2026-11-15
./danibo.py search --arrival 2026-10-17 --departure 2026-10-31 \
    --adults 2 --children 2 --sort price --with-photos --json
```

### Zwei Eigenheiten der Danibo-Daten

- Nicht jedes Ausstattungsmerkmal ist gepflegt. „Grill“, „Terrasse“ und
  „eingezäunt“ sind fast überall leer, obwohl die Beschreibungstexte sie nennen.
  Ein fehlendes Merkmal heißt also nicht zwingend „nicht vorhanden“.
- Zwei Golfstien-Objekte sind bei Danibo als `House` typisiert, tragen aber
  „lejl.“ (dänisch *lejlighed* = Wohnung) in der Adresse und heißen im
  Beschreibungstext Ferienwohnung. Im Bericht stehen sie als Wohnung.
