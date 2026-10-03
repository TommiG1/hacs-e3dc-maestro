# Recorder-Beispiel (lokale HA-Optimierung)

Maestro-Entitäten sollten **nicht** aus dem Recorder ausgeschlossen werden
(Energy-Dashboard, Forecast-Qualitätsprüfung, Sizing Advisor).

**Hinweis (ab v0.3.23):** Die großen Prognose-Kurven-Attribute des Sensors
`sensor.e3dc_maestro_forecast_soc_trajektorie_24h` (`trajectory_points`,
`pv_points`, `house_points`, `grid_points`, `battery_points`, `trajectory_soc`,
`trajectory_phases`) schreibt die Integration selbst **nicht** in die
Recorder-Datenbank (`_unrecorded_attributes`). Ein manueller Ausschluss ist nicht
nötig.

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
