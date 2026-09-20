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

- `tsunami`, `sig`, `mmi`, `cdi`, `felt` werden nicht übernommen. Laut USGS bedeutet `tsunami: 1` nur „großes Beben in ozeanischer Region“; ob ein Tsunami existiert, sagt das Feld nicht. Die Anzeige als Warnung wäre falsch.
- Die bevorzugte ID eines Bebens kann wechseln (Aliasliste `ids`). Der Adapter liefert die Aliase mit; die Zusammenführung behält die zuerst gesehene ID. Test: `test_alias_keeps_first_identity`.
- Kein Ländercode vorhanden. `countries` bleibt leer; `place` ist der Ortsname der Quelle (englisch).
- Unbekannte `status`- oder `alert`-Werte sind Schemadrift und lassen den Abruf scheitern.
- `status: deleted` wird als ausdrücklicher Rückzug (`withdrawn`) behandelt. Ob der Summary-Feed gelöschte Beben überhaupt liefert, ist nicht belegt.

Noch offen (nur im Livebetrieb klärbar): genaue Auswahlregel des Signifikanz-Feeds, Verhalten bei `alert: null` in echten Antworten, Aktualisierungsfrequenz des Feeds.

## Feed-Abdeckung seit 20.09.2026

Der ursprüngliche Prototyp verwendete `significant_week.geojson` und zeigte daher nur die von USGS als signifikant eingeordneten Beben. Das ist **nicht** der vollständige USGS-Kartenbestand. Die produktive interne Quelle nutzt jetzt `all_day.geojson` (sämtliche im USGS-Echtzeit-Feed gelisteten Ereignisse der letzten 24 Stunden). Der Adapter übernimmt daraus nur Features mit `properties.type = earthquake`, nicht etwa Sprengungen. Die Integritätsprüfung `metadata.count == len(features)` zählt weiter alle gelieferten Features vor der Typauswahl. Echtzeit-Feed bedeutet nicht weltweit lückenlose Erfassung kleiner Beben; Erfassungsgrad und Aktualisierung können regional variieren.

Vorhandene ältere Events bleiben im internen Bestand (30-Tage-Retention für nicht erneut im Feed erscheinende Events) und stehen außerhalb des 24-Stunden-Hauptlistenfensters unter historischen Meldungen; diese Aufbewahrung belegt **keine** fortdauernde Aktualität. Bis zum Abschluss des gesonderten Quellentors bleibt `public:false`; die neue Feed-Abdeckung ist in der ausdrücklich gekennzeichneten USGS/NOAA-Testansicht sichtbar. Die historische, unverändert echte Signifikanz-Fixture vom 19.09.2026 bleibt als Parser-Regression erhalten. Der erweiterte aktuelle Feed wird zusätzlich in der Live-Pipeline geprüft.
