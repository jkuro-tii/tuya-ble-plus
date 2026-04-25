import asyncio
import logging
import sys
from pathlib import Path

from bleak import BleakScanner

# Add standalone package path:
# /home/jaroslawkurowski/jk/BLE/tuya-ble-plus/custom_components/tuya_ble_plus
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuya_ble.tuya_ble import TuyaBLEDevice
from tuya_ble.const import TuyaBLEDataPointType


ADDRESS = "AA:BB:CC:DD:EE:FF"

CREDS = {
    "address": ADDRESS,
    "device_id": "your_device_id",
    "local_key": "your_local_key",
    "uuid": "your_uuid",
    "device_name": "Standalone Tuya BLE",
    "category": "szjqr",
    "product_id": "ltak7e1p",
    "product_model": "Unknown",
    "product_name": "Fingerbot",
}


def on_connected() -> None:
    print("connected")


def on_disconnected() -> None:
    print("disconnected")


def on_updates(datapoints) -> None:
    for dp in datapoints:
        print(
            f"id={dp.id} type={dp.type.name} value={dp.value} changed_by_device={dp.changed_by_device}"
        )


async def main() -> None:
    logging.basicConfig(level=logging.DEBUG)

    ble_device = await BleakScanner.find_device_by_address(ADDRESS, timeout=15.0)
    if ble_device is None:
        raise RuntimeError(f"Device not found: {ADDRESS}")

    device = TuyaBLEDevice(
        device_manager=None,
        ble_device=ble_device,
        advertisement_data=None,
    )

    device.apply_credentials(CREDS)
    device.register_connected_callback(on_connected)
    device.register_disconnected_callback(on_disconnected)
    device.register_callback(on_updates)

    await device.initialize()

    try:
        await device.update()
        await asyncio.sleep(3)

        dp = device.get_or_create_datapoint(
            id=2,
            type=TuyaBLEDataPointType.DT_BOOL,
            value=False,
        )
        await dp.set_value(True)

        await asyncio.sleep(5)
    finally:
        await device.stop()


if __name__ == "__main__":
    asyncio.run(main())