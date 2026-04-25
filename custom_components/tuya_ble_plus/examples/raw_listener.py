#!/usr/bin/env python3

import asyncio
import logging
import sys
from pathlib import Path

from bleak import BleakScanner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuya_ble.tuya_ble import TuyaBLEDevice


DEVICE_NAME_HINT = "Fingerbot"  # or set to exact BLE name
SCAN_TIMEOUT = 5.0

CREDS = {
    "address": "C8:A5:C9:BC:C2:BC",
    "device_id": "bf1441cdae678f19c18ams",
    "local_key": "}m/c!(Mw]Ww<7nL7",
    "uuid": "80f5d49ad980e856",
    # optional for standalone use:
    "device_name": "Standalone Tuya BLE",
    "category": "",
    "product_id": "",
    "product_model": "",
    "product_name": "",
}


def on_connected() -> None:
    print("connected")


def on_disconnected() -> None:
    print("disconnected")


def on_updates(datapoints) -> None:
    for dp in datapoints:
        value = dp.value
        if isinstance(value, bytes):
            rendered = value.hex()
        else:
            rendered = repr(value)

        print(
            f"dp id={dp.id} type={dp.type.name} value={rendered} changed_by_device={dp.changed_by_device}"
        )


async def wait_for_device():
    while True:
        print("scanning...")
        devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
        for dev in devices:
            name = dev.name or ""
            print(f"found: {name!r} {dev.address}")
            if DEVICE_NAME_HINT.lower() in name.lower():
                return dev
        await asyncio.sleep(1)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    ble_device = await wait_for_device()
    CREDS["address"] = ble_device.address

    print(f"using device: {ble_device.name!r} {ble_device.address}")

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
        print("pairing...")
        await device.pair()

        print("requesting status...")
        await device.update()

        print("waiting for notifications, press Ctrl+C to stop")
        while True:
            await asyncio.sleep(1)

    finally:
        await device.stop()


if __name__ == "__main__":
    asyncio.run(main())