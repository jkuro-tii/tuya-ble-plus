"""Tuya BLE Plus cover platform."""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import DOMAIN
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import TuyaBLEDataPointType, TuyaBLEDevice

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TuyaBLECoverMapping:
    """Mapping definition for a Tuya BLE cover entity."""

    description: CoverEntityDescription
    control_dp: int | None = None
    control_commands: Collection[str] | None = None
    position_dp: int | None = None
    position_range: tuple[int, int] = (0, 100)
    position_scale: float = 1.0
    current_position_dp: int | None = None
    action_dp: int | None = None
    tilt_dp: int | None = None
    tilt_range: tuple[int, int] | None = None
    tilt_scale: float = 1.0
    invert_position: bool = False
    invert_tilt: bool = False


COVER_PRODUCT_MAPPING: dict[str, TuyaBLECoverMapping] = {
    "dy4dh1q0": TuyaBLECoverMapping(
        description=CoverEntityDescription(
            key="cover",
            device_class=CoverDeviceClass.BLIND,
        ),
        control_dp=1,
        control_commands=frozenset({"open", "close", "stop"}),
        position_dp=2,
        position_range=(0, 100),
        current_position_dp=3,
        action_dp=7,
        tilt_dp=101,
        tilt_range=(1, 10),
        tilt_scale=0.1,
        invert_position=True,
    ),
}


def get_mapping_by_device(device: TuyaBLEDevice) -> TuyaBLECoverMapping | None:
    """Return the cover mapping for the given device."""
    mapping = COVER_PRODUCT_MAPPING.get(device.product_id)
    if not mapping:
        _LOGGER.debug(
            "No cover mapping defined for product_id: %s (category: %s)",
            device.product_id,
            device.category,
        )
    return mapping


class TuyaBLECover(TuyaBLEEntity, CoverEntity):
    """Representation of a Tuya BLE Cover."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        mapping: TuyaBLECoverMapping,
    ) -> None:
        super().__init__(hass, coordinator, device, product, mapping.description)
        self._mapping = mapping

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Return the operations supported by this cover."""
        features = CoverEntityFeature(0)

        if self._mapping.control_dp is not None:
            commands = {cmd.lower() for cmd in self._mapping.control_commands or []}
            if "stop" in commands:
                features |= CoverEntityFeature.STOP
            if "open" in commands:
                features |= CoverEntityFeature.OPEN
            if "close" in commands:
                features |= CoverEntityFeature.CLOSE
        if self._mapping.position_dp is not None:
            features |= CoverEntityFeature.SET_POSITION
            # We can always emulate open/close via position commands.
            features |= CoverEntityFeature.OPEN
            features |= CoverEntityFeature.CLOSE
        if (
            self._mapping.tilt_dp is not None
            and self._mapping.tilt_range is not None
        ):
            features |= CoverEntityFeature.SET_TILT_POSITION
        return features

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if await self._async_send_control_command("open"):
            return
        if await self._async_set_position_percent(100):
            return
        raise NotImplementedError

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        if await self._async_send_control_command("close"):
            return
        if await self._async_set_position_percent(0):
            return
        raise NotImplementedError

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        if await self._async_send_control_command("stop"):
            return
        raise NotImplementedError

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover position."""
        position = kwargs.get(ATTR_POSITION)
        if position is None:
            raise AttributeError
        if await self._async_set_position_percent(position):
            return
        raise NotImplementedError

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Set the cover tilt position."""
        tilt_position = kwargs.get(ATTR_TILT_POSITION)
        if tilt_position is None:
            raise AttributeError
        if await self._async_set_tilt_position_percent(tilt_position):
            return
        raise NotImplementedError

    @property
    def current_cover_position(self) -> int | None:
        """Return the current cover position."""
        position = self._read_position_percent(self._mapping.current_position_dp)
        if position is not None:
            return position
        return self._read_position_percent(self._mapping.position_dp)

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current cover tilt position."""
        return self._read_tilt_percent()

    @property
    def is_opening(self) -> bool | None:
        """Return true if the cover is opening."""
        state = self._current_state
        if state is None:
            return None
        return state == "opening"

    @property
    def is_closing(self) -> bool | None:
        """Return true if the cover is closing."""
        state = self._current_state
        if state is None:
            return None
        return state == "closing"

    @property
    def is_closed(self) -> bool | None:
        """Return true if the cover is closed."""
        state = self._current_state
        if state is None:
            return None
        return state == "closed"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attributes: dict[str, Any] = {}
        if self._mapping.action_dp is not None:
            datapoint = self._device.datapoints[self._mapping.action_dp]
            if datapoint and datapoint.value not in (None, ""):
                attributes["work_state"] = datapoint.value

        target = self._read_position_percent(self._mapping.position_dp)
        if target is not None:
            attributes["target_position"] = target

        tilt = self._read_tilt_percent()
        if tilt is not None:
            attributes["tilt_position"] = tilt

        return attributes

    async def _async_send_control_command(self, command: str) -> bool:
        """Send a control command if supported."""
        if self._mapping.control_dp is None:
            return False

        commands = {cmd.lower() for cmd in self._mapping.control_commands or []}
        if commands and command.lower() not in commands:
            return False

        datapoint = self._device.datapoints.get_or_create(
            self._mapping.control_dp,
            TuyaBLEDataPointType.DT_STRING,
            command,
        )
        await datapoint.set_value(command)
        return True

    async def _async_set_position_percent(self, percent: float) -> bool:
        """Set the target lift position as a percentage."""
        if self._mapping.position_dp is None:
            return False

        raw_value = self._convert_percent_to_raw(percent, is_tilt=False)
        datapoint = self._device.datapoints.get_or_create(
            self._mapping.position_dp,
            TuyaBLEDataPointType.DT_VALUE,
            raw_value,
        )
        await datapoint.set_value(raw_value)
        return True

    async def _async_set_tilt_position_percent(self, percent: float) -> bool:
        """Set the target tilt position as a percentage."""
        if self._mapping.tilt_dp is None or self._mapping.tilt_range is None:
            return False

        raw_value = self._convert_percent_to_raw(percent, is_tilt=True)
        datapoint = self._device.datapoints.get_or_create(
            self._mapping.tilt_dp,
            TuyaBLEDataPointType.DT_VALUE,
            raw_value,
        )
        await datapoint.set_value(raw_value)
        return True

    @property
    def _current_state(self) -> str | None:
        """Return the inferred current state of the cover."""
        if self._mapping.action_dp is not None:
            datapoint = self._device.datapoints[self._mapping.action_dp]
            if datapoint and isinstance(datapoint.value, str):
                action = datapoint.value.lower()
                if action in {"opening", "closing", "opened", "closed"}:
                    return action

        current = self.current_cover_position
        if current is None:
            return None

        if current <= 5:
            return "closed"
        if current >= 95:
            return "opened"

        target = self._read_position_percent(self._mapping.position_dp)
        if target is not None:
            if abs(target - current) <= 2:
                return "opened" if current > 0 else "closed"
            if target > current:
                return "opening"
            if target < current:
                return "closing"

        if self._mapping.control_dp is not None:
            datapoint = self._device.datapoints[self._mapping.control_dp]
            if datapoint and isinstance(datapoint.value, str):
                command = datapoint.value.lower()
                if command in {"open", "close"}:
                    return "opening" if command == "open" else "closing"

        return None

    def _read_position_percent(self, dp_id: int | None) -> int | None:
        """Read a datapoint and convert to percent."""
        if dp_id is None:
            return None
        datapoint = self._device.datapoints[dp_id]
        if not datapoint or datapoint.value in (None, ""):
            return None

        try:
            raw_value = float(datapoint.value)
        except (TypeError, ValueError):
            return None

        scale = self._mapping.position_scale
        raw_value *= scale
        range_min, range_max = self._scaled_position_range()
        if range_max == range_min:
            return 0

        percent = ranged_value_to_percentage((range_min, range_max), raw_value)
        if self._mapping.invert_position:
            percent = 100 - percent
        return int(round(max(0, min(100, percent))))

    def _read_tilt_percent(self) -> int | None:
        """Read tilt datapoint and convert to percent."""
        if self._mapping.tilt_dp is None or self._mapping.tilt_range is None:
            return None

        datapoint = self._device.datapoints[self._mapping.tilt_dp]
        if not datapoint or datapoint.value in (None, ""):
            return None

        try:
            raw_value = float(datapoint.value)
        except (TypeError, ValueError):
            return None

        range_min, range_max = self._scaled_tilt_range()
        raw_value *= self._mapping.tilt_scale

        if range_max == range_min:
            return 0

        percent = ranged_value_to_percentage((range_min, range_max), raw_value)
        if self._mapping.invert_tilt:
            percent = 100 - percent
        return int(round(max(0, min(100, percent))))

    def _convert_percent_to_raw(self, percent: float, *, is_tilt: bool) -> int:
        """Convert a percentage value to its datapoint representation."""
        percent = max(0.0, min(100.0, float(percent)))

        invert = self._mapping.invert_tilt if is_tilt else self._mapping.invert_position
        if invert:
            percent = 100.0 - percent

        if is_tilt:
            if self._mapping.tilt_range is None:
                return int(round(percent))
            range_min, range_max = self._scaled_tilt_range()
            scaled_value = percentage_to_ranged_value((range_min, range_max), percent)
            scale = self._mapping.tilt_scale
            raw_low, raw_high = self._mapping.tilt_range
        else:
            range_min, range_max = self._scaled_position_range()
            scaled_value = percentage_to_ranged_value((range_min, range_max), percent)
            scale = self._mapping.position_scale
            raw_low, raw_high = self._mapping.position_range

        if scale == 0:
            raw_value = scaled_value
        else:
            raw_value = scaled_value / scale

        raw_value = round(raw_value)
        raw_value = max(raw_low, min(raw_high, raw_value))
        return int(raw_value)

    def _scaled_position_range(self) -> tuple[float, float]:
        """Return the scaled position range."""
        low, high = self._mapping.position_range
        scale = self._mapping.position_scale
        return low * scale, high * scale

    def _scaled_tilt_range(self) -> tuple[float, float]:
        """Return the scaled tilt range."""
        if self._mapping.tilt_range is None:
            return (0.0, 100.0)
        low, high = self._mapping.tilt_range
        scale = self._mapping.tilt_scale
        return low * scale, high * scale


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tuya BLE cover entities."""
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    mapping = get_mapping_by_device(data.device)
    if not mapping:
        return

    async_add_entities(
        [
            TuyaBLECover(
                hass,
                data.coordinator,
                data.device,
                data.product,
                mapping,
            )
        ]
    )
