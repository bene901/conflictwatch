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
