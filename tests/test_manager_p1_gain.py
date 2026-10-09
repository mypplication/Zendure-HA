"""Closed-loop tests for the P1 regulation in ZendureManager.powerChanged.

powerChanged adds the device output read *now* to the last P1 value. With a slow
P1 meter (e.g. a Tuya PJ-1203A clamp publishing every ~6 s with late energy flow),
that P1 value reflects the device output of the *previous* update. Correcting 100%
of it then gives b[k+1] = b[k] + (load - b[k-1]), which oscillates forever with a
period of 6 updates. SmartMode.P1_GAIN damps this.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from custom_components.zendure_ha.const import DeviceState, ManagerMode, SmartMode
from custom_components.zendure_ha.manager import ZendureManager


class _RecordingSensor:
    def __init__(self) -> None:
        self.values: list[Any] = []

    def update_value(self, value: Any) -> None:
        self.values.append(value)


class _FakeBattery:
    """Stand-in for a discharging device: its output becomes whatever it is told."""

    def __init__(self, *, pwr_max: int, electric_level: int) -> None:
        self.output = 0
        self.pwr_max = pwr_max
        self.discharge_limit = pwr_max
        self.discharge_start = pwr_max // 10
        self.discharge_optimal = pwr_max // 4
        self.electricLevel = SimpleNamespace(asInt=electric_level, asNumber=electric_level)
        self.state = DeviceState.INACTIVE
        self.pwr_offgrid = 0
        self.pwr_produced = 0
        self.exports_bypass = False
        self.actualKwh = 0
        self.kWh = 8
        self.fuseGrp = SimpleNamespace(
            discharge_limit=lambda d: d.pwr_max,
        )
        self.homeInput = SimpleNamespace(asInt=0)
        self.batteryInput = SimpleNamespace(asInt=0)
        self.solarInput = SimpleNamespace(asInt=0)

    @property
    def homeOutput(self) -> SimpleNamespace:
        return SimpleNamespace(asInt=self.output)

    @property
    def batteryOutput(self) -> SimpleNamespace:
        return SimpleNamespace(asInt=self.output)

    async def power_get(self) -> bool:
        return True

    async def power_discharge(self, power: int) -> int:
        self.output = max(0, min(power, self.discharge_limit))
        return self.output


def _make_manager(device: _FakeBattery) -> ZendureManager:
    manager = object.__new__(ZendureManager)
    manager.devices = [device]
    manager.operation = ManagerMode.MATCHING
    manager.operationstate = _RecordingSensor()
    manager.power = _RecordingSensor()
    manager.availableKwh = _RecordingSensor()
    manager.globalSoc = _RecordingSensor()
    manager.charge_time = datetime.max
    manager.charge_last = datetime.min
    manager.pwr_low = 0
    return manager


def _reset_distribution(manager: ZendureManager) -> None:
    """Per-update reset normally done by _p1_changed before calling powerChanged."""
    manager.charge = []
    manager.charge_limit = 0
    manager.charge_optimal = 0
    manager.charge_weight = 0
    manager.discharge = []
    manager.discharge_bypass = 0
    manager.discharge_limit = 0
    manager.discharge_optimal = 0
    manager.discharge_produced = 0
    manager.discharge_weight = 0
    manager.idle = []
    manager.idle_lvlmax = 0
    manager.idle_lvlmin = 100
    manager.produced = 0


async def _run_lagging_meter(load: int, steps: int) -> list[int]:
    """Drive powerChanged with a P1 meter lagging one update behind."""
    device = _FakeBattery(pwr_max=1500, electric_level=80)
    manager = _make_manager(device)
    previous_output = device.output
    p1_values: list[int] = []
    for _ in range(steps):
        p1 = load - previous_output
        p1_values.append(p1)
        previous_output = device.output
        _reset_distribution(manager)
        await manager.powerChanged(p1, False, datetime(2026, 10, 9, 11, 0, 0))
    return p1_values


async def test_setpoint_applies_p1_gain_on_top_of_current_output() -> None:
    device = _FakeBattery(pwr_max=1500, electric_level=80)
    device.output = 300
    manager = _make_manager(device)
    _reset_distribution(manager)

    await manager.powerChanged(100, False, datetime(2026, 10, 9, 11, 0, 0))

    assert device.output == 300 + int(100 * SmartMode.P1_GAIN)


async def test_lagging_p1_meter_converges_instead_of_oscillating() -> None:
    p1_values = await _run_lagging_meter(load=400, steps=40)

    assert max(abs(p) for p in p1_values[-10:]) <= 10


async def test_lagging_p1_meter_oscillation_amplitude_decays() -> None:
    p1_values = await _run_lagging_meter(load=400, steps=40)

    early = max(abs(p) for p in p1_values[2:8])
    late = max(abs(p) for p in p1_values[20:26])
    assert late < early / 4
