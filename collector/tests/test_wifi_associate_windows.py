import pytest
from collector.app.adapters.wifi_associate_windows import WindowsWiFiAssociationAdapter

SAMPLE_IPCONFIG_WITH_VMWARE = """
Windows IP Configuration

   Host Name . . . . . . . . . . . . : Haykull
   Primary Dns Suffix  . . . . . . . : 
   Node Type . . . . . . . . . . . . : Hybrid
   IP Routing Enabled. . . . . . . . : No
   WINS Proxy Enabled. . . . . . . . : No

Unknown adapter Avast SecureLine VPN Wintun:

   Media State . . . . . . . . . . . : Media disconnected
   Connection-specific DNS Suffix  . : 
   Description . . . . . . . . . . . : Avast SecureLine Wintun Adapter
   Physical Address. . . . . . . . . : 
   DHCP Enabled. . . . . . . . . . . : No
   Autoconfiguration Enabled . . . . : Yes

Wireless LAN adapter Local Area Connection* 8:

   Media State . . . . . . . . . . . : Media disconnected
   Connection-specific DNS Suffix  . : 
   Description . . . . . . . . . . . : Microsoft Wi-Fi Direct Virtual Adapter
   Physical Address. . . . . . . . . : CE-5E-F8-9A-0B-5F
   DHCP Enabled. . . . . . . . . . . : Yes
   Autoconfiguration Enabled . . . . : Yes

Wireless LAN adapter Local Area Connection* 9:

   Media State . . . . . . . . . . . : Media disconnected
   Connection-specific DNS Suffix  . : 
   Description . . . . . . . . . . . : Microsoft Wi-Fi Direct Virtual Adapter #2
   Physical Address. . . . . . . . . : CE-5E-F8-9A-1B-4F
   DHCP Enabled. . . . . . . . . . . : Yes
   Autoconfiguration Enabled . . . . : Yes

Ethernet adapter VMware Network Adapter VMnet1:

   Connection-specific DNS Suffix  . : 
   Description . . . . . . . . . . . : VMware Virtual Ethernet Adapter for VMnet1
   Physical Address. . . . . . . . . : 00-50-56-C0-00-01
   DHCP Enabled. . . . . . . . . . . : Yes
   Autoconfiguration Enabled . . . . : Yes
   Link-local IPv6 Address . . . . . : fe80::8974:8b15:31a4:2c8%12(Preferred) 
   IPv4 Address. . . . . . . . . . . : 192.168.207.1(Preferred) 
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 
   DHCP Server . . . . . . . . . . . : 192.168.207.254
   NetBIOS over Tcpip. . . . . . . . : Enabled

Ethernet adapter VMware Network Adapter VMnet8:

   Connection-specific DNS Suffix  . : 
   Description . . . . . . . . . . . : VMware Virtual Ethernet Adapter for VMnet8
   Physical Address. . . . . . . . . : 00-50-56-C0-00-08
   DHCP Enabled. . . . . . . . . . . : Yes
   Autoconfiguration Enabled . . . . : Yes
   Link-local IPv6 Address . . . . . : fe80::865c:3dcc:e6de:b944%13(Preferred) 
   IPv4 Address. . . . . . . . . . . : 192.168.22.1(Preferred) 
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 
   DHCP Server . . . . . . . . . . . : 192.168.22.254
   NetBIOS over Tcpip. . . . . . . . : Enabled

Wireless LAN adapter Wi-Fi:

   Connection-specific DNS Suffix  . : 
   Description . . . . . . . . . . . : MediaTek Wi-Fi 6 MT7921 Wireless LAN Card
   Physical Address. . . . . . . . . : CC-5E-F8-9A-2B-7F
   DHCP Enabled. . . . . . . . . . . : Yes
   Autoconfiguration Enabled . . . . : Yes
   Link-local IPv6 Address . . . . . : fe80::6f2d:85ba:6987:abcc%16(Preferred) 
   IPv4 Address. . . . . . . . . . . : 192.168.0.75(Preferred) 
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : fe80::f2b4:d2ff:fe81:4c9c%16
                                       192.168.0.1
   DHCP Server . . . . . . . . . . . : 192.168.0.1
   DNS Servers . . . . . . . . . . . : 140.0.10.2
                                       139.228.39.2
                                       118.136.64.4
   NetBIOS over Tcpip. . . . . . . . : Enabled
"""

def test_parse_ipconfig_excludes_vmware_and_picks_wifi():
    result = WindowsWiFiAssociationAdapter._parse_ipconfig_text(SAMPLE_IPCONFIG_WITH_VMWARE)
    assert result != {}
    assert result['ipv4'] == '192.168.0.75'
    assert result['prefix'] == '192.168.0.0/24'
    assert result['gateway'] == '192.168.0.1'
    assert result['dhcp_server'] == '192.168.0.1'
    assert result['dns'] == ['140.0.10.2', '139.228.39.2', '118.136.64.4']
    assert result['captive_state'] == 'internet'

def test_parse_ipconfig_with_target_mac_binding():
    result = WindowsWiFiAssociationAdapter._parse_ipconfig_text(
        SAMPLE_IPCONFIG_WITH_VMWARE,
        target_mac='cc:5e:f8:9a:2b:7f',
    )
    assert result['ipv4'] == '192.168.0.75'
    assert result['gateway'] == '192.168.0.1'

def test_parse_ipconfig_with_target_name_binding():
    result = WindowsWiFiAssociationAdapter._parse_ipconfig_text(
        SAMPLE_IPCONFIG_WITH_VMWARE,
        target_name='Wi-Fi',
    )
    assert result['ipv4'] == '192.168.0.75'
    assert result['gateway'] == '192.168.0.1'

def test_parse_ipconfig_no_physical_wifi_returns_empty():
    only_virtual = '''
Ethernet adapter VMware Network Adapter VMnet1:

   Connection-specific DNS Suffix  . : 
   Description . . . . . . . . . . . : VMware Virtual Ethernet Adapter for VMnet1
   Physical Address. . . . . . . . . : 00-50-56-C0-00-01
   IPv4 Address. . . . . . . . . . . : 192.168.207.1(Preferred) 
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 192.168.207.2
'''
    result = WindowsWiFiAssociationAdapter._parse_ipconfig_text(only_virtual)
    assert result == {}
