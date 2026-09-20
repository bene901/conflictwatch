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

Die drei Fixtures `real_2026-09-20_{tc,fl,wf}_excerpt.json` enthalten je **ein unverändertes echtes Feature** aus dem offiziellen Feed. Die `FeatureCollection`-Hülle wurde für den Test neu gebildet; diese Ausschnitte sind **keine vollständige Originalantwort**. VO und DR kamen im Live-Abruf nicht vor und werden nur mit explizit veränderten Testdaten geprüft. Ein Browserzugriff auf die volle JSON-Datei wurde in dieser Umgebung blockiert. Über die branchbezogene GitHub Action gelang am 20.09.2026 um 11:47 UTC ein vollständiger Abruf: **134475 Bytes**, SHA-256 `3e7361a1aeb6ab71c44c8bff1be92ae7f33466860c2e263542c3de90c3c000cb`, **100 Features** (EQ 22, TC 3, FL 3, WF 72), **78** als relevant verarbeitet. [Lauf und Rohdaten-Artefakt](https://github.com/bene901/conflictwatch/actions/runs/35508798542). Dieser Befund belegt Parserfunktion für die drei tatsächlich vertretenen Typen, nicht Vollständigkeit oder öffentliche Freigabe.

Vor dem Merge: echte VO/DR-Antworten abwarten oder gezielt historische GDACS-Rohdaten belegen, Altbestand/Retention bei `complete=false` klären und eine zweite zeitlich getrennte Rohantwort für Episodenwechsel prüfen. Erst dann Registry-Eintrag und `ADAPTERS["gdacs"]` in einem abgestimmten Integrations-PR hinzufügen. `public:false` bis zum Live-Tor beibehalten.
