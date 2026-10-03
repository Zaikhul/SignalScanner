import pytest
from collector.app.adapters.wifi_windows import WindowsWiFiAdapter


def test_parse_netsh_multilingual_english():
    sample_text = """
Interface name : Wi-Fi 
There are 2 networks currently visible. 

SSID 1 : Office_Network
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP 
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 90%  
         Radio type         : 802.11ax
         Band               : 5 GHz
         Channel            : 36 
    BSSID 2                 : aa:bb:cc:dd:ee:02
         Signal             : 70%  
         Radio type         : 802.11n
         Band               : 2.4 GHz
         Channel            : 6 

SSID 2 : Guest_WiFi
    Network type            : Infrastructure
    Authentication          : Open
    Encryption              : None
    BSSID 1                 : 11:22:33:44:55:66
         Signal             : 50%  
         Channel            : 1 
"""
    adapter = WindowsWiFiAdapter()
    networks = adapter._parse_netsh_output(sample_text)

    assert len(networks) == 3
    # First BSSID
    assert networks[0]["ssid"] == "Office_Network"
    assert networks[0]["bssid"] == "aa:bb:cc:dd:ee:01"
    assert networks[0]["rssi_dbm"] == -55.0  # (90/2) - 100
    assert networks[0]["channel"] == 36
    assert networks[0]["band"] == "5GHz"

    # Second BSSID under same SSID
    assert networks[1]["ssid"] == "Office_Network"
    assert networks[1]["bssid"] == "aa:bb:cc:dd:ee:02"
    assert networks[1]["rssi_dbm"] == -65.0  # (70/2) - 100
    assert networks[1]["channel"] == 6
    assert networks[1]["band"] == "2.4GHz"

    # Second SSID
    assert networks[2]["ssid"] == "Guest_WiFi"
    assert networks[2]["bssid"] == "11:22:33:44:55:66"
    assert networks[2]["rssi_dbm"] == -75.0  # (50/2) - 100


def test_parse_netsh_multilingual_indonesian():
    sample_text = """
Nama Antarmuka : Wi-Fi 
Ada 1 jaringan yang terlihat saat ini. 

SSID 1 : Jaya-Network
    Tipe jaringan           : Infrastruktur
    Autentikasi             : WPA2-Personal
    Enkripsi                : CCMP 
    BSSID 1                 : c8:4c:78:19:d8:b2
         Sinyal             : 92%  
         Tipe radio         : 802.11n
         Saluran            : 6 
"""
    adapter = WindowsWiFiAdapter()
    networks = adapter._parse_netsh_output(sample_text)

    assert len(networks) == 1
    assert networks[0]["ssid"] == "Jaya-Network"
    assert networks[0]["bssid"] == "c8:4c:78:19:d8:b2"
    assert networks[0]["rssi_dbm"] == -54.0  # (92/2) - 100
    assert networks[0]["channel"] == 6
    assert networks[0]["band"] == "2.4GHz"


def test_parse_netsh_hidden_ssid():
    sample_text = """
SSID 1 : 
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP 
    BSSID 1                 : de:ad:be:ef:00:01
         Signal             : 80%  
         Channel            : 11 
"""
    adapter = WindowsWiFiAdapter()
    networks = adapter._parse_netsh_output(sample_text)

    assert len(networks) == 1
    assert networks[0]["ssid"] == "Hidden Network"
    assert networks[0]["bssid"] == "de:ad:be:ef:00:01"
    assert networks[0]["rssi_dbm"] == -60.0
    assert networks[0]["channel"] == 11
