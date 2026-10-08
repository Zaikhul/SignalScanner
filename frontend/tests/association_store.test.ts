import { describe, it, expect, beforeEach } from "vitest";
import { useScannerStore } from "../lib/store";
import { LanHost, WifiAssociation } from "../lib/types";

describe("Association & LAN Host Store Features (PRD v1.1)", () => {
  beforeEach(() => {
    useScannerStore.getState().resetLiveState();
  });

  it("should set and update active association state", () => {
    const store = useScannerStore.getState();

    const mockAssoc: WifiAssociation = {
      id: "asc_test_01",
      session_id: "ses_test_01",
      collector_id: "col_test_01",
      adapter_id: "win_wlan_01",
      target_id: "tgt_01",
      ssid: "Office_WiFi",
      security_type: "wpa2_personal",
      state: "associating",
      created_at: new Date().toISOString(),
    };

    store.setActiveAssociation(mockAssoc);
    expect(useScannerStore.getState().activeAssociation?.state).toBe("associating");
    expect(useScannerStore.getState().activeAssociation?.ssid).toBe("Office_WiFi");

    // Update state to connected with IP address
    useScannerStore.getState().updateAssociationState("connected", {
      ipv4: "192.168.1.50",
      gateway: "192.168.1.1",
      prefix: "192.168.1.0/24",
    });

    const updated = useScannerStore.getState().activeAssociation;
    expect(updated?.state).toBe("connected");
    expect(updated?.ipv4).toBe("192.168.1.50");
    expect(updated?.gateway).toBe("192.168.1.1");
    expect(updated?.ssid).toBe("Office_WiFi"); // Preserved
  });

  it("should upsert and deduplicate LAN hosts correctly", () => {
    const store = useScannerStore.getState();

    const host1: LanHost = {
      ip: "192.168.1.1",
      ip_version: 4,
      hostname: "router.lan",
      mac_hash: "hash_router_mac",
      oui_vendor: "Cisco Systems",
      discovery_methods: ["gateway_snapshot"],
      reachability: "up",
      rtt_ms: 1.0,
      is_self: false,
      is_gateway: true,
      quality_flags: ["gateway"],
      last_seen: new Date().toISOString(),
    };

    store.upsertLanHost(host1);
    expect(useScannerStore.getState().lanHosts).toHaveLength(1);
    expect(useScannerStore.getState().lanHosts[0].ip).toBe("192.168.1.1");

    // Upsert updated host with same mac_hash but updated RTT
    const host1Updated: LanHost = {
      ...host1,
      rtt_ms: 0.8,
      discovery_methods: ["gateway_snapshot", "arp_cache"],
    };
    useScannerStore.getState().upsertLanHost(host1Updated);

    // Should NOT duplicate
    expect(useScannerStore.getState().lanHosts).toHaveLength(1);
    expect(useScannerStore.getState().lanHosts[0].rtt_ms).toBe(0.8);

    // Add another host
    const host2: LanHost = {
      ip: "192.168.1.45",
      ip_version: 4,
      hostname: "pc-workstation",
      mac_hash: "hash_pc_mac",
      oui_vendor: "Dell Inc",
      discovery_methods: ["arp_cache"],
      reachability: "up",
      rtt_ms: 2.1,
      is_self: false,
      is_gateway: false,
      quality_flags: ["arp_cache"],
      last_seen: new Date().toISOString(),
    };
    useScannerStore.getState().upsertLanHost(host2);
    expect(useScannerStore.getState().lanHosts).toHaveLength(2);
  });

  it("should reset association and host states on resetLiveState", () => {
    const store = useScannerStore.getState();

    store.setActiveAssociation({
      id: "asc_01",
      session_id: "ses_01",
      collector_id: "col_01",
      adapter_id: "adap_01",
      target_id: "tgt_01",
      security_type: "open",
      state: "connected",
      created_at: new Date().toISOString(),
    });

    store.upsertLanHost({
      ip: "192.168.1.1",
      ip_version: 4,
      mac_hash: "hash_01",
      discovery_methods: ["arp_cache"],
      reachability: "up",
      is_self: false,
      is_gateway: true,
      quality_flags: [],
      last_seen: new Date().toISOString(),
    });

    store.setAdapterConflictNotice("Scanning paused");

    store.resetLiveState();

    expect(useScannerStore.getState().activeAssociation).toBeNull();
    expect(useScannerStore.getState().lanHosts).toHaveLength(0);
    expect(useScannerStore.getState().adapterConflictNotice).toBeNull();
  });

  it("should preserve and update open_ports on LAN host", () => {
    const store = useScannerStore.getState();

    const initialHost: LanHost = {
      ip: "192.168.1.100",
      ip_version: 4,
      hostname: "webserver.local",
      mac_hash: "hash_webserver",
      oui_vendor: "Intel Corp",
      discovery_methods: ["arp_cache"],
      reachability: "up",
      is_self: false,
      is_gateway: false,
      quality_flags: ["arp_cache"],
      last_seen: new Date().toISOString(),
    };

    store.upsertLanHost(initialHost);
    expect(useScannerStore.getState().lanHosts[0].open_ports).toBeUndefined();

    // After port scan completes
    const scannedHost: LanHost = {
      ...initialHost,
      open_ports: [
        { port: 80, service: "HTTP", state: "open" },
        { port: 443, service: "HTTPS", state: "open" },
      ],
    };

    store.upsertLanHost(scannedHost);
    const hostInStore = useScannerStore.getState().lanHosts[0];
    expect(hostInStore.open_ports).toHaveLength(2);
    expect(hostInStore.open_ports?.[0].port).toBe(80);
    expect(hostInStore.open_ports?.[0].service).toBe("HTTP");
    expect(hostInStore.open_ports?.[1].port).toBe(443);
  });
});
