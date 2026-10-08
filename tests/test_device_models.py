"""Tests for the SolarFlow 4000 Mix Pro model mapping."""

from __future__ import annotations

from custom_components.zendure_ha.api import Api
from custom_components.zendure_ha.config_flow import ZendureConfigFlow
from custom_components.zendure_ha.device import ZendureBattery
from custom_components.zendure_ha.devices.solarflow4000 import SolarFlow4000MixPro


def test_solarflow4000_mix_pro_local_product_is_supported() -> None:
    # The local /properties/report returns "product": "solarFlow4000MixPro".
    model = ZendureConfigFlow._resolve_model("solarFlow4000MixPro")

    assert model == "solarflow4000mixpro"
    assert Api.createdevice[model] is SolarFlow4000MixPro


async def test_solarflow4000_mix_pro_limits(hass) -> None:  # noqa: ANN001
    definition = {"productKey": "local", "snNumber": "EEE3TEST1", "productModel": "solarflow4000mixpro", "ip": "192.168.1.2", "local": True}
    device = SolarFlow4000MixPro(hass, "EEE3TEST1", "SF4000 Mix Pro", definition)

    assert device.charge_limit == -4000
    assert device.discharge_limit == 3000
    assert device.pwr_offgrid == 0


def test_solarflow4000_mix_pro_internal_pack() -> None:
    _, model, kwh = ZendureBattery.get_battery_type("BEAATEST1", 70)

    assert model == "I8000"
    assert kwh == 8.0
