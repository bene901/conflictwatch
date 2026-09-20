# ConflictWatch V6

Amtliche Gefahrenmeldungen als kompakte, mobile Liste. Spezifikation: Rev. 2 (eingefroren).

**Stand dieses Pakets:** nur USGS (Erdbeben). Weitere Quellen erst, wenn der USGS-Datenfluss im echten Repository nachweislich funktioniert.

```
registry.json            Quellen, Skalen, Regeln (nur USGS, public: false)
schema/                  JSON-Schema Rev. 2 (unverändert)
cw/                      Pipeline: Adapter, Zusammenführung, Validierung, Snapshot, CLI
site/                    Website (eine HTML-, eine CSS-, eine JS-Datei; lädt nur data/snapshot.json)
scripts/                 Git-Logik für den Branch data-state
tests/                   54 Tests; Fixture = echte USGS-Antwort vom 19.09.2026
.github/workflows/       pipeline.yml (stündlich), ci.yml (Pull Requests)
docs/RUNBOOK.md          Einrichtung, Funktionstest, Betrieb
docs/USGS.md             Belegte Fakten zur USGS-Schnittstelle
```

Lokal: `pip install -r requirements.txt && python -m unittest discover -s tests -t .`
