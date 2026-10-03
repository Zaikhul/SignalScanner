import pytest
from collector.app.adapters.ble_adapter import BleakSignalAdapter


def test_ble_address_type_classification():
    """Verify BLEID-01 Bluetooth address type classification and rotation susceptibility."""
    # Random Static (starts with 0xC0..0xFF)
    addr_type, conf, rotation = BleakSignalAdapter._classify_address_type("C4:56:78:9A:BC:DE")
    assert addr_type == "random_static"
    assert conf == 0.85
    assert not rotation

    # Resolvable Private Address (starts with 0x40..0x7F)
    addr_type, conf, rotation = BleakSignalAdapter._classify_address_type("5A:11:22:33:44:55")
    assert addr_type == "resolvable_private"
    assert conf == 0.45
    assert rotation

    # Public Address (starts with 0x80..0xBF or standard OUI)
    addr_type, conf, rotation = BleakSignalAdapter._classify_address_type("88:AA:BB:CC:DD:EE")
    assert addr_type == "public"
    assert conf == 1.0
    assert not rotation
