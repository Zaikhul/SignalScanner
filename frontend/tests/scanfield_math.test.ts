import { describe, it, expect } from "vitest";
import {
  getStableAngleHash31,
  computeRadialMapping,
  evaluateTargetFreshness,
  isScanActivelyMoving,
  RSSI_MIN_SCALE,
  RSSI_MAX_SCALE,
} from "@/lib/scanfieldMath";

describe("ScanField Math & Logic (PRD v1.2.1)", () => {
  describe("getStableAngleHash31", () => {
    it("should produce deterministic angle between 0 and 359", () => {
      const id1 = "c0:ee:fb:11:22:33";
      const angle1 = getStableAngleHash31(id1);
      expect(angle1).toBeGreaterThanOrEqual(0);
      expect(angle1).toBeLessThan(360);

      // Determinism
      expect(getStableAngleHash31(id1)).toBe(angle1);
    });

    it("should produce identical angle regardless of order or calls", () => {
      const bssids = [
        "aa:bb:cc:dd:ee:01",
        "aa:bb:cc:dd:ee:02",
        "test-target-ble-99",
        "virtual:sdr:node",
      ];
      const results1 = bssids.map(getStableAngleHash31);
      const results2 = bssids.map(getStableAngleHash31);
      expect(results1).toEqual(results2);
    });

    it("should handle empty and special character strings safely", () => {
      expect(getStableAngleHash31("")).toBe(0);
      expect(getStableAngleHash31("SSID with spaces & 🌟 emoji")).toBeGreaterThanOrEqual(0);
      expect(getStableAngleHash31("SSID with spaces & 🌟 emoji")).toBeLessThan(360);
    });
  });

  describe("computeRadialMapping", () => {
    it("should map -30 dBm to center (u = 0)", () => {
      const res = computeRadialMapping(-30, "dBm");
      expect(res.isPlottable).toBe(true);
      expect(res.clampedSignal).toBe(-30);
      expect(res.normalizedU).toBe(0);
      expect(res.outOfScale).toBeNull();
    });

    it("should map -65 dBm to middle annulus (u = 0.5)", () => {
      const res = computeRadialMapping(-65, "dBm");
      expect(res.isPlottable).toBe(true);
      expect(res.clampedSignal).toBe(-65);
      expect(res.normalizedU).toBeCloseTo(0.5, 5);
      expect(res.outOfScale).toBeNull();
    });

    it("should map -100 dBm to outer boundary (u = 1)", () => {
      const res = computeRadialMapping(-100, "dBm");
      expect(res.isPlottable).toBe(true);
      expect(res.clampedSignal).toBe(-100);
      expect(res.normalizedU).toBe(1);
      expect(res.outOfScale).toBeNull();
    });

    it("should clamp values > -30 dBm with outOfScale: high", () => {
      const res = computeRadialMapping(-20, "dBm");
      expect(res.isPlottable).toBe(true);
      expect(res.rawSignal).toBe(-20);
      expect(res.clampedSignal).toBe(-30);
      expect(res.normalizedU).toBe(0);
      expect(res.outOfScale).toBe("high");
    });

    it("should clamp values < -100 dBm with outOfScale: low", () => {
      const res = computeRadialMapping(-115, "dBm");
      expect(res.isPlottable).toBe(true);
      expect(res.rawSignal).toBe(-115);
      expect(res.clampedSignal).toBe(-100);
      expect(res.normalizedU).toBe(1);
      expect(res.outOfScale).toBe("low");
    });

    it("should reject NaN, null, and incompatible units", () => {
      expect(computeRadialMapping(null as any).isPlottable).toBe(false);
      expect(computeRadialMapping(NaN).isPlottable).toBe(false);
      expect(computeRadialMapping(-50, "mW").isPlottable).toBe(false);
    });
  });

  describe("evaluateTargetFreshness", () => {
    const baseNow = 1700000000000;

    it("should evaluate WiFi freshness thresholds (30s / 60s)", () => {
      // 10s old -> fresh
      const freshTarget = { last_seen: new Date(baseNow - 10000).toISOString() };
      expect(evaluateTargetFreshness(freshTarget, baseNow, "wifi").freshness).toBe("fresh");

      // 40s old -> stale
      const staleTarget = { last_seen: new Date(baseNow - 40000).toISOString() };
      const staleRes = evaluateTargetFreshness(staleTarget, baseNow, "wifi");
      expect(staleRes.freshness).toBe("stale");
      expect(staleRes.isStale).toBe(true);
      expect(staleRes.isExpired).toBe(false);

      // 70s old -> expired
      const expiredTarget = { last_seen: new Date(baseNow - 70000).toISOString() };
      const expRes = evaluateTargetFreshness(expiredTarget, baseNow, "wifi");
      expect(expRes.freshness).toBe("expired");
      expect(expRes.isExpired).toBe(true);
    });

    it("should evaluate BLE freshness thresholds (3s / 10s)", () => {
      // 2s old -> fresh
      const freshBle = { last_seen: new Date(baseNow - 2000).toISOString() };
      expect(evaluateTargetFreshness(freshBle, baseNow, "bluetooth").freshness).toBe("fresh");

      // 5s old -> stale
      const staleBle = { last_seen: new Date(baseNow - 5000).toISOString() };
      expect(evaluateTargetFreshness(staleBle, baseNow, "bluetooth").freshness).toBe("stale");

      // 12s old -> expired
      const expiredBle = { last_seen: new Date(baseNow - 12000).toISOString() };
      expect(evaluateTargetFreshness(expiredBle, baseNow, "bluetooth").freshness).toBe("expired");
    });

    it("should return unknown when timestamp is missing or invalid", () => {
      expect(evaluateTargetFreshness({}, baseNow, "wifi").freshness).toBe("unknown");
      expect(evaluateTargetFreshness({ last_seen: "invalid-date" }, baseNow, "wifi").freshness).toBe("unknown");
    });
  });

  describe("isScanActivelyMoving watchdog", () => {
    const now = 100000;

    it("should return true when scanning active with recent activity", () => {
      const active = isScanActivelyMoving({
        sessionStatus: "active",
        connectionState: "connected",
        hasAdapterConflict: false,
        lastActivityTimestamp: now - 2000,
        actualIntervalMs: 500,
        nowMs: now,
      });
      expect(active).toBe(true);
    });

    it("should return false if session is paused or stopped", () => {
      const paused = isScanActivelyMoving({
        sessionStatus: "paused",
        connectionState: "connected",
        hasAdapterConflict: false,
        lastActivityTimestamp: now - 1000,
        nowMs: now,
      });
      expect(paused).toBe(false);
    });

    it("should return false if adapter conflict exists", () => {
      const conflict = isScanActivelyMoving({
        sessionStatus: "active",
        connectionState: "connected",
        hasAdapterConflict: true,
        lastActivityTimestamp: now - 1000,
        nowMs: now,
      });
      expect(conflict).toBe(false);
    });

    it("should stop sweep if watchdog expires (> max(10s, 3*interval))", () => {
      // Interval 1000ms -> timeout is 10000ms. Elapsed 11000ms -> timeout!
      const expired = isScanActivelyMoving({
        sessionStatus: "active",
        connectionState: "connected",
        hasAdapterConflict: false,
        lastActivityTimestamp: now - 11000,
        actualIntervalMs: 1000,
        nowMs: now,
      });
      expect(expired).toBe(false);
    });
  });
});
