/**
 * E3DC Maestro – Lovelace community dashboard strategy.
 *
 * Registers under Settings → Dashboards → Add dashboard → Community dashboards.
 * Requires Home Assistant 2026.5+ for the picker entry (strategy itself works earlier).
 *
 * Dashboard YAML remains the source of truth; this module loads the synced JSON asset.
 */
const STRATEGY_TYPE = "e3dc-maestro";
const ELEMENT_NAME = `ll-strategy-dashboard-${STRATEGY_TYPE}`;
const ASSET_URL = new URL("./maestro_dashboard.json", import.meta.url).href;

class E3DCMaestroDashboardStrategy extends HTMLElement {
  static noEditor = true;

  static getCreateSuggestions(_hass) {
    return {
      title: "E3DC Maestro",
      icon: "mdi:battery-charging",
    };
  }

  static async generate(config, _hass) {
    const response = await fetch(ASSET_URL, { cache: "no-cache" });
    if (!response.ok) {
      throw new Error(
        `E3DC Maestro dashboard asset failed to load (${response.status})`,
      );
    }
    const dashboard = await response.json();
    if (!dashboard || !Array.isArray(dashboard.views)) {
      throw new Error("E3DC Maestro dashboard asset is invalid");
    }
    if (config && typeof config.title === "string" && config.title.trim()) {
      dashboard.title = config.title.trim();
    }
    return dashboard;
  }
}

if (!customElements.get(ELEMENT_NAME)) {
  customElements.define(ELEMENT_NAME, E3DCMaestroDashboardStrategy);
}

window.customStrategies = window.customStrategies || [];
if (
  !window.customStrategies.some(
    (item) => item && item.type === STRATEGY_TYPE && item.strategyType === "dashboard",
  )
) {
  window.customStrategies.push({
    type: STRATEGY_TYPE,
    strategyType: "dashboard",
    name: "E3DC Maestro",
    description:
      "Classic Maestro dashboard with overview, controls, diagnostics and help tabs. Requires Mushroom Cards and ApexCharts from HACS.",
    documentationURL: "https://github.com/TommiG1/hacs-e3dc-maestro",
  });
}
