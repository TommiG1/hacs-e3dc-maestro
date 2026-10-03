# Recorder-Beispiel (lokale HA-Optimierung)

Maestro-Entitäten sollten **nicht** aus dem Recorder ausgeschlossen werden
(Energy-Dashboard, Forecast-Qualitätsprüfung, Sizing Advisor).

**Einzige Ausnahme (ab v0.3.23):** der Sensor
`sensor.e3dc_maestro_forecast_soc_trajektorie_24h` trägt die Prognose-Kurven als
Attribute (rund 12 KB, bei jedem Update neu). Die Karten brauchen nur den
aktuellen Zustand, keine Historie. Bitte vom Recorder ausschließen, sonst wächst
die Datenbank spürbar, und bei 48-h-Horizont kann das Attribut-Limit des
Recorders (16 KB) überschritten werden:

```yaml
recorder:
  exclude:
    entities:
      - sensor.e3dc_maestro_forecast_soc_trajektorie_24h
```

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

- `sensor.e3dc_maestro_*` (außer dem oben genannten Trajektorie-Sensor)
- `sensor.s10e_pro_*` / `sensor.e3dc_*` (RSCP-Quellen)
- Energy-/Power-Sensoren der PV-Anlage
