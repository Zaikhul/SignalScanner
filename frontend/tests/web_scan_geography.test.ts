import { describe, it, expect } from "vitest";
import {
  WebScanGeographyResponse,
  GeoEndpoint,
  GeoRelation,
  GeoCoverage,
} from "@/lib/webScanTypes";

describe("WebScan Geography Schema & Logic", () => {
  const mockGeographyData: WebScanGeographyResponse = {
    schema_version: "web_scan.geo.v1",
    scan_id: "scan_test_101",
    data_revision: 1,
    generated_at: "2026-10-05T00:00:00Z",
    readiness_status: "ready",
    target_display: "https://example.com",
    scan_status: "completed",
    coverage: {
      observations_total: 10,
      observations_stored: 10,
      eligible_records: 3,
      both_located_count: 1,
      partial_located_count: 1,
      unlocated_count: 1,
      is_subset: false,
      storage_ceiling: 200,
    },
    endpoints: [
      {
        id: "src_executor_1",
        role: "source",
        display_name: "scanner-backend-worker-1",
        ip: "103.20.10.5",
        address_basis: "configured",
        executor_id: "scanner-backend-worker-1",
        location: {
          latitude: -6.2088,
          longitude: 106.8456,
          city: "Jakarta",
          region: "Jakarta",
          country_code: "ID",
          country: "Indonesia",
        },
        location_level: "coordinates",
        location_basis: "configured",
        location_status: "located",
        status_reason: "Configured backend executor egress coordinates",
      },
      {
        id: "tgt_public_1",
        role: "target",
        display_name: "1.1.1.1",
        ip: "1.1.1.1",
        address_basis: "observed_connection",
        location: {
          latitude: -33.8688,
          longitude: 151.2093,
          city: "Sydney",
          region: "New South Wales",
          country_code: "AU",
          country: "Australia",
        },
        location_level: "coordinates",
        location_basis: "ip_lookup_estimate",
        location_status: "located",
        status_reason: "Offline database resolution",
      },
      {
        id: "tgt_private_1",
        role: "target",
        display_name: "192.168.1.10",
        ip: "192.168.1.10",
        address_basis: "transport_selected",
        location: null,
        location_level: "unknown",
        location_basis: "unknown",
        location_status: "unsupported",
        status_reason: "Private, loopback, or reserved IP address",
      },
      {
        id: "tgt_unresolved_1",
        role: "target",
        display_name: "subdomain.internal.corp",
        ip: null,
        address_basis: "unresolved",
        location: null,
        location_level: "unknown",
        location_basis: "unknown",
        location_status: "unknown",
        status_reason: "Hostname could not be resolved to IP",
      },
    ],
    relations: [
      {
        id: "rel_1",
        source_endpoint_id: "src_executor_1",
        target_endpoint_id: "tgt_public_1",
        direction: "source_to_target",
        relation_basis: "observed_http",
        record_count: 5,
        unit: "records",
        status_codes: [200],
        methods: ["GET"],
        supporting_observation_ids: ["obs_1", "obs_2"],
        linked_finding_ids: ["find_1"],
      },
      {
        id: "rel_2",
        source_endpoint_id: "src_executor_1",
        target_endpoint_id: "tgt_private_1",
        direction: "source_to_target",
        relation_basis: "transport_attempt",
        record_count: 1,
        unit: "records",
        status_codes: [403],
        methods: ["GET"],
        supporting_observation_ids: ["obs_3"],
        linked_finding_ids: [],
      },
      {
        id: "rel_3",
        source_endpoint_id: "src_executor_1",
        target_endpoint_id: "tgt_unresolved_1",
        direction: "source_to_target",
        relation_basis: "configured_target",
        record_count: 1,
        unit: "records",
        status_codes: [],
        methods: ["GET"],
        supporting_observation_ids: [],
        linked_finding_ids: [],
      },
    ],
    time_info: {
      generated_at: "2026-10-05T00:00:00Z",
    },
    disclaimers: {
      mandatory: "Lokasi IP merupakan perkiraan.",
    },
  };

  it("should validate web_scan.geo.v1 schema integrity", () => {
    expect(mockGeographyData.schema_version).toBe("web_scan.geo.v1");
    expect(mockGeographyData.scan_id).toBe("scan_test_101");
    expect(mockGeographyData.readiness_status).toBe("ready");
    expect(mockGeographyData.disclaimers.mandatory).toBeDefined();
  });

  it("should correctly identify resolved vs unsupported vs unresolved endpoints", () => {
    const endpointsById = new Map(mockGeographyData.endpoints.map((e) => [e.id, e]));

    const publicTarget = endpointsById.get("tgt_public_1")!;
    expect(publicTarget.location_status).toBe("located");
    expect(publicTarget.location?.latitude).toBeCloseTo(-33.8688);
    expect(publicTarget.location?.longitude).toBeCloseTo(151.2093);
    expect(publicTarget.location?.country_code).toBe("AU");

    const privateTarget = endpointsById.get("tgt_private_1")!;
    expect(privateTarget.location_status).toBe("unsupported");
    expect(privateTarget.location).toBeNull();
    expect(privateTarget.status_reason).toContain("Private");

    const unresolvedTarget = endpointsById.get("tgt_unresolved_1")!;
    expect(unresolvedTarget.location_status).toBe("unknown");
    expect(unresolvedTarget.location).toBeNull();
    expect(unresolvedTarget.ip).toBeNull();
  });

  it("prevents drawing phantom arcs for unresolved or unsupported endpoints", () => {
    // Globe should only attempt 3D arc projection when BOTH source and target have located coordinates
    const endpointsById = new Map(mockGeographyData.endpoints.map((e) => [e.id, e]));
    const source = endpointsById.get("src_executor_1")!;

    const renderableArcs = mockGeographyData.relations.filter((rel) => {
      const tgt = endpointsById.get(rel.target_endpoint_id);
      return (
        source?.location?.latitude != null &&
        source?.location?.longitude != null &&
        source?.location_status === "located" &&
        tgt?.location?.latitude != null &&
        tgt?.location?.longitude != null &&
        tgt?.location_status === "located"
      );
    });

    expect(renderableArcs.length).toBe(1);
    expect(renderableArcs[0].id).toBe("rel_1");
  });

  it("should filter relations by relation_basis", () => {
    const filterByBasis = (basis: string) => {
      if (basis === "all") return mockGeographyData.relations;
      return mockGeographyData.relations.filter((r) => r.relation_basis === basis);
    };

    expect(filterByBasis("all").length).toBe(3);
    expect(filterByBasis("observed_http").length).toBe(1);
    expect(filterByBasis("transport_attempt").length).toBe(1);
    expect(filterByBasis("configured_target").length).toBe(1);
  });

  it("should filter relations by search query (IP, display_name, country, city)", () => {
    const endpointsById = new Map(mockGeographyData.endpoints.map((e) => [e.id, e]));

    const searchRelations = (query: string) => {
      const q = query.toLowerCase().trim();
      if (!q) return mockGeographyData.relations;

      return mockGeographyData.relations.filter((rel) => {
        const tgt = endpointsById.get(rel.target_endpoint_id);
        if (!tgt) return false;

        return (
          tgt.display_name.toLowerCase().includes(q) ||
          (tgt.ip && tgt.ip.toLowerCase().includes(q)) ||
          (tgt.location?.country && tgt.location.country.toLowerCase().includes(q)) ||
          (tgt.location?.country_code && tgt.location.country_code.toLowerCase().includes(q)) ||
          (tgt.location?.city && tgt.location.city.toLowerCase().includes(q))
        );
      });
    };

    expect(searchRelations("1.1.1.1").length).toBe(1);
    expect(searchRelations("Australia").length).toBe(1);
    expect(searchRelations("Sydney").length).toBe(1);
    expect(searchRelations("192.168").length).toBe(1);
    expect(searchRelations("subdomain").length).toBe(1);
    expect(searchRelations("nonexistent").length).toBe(0);
  });

  it("computes accurate coverage statistics", () => {
    const coverage = mockGeographyData.coverage;
    expect(coverage.eligible_records).toBe(3);
    expect(coverage.both_located_count).toBe(1);
    expect(coverage.partial_located_count).toBe(1);
    expect(coverage.unlocated_count).toBe(1);
  });

  it("links findings to relations correctly", () => {
    const relWithFindings = mockGeographyData.relations.find((r) => r.linked_finding_ids.length > 0);
    expect(relWithFindings).toBeDefined();
    expect(relWithFindings?.linked_finding_ids).toContain("find_1");
  });
});
