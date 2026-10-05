"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowsClockwise,
  Crosshair,
  MagnifyingGlassMinus,
  MagnifyingGlassPlus,
} from "@phosphor-icons/react";
import { GeoEndpoint, GeoRelation } from "@/lib/webScanTypes";

interface WebScanGlobeProps {
  endpointsById: Map<string, GeoEndpoint>;
  relations: GeoRelation[];
  selectedRelationId: string | null;
  onSelectRelation: (id: string | null) => void;
  onWebglError?: () => void;
}

// Major continent reference dots to provide visual geographic landmasses on the globe
const CONTINENT_DOTS: [number, number][] = [
  // North America
  [45, -100], [55, -115], [35, -95], [38, -122], [40, -74], [60, -135], [25, -80], [30, -105],
  // South America
  [-15, -55], [-23, -46], [-34, -58], [-0, -60], [-10, -75], [-40, -65],
  // Europe
  [48, 2], [52, 13], [55, 37], [40, -3], [41, 12], [59, 18], [60, 10], [51, 0], [45, 25],
  // Africa
  [0, 20], [9, 8], [-26, 28], [30, 31], [15, 30], [-1, 37], [-18, 25],
  // Asia
  [35, 105], [55, 80], [28, 77], [35, 139], [31, 121], [1, 103], [13, 100], [-6, 106],
  // Australia / Oceania
  [-25, 135], [-33, 151], [-37, 144], [-31, 115], [-41, 174],
];

export function WebScanGlobe({
  endpointsById,
  relations,
  selectedRelationId,
  onSelectRelation,
  onWebglError,
}: WebScanGlobeProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Rotation angles (radians)
  const [rotX, setRotX] = useState<number>(0.2); // pitch / tilt
  const [rotY, setRotY] = useState<number>(-1.5); // yaw / longitude
  const [zoom, setZoom] = useState<number>(1.0);

  const isDraggingRef = useRef(false);
  const lastMousePos = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const reducedMotionRef = useRef(false);

  // Check prefers-reduced-motion
  useEffect(() => {
    if (typeof window !== "undefined") {
      const media = window.matchMedia("(prefers-reduced-motion: reduce)");
      reducedMotionRef.current = media.matches;
      const listener = (e: MediaQueryListEvent) => {
        reducedMotionRef.current = e.matches;
      };
      media.addEventListener("change", listener);
      return () => media.removeEventListener("change", listener);
    }
  }, []);

  // Center camera on selected relation if requested
  const focusRelation = useCallback((relId: string) => {
    const rel = relations.find((r) => r.id === relId);
    if (!rel) return;
    const tgt = endpointsById.get(rel.target_endpoint_id);
    if (tgt?.location) {
      const targetRotY = -((tgt.location.longitude * Math.PI) / 180) - Math.PI / 2;
      const targetRotX = (tgt.location.latitude * Math.PI) / 180 * 0.5;
      setRotY(targetRotY);
      setRotX(targetRotX);
    }
  }, [relations, endpointsById]);

  useEffect(() => {
    if (selectedRelationId) {
      focusRelation(selectedRelationId);
    }
  }, [selectedRelationId, focusRelation]);

  // Main Canvas Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      onWebglError?.();
      return;
    }

    let animationId: number = 0;

    const render = () => {
      const width = canvas.width;
      const height = canvas.height;
      const cx = width / 2;
      const cy = height / 2;
      const radius = Math.min(width, height) * 0.38 * zoom;

      ctx.clearRect(0, 0, width, height);

      // 1. Globe Sphere Outer Glow & Background
      const glowGrad = ctx.createRadialGradient(cx, cy, radius * 0.8, cx, cy, radius * 1.25);
      glowGrad.addColorStop(0, "rgba(59, 130, 246, 0.12)");
      glowGrad.addColorStop(0.7, "rgba(59, 130, 246, 0.03)");
      glowGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = glowGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.25, 0, Math.PI * 2);
      ctx.fill();

      // Sphere Body
      const sphereGrad = ctx.createRadialGradient(cx - radius * 0.3, cy - radius * 0.3, radius * 0.1, cx, cy, radius);
      sphereGrad.addColorStop(0, "#18181b"); // zinc-900
      sphereGrad.addColorStop(0.8, "#09090b"); // zinc-950
      sphereGrad.addColorStop(1, "#030712");
      ctx.fillStyle = sphereGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();

      // Sphere Border
      ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Helper: 3D point projection to screen
      const project = (lat: number, lon: number, altitudeOffset = 0): { x: number; y: number; visible: boolean; z: number } => {
        const phi = (lat * Math.PI) / 180;
        const lambda = (lon * Math.PI) / 180;
        const r = radius + altitudeOffset;

        const x0 = r * Math.cos(phi) * Math.sin(lambda);
        const y0 = -r * Math.sin(phi);
        const z0 = r * Math.cos(phi) * Math.cos(lambda);

        // Rotate around Y-axis (rotY)
        const cosY = Math.cos(rotY);
        const sinY = Math.sin(rotY);
        const x1 = x0 * cosY + z0 * sinY;
        const z1 = -x0 * sinY + z0 * cosY;

        // Rotate around X-axis (rotX)
        const cosX = Math.cos(rotX);
        const sinX = Math.sin(rotX);
        const y2 = y0 * cosX - z1 * sinX;
        const z2 = y0 * sinX + z1 * cosX;

        return {
          x: cx + x1,
          y: cy + y2,
          visible: z2 > 0,
          z: z2,
        };
      };

      // 2. Graticules (Latitude & Longitude grid lines)
      ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
      ctx.lineWidth = 1;

      // Longitude lines every 45 deg
      for (let lon = -180; lon < 180; lon += 45) {
        ctx.beginPath();
        let started = false;
        for (let lat = -80; lat <= 80; lat += 5) {
          const pt = project(lat, lon);
          if (pt.visible) {
            if (!started) {
              ctx.moveTo(pt.x, pt.y);
              started = true;
            } else {
              ctx.lineTo(pt.x, pt.y);
            }
          } else {
            started = false;
          }
        }
        ctx.stroke();
      }

      // Latitude lines every 30 deg
      for (let lat = -60; lat <= 60; lat += 30) {
        ctx.beginPath();
        let started = false;
        for (let lon = -180; lon <= 180; lon += 5) {
          const pt = project(lat, lon);
          if (pt.visible) {
            if (!started) {
              ctx.moveTo(pt.x, pt.y);
              started = true;
            } else {
              ctx.lineTo(pt.x, pt.y);
            }
          } else {
            started = false;
          }
        }
        ctx.stroke();
      }

      // 3. Continent Reference Dots
      ctx.fillStyle = "rgba(161, 161, 170, 0.35)"; // zinc-400 subtle
      for (const [lat, lon] of CONTINENT_DOTS) {
        const pt = project(lat, lon);
        if (pt.visible) {
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 2.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // 4. Arcs (Relations)
      for (const rel of relations) {
        const isSelected = rel.id === selectedRelationId;
        const sourceEp = endpointsById.get(rel.source_endpoint_id);
        const targetEp = endpointsById.get(rel.target_endpoint_id);

        if (!sourceEp?.location || !targetEp?.location) {
          continue; // PRD FR-08: Busur hanya dibuat jika kedua endpoint memiliki lokasi
        }

        const lat1 = sourceEp.location.latitude;
        const lon1 = sourceEp.location.longitude;
        const lat2 = targetEp.location.latitude;
        const lon2 = targetEp.location.longitude;

        // Calculate angular distance for arc altitude
        const dLat = ((lat2 - lat1) * Math.PI) / 180;
        const dLon = ((lon2 - lon1) * Math.PI) / 180;
        const dist = Math.sqrt(dLat * dLat + dLon * dLon);
        const maxAltitude = Math.min(80, Math.max(15, dist * 25));

        const segments = 24;
        const pts: { x: number; y: number; visible: boolean }[] = [];

        for (let i = 0; i <= segments; i++) {
          const t = i / segments;
          const lat = lat1 + (lat2 - lat1) * t;
          const lon = lon1 + (lon2 - lon1) * t;
          const alt = Math.sin(t * Math.PI) * maxAltitude;
          pts.push(project(lat, lon, alt));
        }

        // Draw Arc Line
        ctx.beginPath();
        let drawing = false;
        for (const pt of pts) {
          if (pt.visible) {
            if (!drawing) {
              ctx.moveTo(pt.x, pt.y);
              drawing = true;
            } else {
              ctx.lineTo(pt.x, pt.y);
            }
          } else {
            drawing = false;
          }
        }

        if (isSelected) {
          ctx.strokeStyle = "#38bdf8"; // sky-400
          ctx.lineWidth = 3;
          ctx.shadowColor = "#38bdf8";
          ctx.shadowBlur = 8;
          ctx.stroke();
          ctx.shadowBlur = 0; // reset
        } else {
          ctx.strokeStyle = "rgba(59, 130, 246, 0.65)"; // blue-500
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }

        // Direction Arrow at 65% of arc
        const arrowIdx = Math.floor(segments * 0.65);
        const arrowPt = pts[arrowIdx];
        const nextPt = pts[arrowIdx + 1];
        if (arrowPt?.visible && nextPt?.visible) {
          const angle = Math.atan2(nextPt.y - arrowPt.y, nextPt.x - arrowPt.x);
          ctx.save();
          ctx.translate(arrowPt.x, arrowPt.y);
          ctx.rotate(angle);
          ctx.fillStyle = isSelected ? "#38bdf8" : "#60a5fa";
          ctx.beginPath();
          ctx.moveTo(6, 0);
          ctx.lineTo(-4, -4);
          ctx.lineTo(-4, 4);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
      }

      // 5. Endpoint Pins & Markers
      for (const ep of Array.from(endpointsById.values())) {
        if (!ep.location) continue;

        const pt = project(ep.location.latitude, ep.location.longitude);
        if (!pt.visible) continue;

        const isSource = ep.role === "source";

        if (isSource) {
          // Source: Triangle (Blue)
          ctx.fillStyle = "#3b82f6"; // blue-500
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(pt.x, pt.y - 7);
          ctx.lineTo(pt.x - 6, pt.y + 5);
          ctx.lineTo(pt.x + 6, pt.y + 5);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();

          // Label
          ctx.font = "10px monospace";
          ctx.fillStyle = "#93c5fd";
          ctx.fillText("Source", pt.x + 8, pt.y + 3);
        } else {
          // Target: Circle with center dot (Emerald/Lime)
          ctx.fillStyle = "#10b981"; // emerald-500
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 5, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = "#ffffff";
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 2, 0, Math.PI * 2);
          ctx.fill();

          // Label
          ctx.font = "10px monospace";
          ctx.fillStyle = "#a7f3d0";
          const label = ep.ip || ep.display_name;
          ctx.fillText(label, pt.x + 8, pt.y + 3);
        }
      }
    };

    render();

    // Auto resize handling
    const handleResize = () => {
      if (containerRef.current && canvas) {
        const rect = containerRef.current.getBoundingClientRect();
        canvas.width = rect.width * (window.devicePixelRatio || 1);
        canvas.height = rect.height * (window.devicePixelRatio || 1);
        render();
      }
    };

    handleResize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (animationId) cancelAnimationFrame(animationId);
    };
  }, [rotX, rotY, zoom, endpointsById, relations, selectedRelationId, onWebglError]);

  // Pointer drag controls for smooth 3D rotation
  const handleMouseDown = (e: React.MouseEvent) => {
    isDraggingRef.current = true;
    lastMousePos.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDraggingRef.current) return;
    const dx = e.clientX - lastMousePos.current.x;
    const dy = e.clientY - lastMousePos.current.y;
    lastMousePos.current = { x: e.clientX, y: e.clientY };

    const sensitivity = 0.005;
    setRotY((prev) => prev + dx * sensitivity);
    setRotX((prev) => Math.max(-1.4, Math.min(1.4, prev + dy * sensitivity)));
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  // Touch drag for mobile
  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      isDraggingRef.current = true;
      lastMousePos.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!isDraggingRef.current || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - lastMousePos.current.x;
    const dy = e.touches[0].clientY - lastMousePos.current.y;
    lastMousePos.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };

    const sensitivity = 0.005;
    setRotY((prev) => prev + dx * sensitivity);
    setRotX((prev) => Math.max(-1.4, Math.min(1.4, prev + dy * sensitivity)));
  };

  // Click / Hit detection to select relationship
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const clickX = (e.clientX - rect.left) * (canvas.width / rect.width);
    const clickY = (e.clientY - rect.top) * (canvas.height / rect.height);

    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const radius = Math.min(canvas.width, canvas.height) * 0.38 * zoom;

    // Check click against target endpoint nodes
    for (const ep of Array.from(endpointsById.values())) {
      if (!ep.location) continue;
      const phi = (ep.location.latitude * Math.PI) / 180;
      const lambda = (ep.location.longitude * Math.PI) / 180;
      const x0 = radius * Math.cos(phi) * Math.sin(lambda);
      const y0 = -radius * Math.sin(phi);
      const z0 = radius * Math.cos(phi) * Math.cos(lambda);

      const cosY = Math.cos(rotY);
      const sinY = Math.sin(rotY);
      const x1 = x0 * cosY + z0 * sinY;
      const z1 = -x0 * sinY + z0 * cosY;

      const cosX = Math.cos(rotX);
      const sinX = Math.sin(rotX);
      const y2 = y0 * cosX - z1 * sinX;
      const z2 = y0 * sinX + z1 * cosX;

      if (z2 > 0) {
        const sx = cx + x1;
        const sy = cy + y2;
        const dist = Math.hypot(clickX - sx, clickY - sy);
        if (dist <= 16) {
          // Find relation corresponding to this endpoint
          const matchedRel = relations.find(
            (r) => r.target_endpoint_id === ep.id || r.source_endpoint_id === ep.id
          );
          if (matchedRel) {
            onSelectRelation(matchedRel.id);
            return;
          }
        }
      }
    }
  };

  const handleResetCamera = () => {
    setRotX(0.2);
    setRotY(-1.5);
    setZoom(1.0);
  };

  return (
    <div
      ref={containerRef}
      className="relative w-full h-[420px] bg-zinc-950 rounded-lg overflow-hidden border border-white/5 select-none"
    >
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleMouseUp}
        onClick={handleCanvasClick}
        className="w-full h-full cursor-grab active:cursor-grabbing"
      />

      {/* Camera Controls Overlay */}
      <div className="absolute bottom-3 right-3 flex items-center gap-1.5 bg-zinc-900/80 backdrop-blur border border-white/10 rounded-lg p-1 text-zinc-300">
        <button
          onClick={() => setZoom((z) => Math.min(2.0, z + 0.15))}
          title="Zoom In"
          className="p-1.5 hover:bg-white/10 rounded transition"
        >
          <MagnifyingGlassPlus size={16} />
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.6, z - 0.15))}
          title="Zoom Out"
          className="p-1.5 hover:bg-white/10 rounded transition"
        >
          <MagnifyingGlassMinus size={16} />
        </button>
        {selectedRelationId && (
          <button
            onClick={() => focusRelation(selectedRelationId)}
            title="Focus Selected Relation"
            className="p-1.5 hover:bg-white/10 rounded text-blue-400 transition"
          >
            <Crosshair size={16} />
          </button>
        )}
        <button
          onClick={handleResetCamera}
          title="Reset Camera Orientation"
          className="p-1.5 hover:bg-white/10 rounded transition"
        >
          <ArrowsClockwise size={16} />
        </button>
      </div>

      {/* Floating Visual Legend */}
      <div className="absolute top-3 left-3 bg-zinc-900/80 backdrop-blur border border-white/10 rounded-lg p-2.5 text-[11px] text-zinc-400 space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 inline-block border-b-2 border-r-2 border-blue-500 rotate-45" />
          <span className="text-zinc-200">Sumber (Executor)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
          <span className="text-zinc-200">Target (IP Tujuan)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 bg-blue-500 inline-block" />
          <span>Hubungan Visual (Bukan Rute Paket)</span>
        </div>
      </div>
    </div>
  );
}
