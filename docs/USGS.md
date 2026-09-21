# USGS – belegte Fakten (Abschnitt E, Punkt 3)

Quelle der Belege: echte Antwort `significant_week.geojson` vom 19.09.2026 13:08:51 UTC
(`tests/fixtures/usgs/real_2026-09-19_significant_week.json`) und die ComCat-Dokumentation der USGS.

| Frage | Ergebnis |
|---|---|
| Vollständigkeit | `metadata.count` vorhanden, = Anzahl Features (1) |
| Zeitformat | `time`, `updated` in Epoch-Millisekunden, UTC |
| PAGER | `alert` = `"green"`; laut Doku auch `null` möglich |
| Prüfstatus | `status` = `"reviewed"` |
| Koordinaten | `[lon, lat, Tiefe km]` |
| Identität | `id` plus Aliasliste `ids` (3 IDs aus 3 Netzen) |
| Tsunami | `tsunami: 1` ist ein Regions-Flag, keine Warnung |

Konsequenzen im Adapter:

- `mmi`, `cdi` und `felt` **werden übernommen** (`shaking_mmi`, `reported_cdi`, `felt_reports`). Sie beantworten, was die Magnitude nicht beantwortet: ob und wie stark ein Beben bei Menschen angekommen ist. `mmi` ist die instrumentell geschätzte, `cdi` die von Menschen gemeldete Intensität — beide auf der Mercalli-Skala I–XII, die **Wirkung** misst, nicht freigesetzte Energie. Werte außerhalb 0–12 sind ein `sanity`-Fehler, `felt` muss eine nicht-negative ganze Zahl sein. Fehlt ein Feld, steht `null` — ausdrücklich nicht `0`, denn „nicht angegeben" ist nicht „nicht gespürt".
- `tsunami` und `sig` werden **nicht** übernommen. Laut USGS bedeutet `tsunami: 1` nur „großes Beben in ozeanischer Region"; ob ein Tsunami existiert, sagt das Feld ausdrücklich nicht. Die Anzeige als Warnung wäre falsch — in der echten Antwort vom 19.09.2026 ist das Flag gesetzt, obwohl PAGER grün ist. Wer Tsunami-Warnungen braucht, braucht eine Warnquelle, nicht dieses Feld. `sig` ist eine interne USGS-Rangzahl ohne Bedeutung für Leser.
- Die bevorzugte ID eines Bebens kann wechseln (Aliasliste `ids`). Der Adapter liefert die Aliase mit; die Zusammenführung behält die zuerst gesehene ID. Test: `test_alias_keeps_first_identity`.
- Kein Ländercode vorhanden. `countries` bleibt leer; `place` ist der Ortsname der Quelle (englisch).
- Unbekannte `status`- oder `alert`-Werte sind Schemadrift und lassen den Abruf scheitern.
- `status: deleted` wird als ausdrücklicher Rückzug (`withdrawn`) behandelt. Ob der Summary-Feed gelöschte Beben überhaupt liefert, ist nicht belegt.

Noch offen (nur im Livebetrieb klärbar): Verhalten bei `alert: null` in echten Antworten und die tatsächliche Aktualisierungsfrequenz des Feeds.

## Feed-Entwicklung seit 20.09.2026

Der ursprüngliche Prototyp verwendete `significant_week.geojson` und zeigte daher nur die von USGS als signifikant eingeordneten Beben. Danach wurde `all_day.geojson` live verifiziert, um die vollständige technische Verarbeitung des USGS-Tagesfeeds zu prüfen. Diese breite Auswahl wurde anschließend bewusst **nicht** als dauerhafte Weltkartenbasis übernommen, weil kleine Beben regional stark ungleich erfasst werden.

Die aktuelle öffentliche Quelle ist deshalb `4.5_day.geojson`; Auswahl und Begründung stehen im nächsten Abschnitt. Die historische, unverändert echte Signifikanz-Fixture vom 19.09.2026 bleibt als Parser-Regression erhalten. `metadata.count == len(features)` wird weiterhin vor der Typauswahl geprüft.

## Auswahl: ab Magnitude 4,5, und warum

Der Feed ist `4.5_day.geojson` — die **Auswahl von USGS**, nicht von ConflictWatch. Das war eine bewusste Korrektur: zuvor lief `all_day` (alle gelisteten Beben der letzten 24 Stunden), am 20.09.2026 waren das 212 Ereignisse mit Median-Magnitude 1,5.

Der Grund gegen `all_day` ist nicht „zu viele Punkte", sondern **Verzerrung**. Dieselbe echte Antwort, nach Region aufgeschlüsselt:

| Magnitude | Anzahl | USA und Territorien | Rest der Welt |
| --- | --- | --- | --- |
| unter M2.5 | 161 | 152 | 9 |
| M2.5–4.4 | 35 | 20 | 15 |
| ab M4.5 | 15 | 2 | 13 |

Unterhalb M4.5 zeigt eine Weltkarte vor allem die Dichte des US-Messnetzes, nicht die Verteilung von Erdbeben. Erst ab M4.5 erfasst USGS weltweit gleichmäßig. Deshalb liegt die Schwelle dort — belegbar, nicht nach Gefühl.

**Was das für Aussagen bedeutet.** `complete=true` heißt jetzt: vollständig ist die *Auswahl des Feeds*, nicht die Gesamtheit aller Beben. Schwächere Beben sind nicht enthalten, und das ist **keine Entwarnung**. Dieser Satz steht in `coverage_note`, im Hinweistext unter der Karte und in der Legende.

**Aufbewahrung.** `retention_days: 7`. Mit `all_day` und 30 Tagen wäre der Bestand auf grob 6.500 Beben und der öffentliche `snapshot.json` auf etwa 4,6 MB gewachsen — eine Datei, die jeder Seitenaufruf vollständig lädt. Mit `4.5_day` und 7 Tagen sind es rund 235 Einträge und etwa 185 KB.

**Kartenfilter.** Da der Bestand bereits die Auswahl der Quelle ist, blendet die Karte voreingestellt nichts zusätzlich aus („alle gespeicherten"). Wer weiter einschränken will, kann auf M5, M6 oder M7 gehen; der Hinweistext nennt dann getrennt, was die Quelle gar nicht liefert und was der gewählte Filter verbirgt — letzteres ausdrücklich als *gespeichert*, nicht als nicht vorhanden.

Der Zeitfilter (24 h / 7 Tage / gesamter Datenstand) folgt `highlight.recency_basis`: bei USGS zählt die Ereigniszeit, bei GDACS die letzte Sichtung. Sonst fiele ein seit Monaten brennender Waldbrand aus „letzte 24 Stunden" heraus, obwohl die Quelle ihn heute meldet.

Ohne Zusammenfassung wäre auch dieser Bestand unübersichtlich. `site/map.js` fasst Marker zusammen, die einander auf dem Bildschirm überdecken (16 px), und trennt sie beim Hineinzoomen wieder auf. Punktgenaue und ungefähre Orte werden dabei **nie** zu einem Marker verschmolzen.

## Wirkung statt Energie in der Anzeige

Die Meldung nennt die Mercalli-Stufe als römische Ziffer mit der Beschreibung der Skala und **getrennt davon** den Messwert: „Mercalli V – von fast allen gespürt (Messwert 4,98)". Die Stufe ist gerundet, der Messwert nicht — aus 4,983 darf nicht der Eindruck eines glatten Messwerts 5 entstehen. Die Stufenbeschreibungen stammen von der Mercalli-Skala, nicht von ConflictWatch.

Hat ein Beben weder `mmi` noch `cdi`, steht in der Meldung ausdrücklich: „Von der Quelle nicht angegeben. Das heißt nicht, dass das Beben nicht gespürt wurde." Das ist der Normalfall — am 20.09.2026 hatten nur 4 von 213 Beben überhaupt eine PAGER-Stufe, und Wirkungsdaten entstehen erst, wenn ShakeMap gerechnet oder Rückmeldungen abgegeben wurden.

