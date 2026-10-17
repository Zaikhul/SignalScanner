import { describe, it, expect } from "vitest";
import {
  buildActiveFindingSeverityMap,
  latLonToUnitVec3,
  slerpUnitVec3,
  distancePointToSegment,
  resolveRelationVisualStyle,
  clusterTargetEndpoints,
} from "@/lib/globeMath";
import { GeoEndpoint, GeoRelation, Severity } from "@/lib/webScanTypes";

describe("3D Globe Geodesic Math & Visual Encoding", () => {
  it("F09: buildActiveFindingSeverityMap suppresses false_positive and resolved findings", () => {
    const findings: { id: string; severity: Severity; triage_status?: any }[] = [
      { id: "f_open", severity: "critical", triage_status: "open" },
      { id: "f_in_prog", severity: "high", triage_status: "in_progress" },
      { id: "f_accepted", severity: "medium", triage_status: "accepted_risk" },
      { id: "f_fp", severity: "critical", triage_status: "false_positive" },
      { id: "f_res", severity: "high", triage_status: "resolved" },
      { id: "f_untriaged", severity: "low" },
    ];
    const active = buildActiveFindingSeverityMap(findings);
    expect(active.get("f_open")).toBe("critical");
    expect(active.get("f_in_prog")).toBe("high");
    expect(active.get("f_accepted")).toBe("medium");
    expect(active.get("f_untriaged")).toBe("low");
    expect(active.has("f_fp")).toBe(false);
    expect(active.has("f_res")).toBe(false);

    // Verify arc visual style falls back when its only critical finding was triaged away
    const rel: GeoRelation = {
      id: "rel_triage",
      source_endpoint_id: "src_1",
      target_endpoint_id: "tgt_1",
      direction: "source_to_target",
      relation_basis: "observed_http",
      record_count: 5,
      unit: "records",
      status_codes: [200],
      methods: ["GET"],
      supporting_observation_ids: [],
      linked_finding_ids: ["f_fp"],
    };
    const styleSuppressed = resolveRelationVisualStyle(rel, "severity", active);
    expect(styleSuppressed.stroke).toBe("#10b981");
    expect(styleSuppressed.badgeText).toBe("CLEAN");
  });

  it("converts lat/lon to unit 3D vector with norm = 1", () => {
    const vJakarta = latLonToUnitVec3(-6.2088, 106.8456);
    const norm = Math.hypot(vJakarta.x, vJakarta.y, vJakarta.z);
    expect(norm).toBeCloseTo(1.0, 5);
  });

  it("computes Great-Circle Slerp midpoint on unit sphere", () => {
    const v1 = latLonToUnitVec3(0, 0);
    const v2 = latLonToUnitVec3(0, 90);
    const { point, omega } = slerpUnitVec3(v1, v2, 0.5);
    expect(omega).toBeCloseTo(Math.PI / 2, 4);
    expect(Math.hypot(point.x, point.y, point.z)).toBeCloseTo(1.0, 5);
    expect(point.x).toBeCloseTo(Math.SQRT1_2, 4);
    expect(point.z).toBeCloseTo(Math.SQRT1_2, 4);
  });

  it("accurately measures point-to-segment distance for arc hit-testing", () => {
    const d1 = distancePointToSegment(50, 12, 10, 10, 90, 10);
    expect(d1).toBeCloseTo(2.0, 4);

    const d2 = distancePointToSegment(0, 10, 10, 10, 90, 10);
    expect(d2).toBeCloseTo(10.0, 4);
  });

  it("encodes relation color by highest finding severity and HTTP status", () => {
    const rel: GeoRelation = {
      id: "rel_1",
      source_endpoint_id: "src_1",
      target_endpoint_id: "tgt_1",
      direction: "source_to_target",
      relation_basis: "observed_http",
      record_count: 15,
      unit: "records",
      status_codes: [200, 403],
      methods: ["GET", "POST"],
      supporting_observation_ids: ["obs_1"],
      linked_finding_ids: ["f_crit"],
    };

    const sevMap = new Map<string, Severity>([["f_crit", "critical"]]);
    const sevStyle = resolveRelationVisualStyle(rel, "severity", sevMap);
    expect(sevStyle.stroke).toBe("#f43f5e");
    expect(sevStyle.badgeText).toBe("CRITICAL");

    const httpStyle = resolveRelationVisualStyle(rel, "http_status", sevMap);
    expect(httpStyle.stroke).toBe("#f59e0b");
    expect(httpStyle.badgeText).toBe("HTTP 4xx");
  });

  it("clusters co-located target endpoints to prevent label collision", () => {
    const endpoints = new Map<string, GeoEndpoint>([
      [
        "tgt_a",
        {
          id: "tgt_a",
          role: "target",
          display_name: "api.example.com",
          ip: "104.16.1.1",
          address_basis: "observed_connection",
          location: { latitude: 37.7749, longitude: -122.4194, city: "San Francisco", country: "US" },
          location_level: "city",
          location_basis: "ip_lookup_estimate",
          location_status: "located",
        },
      ],
      [
        "tgt_b",
        {
          id: "tgt_b",
          role: "target",
          display_name: "cdn.example.com",
          ip: "104.16.1.2",
          address_basis: "observed_connection",
          location: { latitude: 37.7751, longitude: -122.4196, city: "San Francisco", country: "US" },
          location_level: "city",
          location_basis: "ip_lookup_estimate",
          location_status: "located",
        },
      ],
    ]);

    const relations: GeoRelation[] = [
      {
        id: "rel_a",
        source_endpoint_id: "src_1",
        target_endpoint_id: "tgt_a",
        direction: "source_to_target",
        relation_basis: "observed_http",
        record_count: 4,
        unit: "records",
        status_codes: [200],
        methods: ["GET"],
        supporting_observation_ids: [],
        linked_finding_ids: ["f1"],
      },
      {
        id: "rel_b",
        source_endpoint_id: "src_1",
        target_endpoint_id: "tgt_b",
        direction: "source_to_target",
        relation_basis: "observed_http",
        record_count: 6,
        unit: "records",
        status_codes: [200],
        methods: ["GET"],
        supporting_observation_ids: [],
        linked_finding_ids: [],
      },
    ];

    const clusters = clusterTargetEndpoints(relations, endpoints);
    expect(clusters.length).toBe(1);
    expect(clusters[0].endpoints.length).toBe(2);
    expect(clusters[0].totalRecords).toBe(10);
    expect(clusters[0].totalFindings).toBe(1);
  });
});
