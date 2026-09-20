# GDACS-Adapter (Draft, nicht integriert)

## Quelle und Abdeckung

- Feed: [GDACS-App-Feed](https://www.gdacs.org/contentdata/xml/gdacs_app_feed.json), GeoJSON `FeatureCollection`.
- [GDACS-Nutzungsbedingungen](https://www.gdacs.org/About/termofuse.aspx): GDACS erstellt Modell-basierte Meldungen aus verschiedenen Quellen und garantiert weder Aktualität noch Vollständigkeit. GDACS ersetzt keine Warnung lokaler/nationaler Behörden.
- Dieser Adapter übernimmt **nur** `TC` (Zyklon), `FL` (Flut), `VO` (Vulkan), `DR` (Dürre), `WF` (Waldbrand). `EQ` und `TS` werden ignoriert. Das Feld `alertlevel` bleibt in der GDACS-Skala `Green`, `Orange`, `Red`, ohne Vergleich zur USGS-Skala.
- ID: `gdacs:<eventtype>:<eventid>`. Eine neue `episodeid` aktualisiert das bestehende Ereignis. `fromdate` wird als Ereignisbeginn, `datemodified` als Quellenänderung übernommen; `todate` wird validiert, aber nicht als sicheres Ende interpretiert. GDACS-Zeitfelder ohne Zeitzone werden als UTC interpretiert, wie auf den Berichtsseiten bezeichnet. Diese Annahme ist im Live-Test zu prüfen.
- `iscurrent` wird nur als roher Quellenwert gespeichert: Es ist keine gesicherte Aussage über `ongoing` oder den Review-Status. `ongoing=null` und `data_status=unknown` vermeiden diese Fehldeutung.
- Der Punkt im App-Feed ist ein **Zentroid**, nicht die Fläche des Schadens. Deshalb `location.precision=region`. Ländernamen werden nicht in ISO-2 geraten; nur `affectedcountries[].iso2` wird übernommen.

## Vollständigkeit und Live-Tor

Die Quelle veröffentlicht keine `metadata.count` wie USGS. Zudem schließt GDACS selbst Vollständigkeitsgarantien aus. Der Adapter liefert deshalb **immer `complete=false`**: Ein fehlendes Ereignis bedeutet weder zurückgezogen noch veraltet, und eine Antwort mit `features:[]` beweist keinen leeren GDACS-Bestand. Dieses Verhalten verhindert Löschungen durch einen gekürzten Feed, führt aber ohne gesonderte Aufbewahrungsregel langfristig zu anwachsenden Altbeständen. Diese Regel ist vor Integration und Veröffentlichung festzulegen.

Die Fixture `tests/fixtures/gdacs/real_2026-09-20_tc_excerpt.json` enthält genau **ein unverändertes echtes Feature** (TC `1001324`, ODALYS-26), das am 20.09.2026 aus dem offiziellen Feed gelesen wurde. Die `FeatureCollection`-Hülle wurde für den Test neu gebildet; sie ist **keine vollständige Originalantwort**. Andere Kategorien werden derzeit mit explizit veränderten Testdaten geprüft und benötigen jeweils einen echten Datenbeleg. Ein Browserzugriff auf die volle JSON-Datei wurde in dieser Umgebung blockiert; der Webabruf zeigte nur den gekürzten Anfang.

Vor dem Merge: vollständigen Rohabruf mit Zeit, Bytezahl und SHA-256 dokumentieren; alle vorhandenen Hazard-Typen und Feldvarianten gegen den Adapter laufen lassen; echte Fixtures aus unterschiedlichen Typen übernehmen; absichtlich leere/fehlerhafte Antwort und wiederholte Episoden prüfen. Erst dann Registry-Eintrag und `ADAPTERS["gdacs"]` in einem abgestimmten Integrations-PR hinzufügen. `public:false` bis zum Live-Tor beibehalten.
