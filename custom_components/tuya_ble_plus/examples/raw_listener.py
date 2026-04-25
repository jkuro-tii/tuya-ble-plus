#!/usr/bin/env python3

import asyncio
import logging
import sys
from pathlib import Path

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuya_ble.tuya_ble import TuyaBLEDevice


SCAN_TIMEOUT = 120.0

DEVICE_CONFIGS = [
    {
        "label": "T&H_1",
        "name_hint": "T & H Sensor",
        "creds": {
            "address": "38:A5:C9:C7:10:41",
            "device_id": "bf3bb9ed368f558f660mpf",
            "local_key": "B}Tr5c_VF@ntBN?f",
            "uuid": "29ef7b2fa99ed71b",
            "device_name": "T&H Sensor 1",
            "category": "",
            "product_id": "",
            "product_model": "",
            "product_name": "",
        },
    },
    # {
    #     "label": "T&H_2",
    #     "name_hint": "T & H Sensor 2",
    #     "creds": {
    #         "address": "38:A5:C9:BC:C2:BC",
    #         "device_id": "bf1441cdae678f19c18ams",
    #         "local_key": "}m/c!(Mw]Ww<7nL7",
    #         "uuid": "80f5d49ad980e856",
    #         "device_name": "T&H Sensor 2",
    #         "category": "",
    #         "product_id": "",
    #         "product_model": "",
    #         "product_name": "",
    #     },
    # }
    # ,
    # {
    #     "label": "4-443",
    #     "name_hint": "4-443",
    #     "creds": {
    #         "address": "3C:0B:59:9D:17:3F",
    #         "device_id": "bf0ea1e2568235c4b9v9w9",
    #         "local_key": "VWhSB_SR]p;ZUz5:",
    #         "uuid": "6176fa88e513a030",
    #         "device_name": "4-443",
    #         "category": "",
    #         "product_id": "",
    #         "product_model": "",
    #         "product_name": "",
    #     },
    # }
    # {
    #     "label": "Fan socket",
    #     "name_hint": "Fan Socket",
    #     "creds": {
    #         "address": "FC:67:1F:7E:C4:7C",
    #         "device_id": "bf299a752211936eaaa9er",
    #         "local_key": "zUJK5i(5{J=(>1Uz",
    #         "uuid": "98b6d6d54c9f7963",
    #         "device_name": "Fan Socket",
    #         "category": "",
    #         "product_id": "",
    #         "product_model": "",
    #         "product_name": "",
    #     },
    # }
    # {
    #     "label": "Temp_sensor",
    #     "name_hint": "Temp_sensor",
    #     "creds": {
    #         "address": "FC:67:1F:7E:7B:F3",
    #         "device_id": "bfa312ccedeea8d29cl9hb",
    #         "local_key": "+$.!ch.xlFJ<[?5$",
    #         "uuid": "c681e4a6d2ed6695",
    #         "device_name": "Temp_sensor",
    #         "category": "",
    #         "product_id": "",
    #         "product_model": "",
    #         "product_name": "",
    #     },
    # }
    # {
    #     "label": "RPi_sensor",
    #     "name_hint": "RPi_sensor",
    #     "creds": {
    #         "address": "3C:0B:59:01:FD:C7",
    #         "device_id": "bfcf265f2c4afce354ae7x",
    #         "local_key": "}xi$4N7JaCM_'|u|",
    #         "uuid": "1a3d14645cece858",
    #         "device_name": "RPi_sensor",
    #         "category": "",
    #         "product_id": "",
    #         "product_model": "",
    #         "product_name": "",
    #     },  
    # }
]


def make_on_connected(label: str):
    def on_connected() -> None:
        print(f"[{label}] connected")

    return on_connected


def make_on_disconnected(label: str):
    def on_disconnected() -> None:
        print(f"[{label}] disconnected")

    return on_disconnected


def make_on_updates(label: str):
    def on_updates(datapoints) -> None:
        for dp in datapoints:
            value = dp.value
            rendered = value.hex() if isinstance(value, bytes) else repr(value)
            print(
                f"[{label}] dp id={dp.id} type={dp.type.name} "
                f"value={rendered} changed_by_device={dp.changed_by_device}"
            )

    return on_updates


def _matches(config: dict, dev: BLEDevice) -> bool:
    cfg_address = (config["creds"].get("address") or "").upper()
    if cfg_address and dev.address.upper() == cfg_address:
        return True

    name_hint = (config.get("name_hint") or "").lower()
    name = (dev.name or "").lower()
    return bool(name_hint and name_hint in name)


async def wait_for_all_devices() -> dict[str, BLEDevice]:
    found: dict[str, BLEDevice] = {}

    while len(found) < len(DEVICE_CONFIGS):
        print("scanning...")
        devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)

        for dev in devices:
            print(f"found: {dev.name!r} {dev.address}")
            for config in DEVICE_CONFIGS:
                label = config["label"]
                if label in found:
                    continue
                if _matches(config, dev):
                    found[label] = dev
                    print(f"[{label}] matched {dev.name!r} {dev.address}")

        missing = [cfg["label"] for cfg in DEVICE_CONFIGS if cfg["label"] not in found]
        if missing:
            print(f"waiting for: {', '.join(missing)}")
            await asyncio.sleep(1)

    return found


async def run_device(config: dict, ble_device: BLEDevice) -> None:
    label = config["label"]
    creds = dict(config["creds"])
    creds["address"] = ble_device.address

    print(f"[{label}] using device: {ble_device.name!r} {ble_device.address}")

    device = TuyaBLEDevice(
        device_manager=None,
        ble_device=ble_device,
        advertisement_data=None,
    )

    device.apply_credentials(creds)
    device.register_connected_callback(make_on_connected(label))
    device.register_disconnected_callback(make_on_disconnected(label))
    device.register_callback(make_on_updates(label))

    await device.initialize()

    try:
        print(f"[{label}] pairing...")
        await device.pair()

        print(f"[{label}] requesting status...")
        await device.update()

        print(f"[{label}] waiting for notifications")
        while True:
            await asyncio.sleep(1)

    finally:
        await device.stop()


async def main() -> None:
    logging.basicConfig(level=logging.DEBUG)

    matched = await wait_for_all_devices()
    tasks = [
        asyncio.create_task(run_device(config, matched[config["label"]]))
        for config in DEVICE_CONFIGS
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())