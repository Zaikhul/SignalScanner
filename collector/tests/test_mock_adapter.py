import pytest
from collector.app.adapters.mock_adapter import MockSignalAdapter
from collector.app.core.adapter_base import ScanConfig


@pytest.mark.asyncio
async def test_mock_wifi_adapter_stream():
    adapter = MockSignalAdapter(mode="wifi")
    caps = await adapter.capabilities()
    assert caps.mode == "wifi"
    assert caps.is_available is True

    config = ScanConfig(session_id="ses_test_wifi", sample_interval_ms=100)
    
    count = 0
    async for batch in adapter.start(config):
        count += 1
        assert batch["session_id"] == "ses_test_wifi"
        assert len(batch["measurements"]) > 0
        m0 = batch["measurements"][0]
        assert m0["mode"] == "wifi"
        assert m0["signal"]["unit"] == "dBm"
        assert m0["target_id"].startswith("hmac:")
        assert -100 <= m0["signal"]["value"] <= 0
        if count >= 3:
            await adapter.stop()
            break


@pytest.mark.asyncio
async def test_mock_bluetooth_adapter_stream():
    adapter = MockSignalAdapter(mode="bluetooth")
    config = ScanConfig(session_id="ses_test_ble", sample_interval_ms=100)

    count = 0
    async for batch in adapter.start(config):
        count += 1
        assert len(batch["measurements"]) > 0
        m0 = batch["measurements"][0]
        assert m0["mode"] == "bluetooth"
        assert m0["signal"]["unit"] == "dBm"
        if count >= 2:
            await adapter.stop()
            break


@pytest.mark.asyncio
async def test_mock_radio_adapter_stream():
    adapter = MockSignalAdapter(mode="radio")
    config = ScanConfig(
        session_id="ses_test_rf",
        sample_interval_ms=100,
        center_frequency_hz=433920000,
        fft_size=512
    )

    count = 0
    async for batch in adapter.start(config):
        count += 1
        m0 = batch["measurements"][0]
        assert m0["mode"] == "radio"
        assert m0["signal"]["unit"] == "dBFS"
        assert len(m0["radio"]["fft_bins"]) == 512
        if count >= 2:
            await adapter.stop()
            break
