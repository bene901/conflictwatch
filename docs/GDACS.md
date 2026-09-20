# GDACS-Adapter – interne Integration, öffentlich noch nicht freigegeben

## Quelle und Abdeckung

- Feed: [GDACS-App-Feed](https://www.gdacs.org/contentdata/xml/gdacs_app_feed.json), GeoJSON `FeatureCollection`.
- [GDACS-Nutzungsbedingungen](https://www.gdacs.org/About/termofuse.aspx): GDACS erstellt Modell-basierte Meldungen aus verschiedenen Quellen und garantiert weder Aktualität noch Vollständigkeit. GDACS ersetzt keine Warnung lokaler/nationaler Behörden.
- Dieser Adapter übernimmt im aktuellen Schritt **nur** `TC` (Zyklon), `FL` (Flut) und `WF` (Waldbrand). `VO` (Vulkan) und `DR` (Dürre) werden bewusst übersprungen: Ihr authentisches App-Feed-Format ist nicht belegt, deshalb ist ihre **Abdeckung null – ausdrücklich keine Entwarnung**. `EQ` und `TS` werden ignoriert. Das Feld `alertlevel` bleibt in der GDACS-Skala `Green`, `Orange`, `Red`, ohne Vergleich zur USGS-Skala.
- ID: `gdacs:<eventtype>:<eventid>`. Eine neue `episodeid` aktualisiert das bestehende Ereignis. `fromdate` wird als Ereignisbeginn, `datemodified` als Quellenänderung übernommen; `todate` wird validiert, aber nicht als sicheres Ende interpretiert. GDACS-Zeitfelder ohne Zeitzone werden als UTC interpretiert, wie auf den Berichtsseiten bezeichnet. Diese Annahme ist im Live-Test zu prüfen.
- `iscurrent` wird nur als roher Quellenwert gespeichert: Es ist keine gesicherte Aussage über `ongoing` oder den Review-Status. `ongoing=null` und `data_status=unknown` vermeiden diese Fehldeutung.
- Der Punkt im App-Feed ist ein **Zentroid**, nicht die Fläche des Schadens. Deshalb `location.precision=region`. Ländernamen werden nicht in ISO-2 geraten; nur `affectedcountries[].iso2` wird übernommen.

## Vollständigkeit und Live-Tor

Die Quelle veröffentlicht keine `metadata.count` wie USGS. Zudem schließt GDACS selbst Vollständigkeitsgarantien aus. Der Adapter liefert deshalb **immer `complete=false`**: Ein fehlendes Ereignis bedeutet weder zurückgezogen noch veraltet, und eine Antwort mit `features:[]` beweist keinen leeren GDACS-Bestand. Dieses Verhalten verhindert Löschungen durch einen gekürzten Feed, führt aber ohne gesonderte Aufbewahrungsregel langfristig zu anwachsenden Altbeständen. Nach jedem **erfolgreich geparsten** GDACS-Abruf läuft ein nicht erneut gesichtetes Ereignis nach mehr als 30 Tagen seit `ingest.last_seen_at` technisch aus dem aktiven Bestand aus (`unseen_expiry_days:30`); es wird NICHT als beendet oder zurückgezogen gemeldet. Fehlerhafte oder übersprungene Abrufe löschen nichts. `retention_days:30` ist weiterhin Schema-Pflicht und wirkt bei `complete=false` nicht.

Die drei Fixtures `real_2026-09-20_{tc,fl,wf}_excerpt.json` enthalten je **ein unverändertes echtes Feature** aus dem offiziellen Feed. Die `FeatureCollection`-Hülle wurde für den Test neu gebildet; diese Ausschnitte sind **keine vollständige Originalantwort**. VO und DR kamen im Live-Abruf nicht vor und werden nur mit explizit veränderten Testdaten geprüft. Ein Browserzugriff auf die volle JSON-Datei wurde in dieser Umgebung blockiert. Über die branchbezogene GitHub Action gelang am 20.09.2026 um 11:47 UTC ein vollständiger Abruf: **134475 Bytes**, SHA-256 `3e7361a1aeb6ab71c44c8bff1be92ae7f33466860c2e263542c3de90c3c000cb`, **100 Features** (EQ 22, TC 3, FL 3, WF 72), **78** als relevant verarbeitet. [Lauf und Rohdaten-Artefakt](https://github.com/bene901/conflictwatch/actions/runs/35508798542). Dieser Befund belegt Parserfunktion für die drei tatsächlich vertretenen Typen, nicht Vollständigkeit oder öffentliche Freigabe.

Der [zweite Probe-Lauf](https://github.com/bene901/conflictwatch/actions/runs/35508975001) las zusätzlich `archive.geojson` (94421 Bytes, SHA-256 `aefeae87bf6d4168f3ae013a7953705fb4c602b5bb72a99252da4942f9221476`): EQ 26, FL 24, TC 18, VO 6, WF 15, DR 0. **Das Archiv hat ein anderes Schema.** Beim historischen VO-Feature sind z. B. `eventid`/`episodeid` Zeichenketten, `fromdate` ist `04 Sep 2026 21:00:00`, und `url.report` sowie `datemodified` fehlen. Diese VO-Einträge sind daher kein Live-Beweis, dass der App-Feed für VO dieselben Felder wie TC/FL/WF verwendet. Ein Archiv-Adapter wäre ein eigenständiger Arbeitsauftrag mit eigener Zeit- und Vollständigkeitssemantik.

Vor öffentlicher Freigabe: wiederholte zeitlich getrennte Rohantworten und reale Episodenänderungen auswerten, aktuelle Ereignisse gegen die GDACS-Originalseite prüfen und die 7-Tage-Beobachtung je Quelle abschließen. VO/DR sind NICHT unterstützt, bis echte App-Feed-Antworten gesondert validiert sind. `registry.json public:false` bis zum Live-Tor beibehalten; der öffentlich zugängliche USGS/NOAA-Testmodus ist ausdrücklich weiterhin eine 2-Quellen-Allowlist und zeigt GDACS nicht automatisch.

## Aktualität: gesehen ist nicht andauernd

GDACS-Ereignisse haben eine **Dauer**, kein Datum. `occurred_at` ist `fromdate`, also der **Beginn**. Ein Waldbrand, der seit vier Monaten brennt, hat ein vier Monate altes `occurred_at` und ist trotzdem maximal aktuell. Eine Zeitfenster-Regel über der Anzeigezeit (`window_h`) stuft ihn deshalb systematisch falsch ein: am 20.09.2026 lagen **49 von 87** GDACS-Ereignissen außerhalb von 168 h, darunter eine Flut vom 19.05.2026, die GDACS am selben Tag noch meldete.

Die Quelle trägt deshalb `highlight.recency_basis: "last_seen"`. Ein Eintrag gilt als aktuell, wenn ihn der **jüngste erfolgreiche Abruf** geliefert hat (`last_seen_at == last_success_at` der Quelle). `window_h` wird für solche Quellen **nicht** ausgewertet und steht bei GDACS wieder auf 72; USGS und NOAA behalten `display_time` und ihr bisheriges Verhalten unverändert.

Diese Regel behauptet genau eine Sache: **GDACS führt die Meldung weiterhin.** Sie ist *kein* Beleg, dass das Ereignis andauert — `iscurrent` bleibt unbenutzt, `ongoing` bleibt `null`, `include_ongoing` bleibt `false`. Umgekehrt ist das Fehlen im Feed **keine Entwarnung**: der Eintrag bleibt bis zum technischen Auslaufen (`unseen_expiry_days`) im Bestand und wird lediglich nicht mehr als frisch gesehen geführt. Ein **fehlgeschlagener** oder übersprungener Abruf ändert weder `last_seen_at` noch `last_success_at` und damit auch nicht das Urteil.

In der Oberfläche stehen beide Zeitpunkte getrennt: „Beginn laut Quelle" und „Zuletzt im GDACS-Feed gesehen", letzteres mit dem ausdrücklichen Hinweis, dass daraus keine Fortdauer folgt. In der Zusammenfassungszeile steht zusätzlich „zuletzt gemeldet …", damit ein vier Monate alter Beginn nicht als veralteter Datenstand gelesen wird.

Der öffentliche Snapshot führt dafür **ein einziges abgeleitetes Feld** `last_seen_at`; das interne `ingest`-Objekt wird nicht veröffentlicht. Das Schema erzwingt die Trennung: `Item` verlangt `ingest` und verbietet `last_seen_at`, `PublicItem` verlangt `last_seen_at` und verbietet `ingest`. Der Validator lehnt zusätzlich eine Sichtung ab, die jünger ist als der letzte Abruferfolg der Quelle.

Die Regel selbst wird nicht per Textvergleich geprüft: `tests/test_recency_basis.py` lädt `site/app.js` in node und ruft `onStart` mit echten Snapshot-Daten auf.

## Kartendarstellung

USGS-Erdbeben behalten ihren gefüllten Punktmarker; ihre Koordinate ist punktgenau. GDACS-Ereignisse bekommen einen **gestrichelten, ungefüllten Ring** und in jeder Beschriftung den Satz „ungefähre Lage laut GDACS – keine Schadensfläche". Ein Zentroid wird nie wie ein punktgenauer Gefahrenort gezeichnet. Beide Genauigkeiten stehen als eigene Abfrage im Quelltext (`precision === "point"` bzw. `"region"`), damit in `tests/test_equal_earth_map.py` prüfbar bleibt, dass die Trennung besteht.

Marker desselben Gefahrentyps, die einander auf der Karte überdecken (16 px), werden zu einem Marker mit Anzahl zusammengefasst. **Verschiedene Gefahrenarten werden nie verschmolzen** — sonst entstünde ein Marker, der nichts Bestimmtes mehr aussagt. Am echten Datenstand vom 20.09.2026 werden aus 87 GDACS-Ereignissen 25 Marker, davon 14 Zusammenfassungen.

Die Karte hat getrennte Filter für Waldbrände, Überschwemmungen und Wirbelstürme; angeboten wird nur, was im Datenstand vorkommt. Standardmäßig zeigt sie ausschließlich Ereignisse aus dem **jüngsten erfolgreichen Abruf** (dieselbe Regel wie die Liste, siehe oben). Ältere, noch gespeicherte Meldungen sind über einen eigenen Filter einblendbar, werden dann abgeschwächt dargestellt und tragen den Hinweis, dass sie nicht aus dem jüngsten Abruf stammen — ausdrücklich keine Entwarnung.

Die Markerfarben geben die Warnstufe **der Quelle** wieder (GDACS: Green, Orange, Red). Bei einer Zusammenfassung wird die höchste von GDACS vergebene Stufe der Gruppe verwendet und die Verteilung in der Beschriftung genannt. ConflictWatch leitet daraus keine eigene Gefahrenbewertung ab; die Legende sagt das ausdrücklich.

Geprüft wird nicht per Textvergleich: `tests/js/map_probe.js` führt `site/map.js` in node aus und liest die tatsächlich erzeugte SVG-Struktur aus; `tests/test_gdacs_map_layer.py` prüft daran Marker, Zusammenfassung, Filter und Sichtung.

