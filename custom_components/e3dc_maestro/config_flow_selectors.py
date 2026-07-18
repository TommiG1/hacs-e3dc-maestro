"""Shared selector helpers for the Maestro config / options flow."""
from __future__ import annotations

from homeassistant.helpers import selector


def entity_selector(domain: str = "sensor") -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=domain)
    )


def number_selector(
    min_val: float, max_val: float, step: float = 1.0, unit: str | None = None
) -> selector.NumberSelector:
    del unit
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_val,
            max=max_val,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
        )
    )
