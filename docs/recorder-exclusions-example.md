# Recorder-Beispiel (lokale HA-Optimierung)

Maestro-Entitäten sollten **nicht** aus dem Recorder ausgeschlossen werden
(Energy-Dashboard, Forecast-Qualitätsprüfung, Sizing Advisor).

Das lokale Snippet unter `.ha-deploy/` (nicht im Produkt-Repo versioniert)
kann Domains und hochfrequente Diagnose-Sensoren anderer Integrationen
ausschließen. Typische sichere Ausschlüsse:

```yaml
recorder:
  exclude:
    domains:
      - media_player
      - light
      - camera
      - update
      - device_tracker
    entity_globs:
      - sensor.*_linkquality
      - sensor.*_rssi
      - sensor.*_uptime
```

Bewusst **nicht** ausschließen:

- `sensor.e3dc_maestro_*`
- `sensor.s10e_pro_*` / `sensor.e3dc_*` (RSCP-Quellen)
- Energy-/Power-Sensoren der PV-Anlage
