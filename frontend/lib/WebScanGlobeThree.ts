/**
 * WebScanGlobeThree.ts
 * ----------------------------------------------------------------------------
 * Three.js WebGL rendering engine for the SignalScanner 3D Telemetry Globe.
 *
 * Implements the 7 required objectives from the redesign specification:
 *   1. Real-Earth geography from local Natural Earth GeoJSON assets
 *      (ne_110m_land, ne_110m_admin_0_countries, ne_110m_admin_0_boundary_lines).
 *   2. Support for Polygon, MultiPolygon, interior holes (Caspian Sea, Lesotho),
 *      small islands, antimeridian unwrapping, and polar closure.
 *   3. Spherical curvature tessellation with radius stratification:
 *        R_OCEAN  = 100.00 (renderOrder 0)
 *        R_LAND   = 100.32 (renderOrder 1, polygonOffset -1/-1)
 *        R_BORDER = 100.40 (renderOrder 2, LineSegments)
 *        R_COAST  = 100.46 (renderOrder 3, LineSegments)
 *        R_TELEMETRY = 100.32 (renderOrder 4, hexagonal pillars, shockwaves, tubes)
 *   4. Zero Z-fighting via strict shell offsets and depthWrite/polygonOffset management.
 *   5. Preserves all existing features: 3 color modes (severity, http_status, latency),
 *      3 visual presets (hex_matrix, night_ops, wireframe), 3D hexagonal pillars,
 *      shockwave rings, great-circle 3D tube arcs, animated data packet particles,
 *      custom GLSL Fresnel atmosphere shader, telemetry orbit rings, 3D raycasting,
 *      smooth camera fly-to, auto-orbit, and WCAG 2.2 AA keyboard controls.
 *   6. Single merged BufferGeometry batching for land, coastline, and borders.
 *   7. Zero external egress (100% offline static assets, fallback gracefully).
 */

import * as THREE from "three";
import { GeoEndpoint, GeoRelation, Severity } from "@/lib/webScanTypes";
import {
  clusterTargetEndpoints,
  EndpointCluster,
  GlobeColorMode,
  resolveRelationVisualStyle,
  slerpUnitVec3,
  Vec3,
} from "@/lib/globeMath";
import {
  buildGlobeGeometries,
  disposeGlobeGeometries,
  GlobeGeometrySet,
  latLonToVec3,
  R_LAND,
  R_OCEAN,
} from "@/lib/globeGeographyMesh";

export type GlobeVisualPreset = "hex_matrix" | "night_ops" | "wireframe";

export interface WebScanGlobeThreeOptions {
  canvas: HTMLCanvasElement;
  container: HTMLElement;
  endpointsById: Map<string, GeoEndpoint>;
  relations: GeoRelation[];
  selectedRelationId: string | null;
  colorMode: GlobeColorMode;
  visualPreset: GlobeVisualPreset;
  showBorders: boolean;
  autoOrbit: boolean;
  reducedMotion: boolean;
  onSelectRelation: (id: string | null) => void;
  onHoverChange: (
    relationId: string | null,
    clusterKey: string | null,
    clientPos: { x: number; y: number } | null
  ) => void;
  onError?: (err: Error) => void;
}

// Visual preset configurations
const PRESET_STYLES: Record<
  GlobeVisualPreset,
  {
    oceanColor: number;
    oceanEmissive: number;
    oceanRoughness: number;
    oceanMetalness: number;
    landColor: number;
    landEmissive: number;
    landRoughness: number;
    landMetalness: number;
    coastColor: number;
    coastOpacity: number;
    borderColor: number;
    borderOpacity: number;
    atmosphereColor: THREE.Color;
    atmosphereIntensity: number;
    gridOpacity: number;
  }
> = {
  hex_matrix: {
    oceanColor: 0x07090b,
    oceanEmissive: 0x020304,
    oceanRoughness: 0.85,
    oceanMetalness: 0.25,
    landColor: 0x111618,
    landEmissive: 0x040806,
    landRoughness: 0.75,
    landMetalness: 0.35,
    coastColor: 0xa8d94f, // Signal-lime accent
    coastOpacity: 0.72,
    borderColor: 0x5a6560,
    borderOpacity: 0.32,
    atmosphereColor: new THREE.Color(0x38bdf8),
    atmosphereIntensity: 0.55,
    gridOpacity: 0.08,
  },
  night_ops: {
    oceanColor: 0x030406,
    oceanEmissive: 0x010203,
    oceanRoughness: 0.92,
    oceanMetalness: 0.15,
    landColor: 0x0d1117,
    landEmissive: 0x020406,
    landRoughness: 0.88,
    landMetalness: 0.2,
    coastColor: 0x38bdf8, // Sky-blue radar outline
    coastOpacity: 0.65,
    borderColor: 0x334155,
    borderOpacity: 0.28,
    atmosphereColor: new THREE.Color(0x0284c7),
    atmosphereIntensity: 0.45,
    gridOpacity: 0.05,
  },
  wireframe: {
    oceanColor: 0x020304,
    oceanEmissive: 0x000000,
    oceanRoughness: 1.0,
    oceanMetalness: 0.0,
    landColor: 0x0a0e12,
    landEmissive: 0x010204,
    landRoughness: 0.9,
    landMetalness: 0.1,
    coastColor: 0x10b981, // Emerald vector wire
    coastOpacity: 0.85,
    borderColor: 0x047857,
    borderOpacity: 0.45,
    atmosphereColor: new THREE.Color(0x10b981),
    atmosphereIntensity: 0.4,
    gridOpacity: 0.14,
  },
};

// Procedural Hex-Matrix Texture Generator (Zero Egress, memoized in memory)
function createHexMatrixTexture(): THREE.CanvasTexture {
  const size = 512;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = "#090b0c";
    ctx.fillRect(0, 0, size, size);

    // Subtle hexagonal dot grid
    ctx.fillStyle = "rgba(168, 217, 79, 0.06)";
    const s = 16;
    for (let y = 0; y < size; y += s) {
      const offsetX = (Math.floor(y / s) % 2) * (s / 2);
      for (let x = 0; x < size; x += s) {
        ctx.beginPath();
        ctx.arc(x + offsetX, y, 1.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(8, 4);
  return tex;
}

export class WebScanGlobeThree {
  private canvas: HTMLCanvasElement;
  private container: HTMLElement;
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;

  // Root rotation container for Euler XYZ camera orientation
  private globeRoot: THREE.Group;

  // Geometry layers
  private oceanMesh!: THREE.Mesh;
  private landMesh!: THREE.Mesh;
  private coastlineMesh!: THREE.LineSegments;
  private countryBordersMesh!: THREE.LineSegments;
  private atmosphereMesh!: THREE.Mesh;
  private telemetryGroup: THREE.Group;
  private graticuleGroup: THREE.Group;
  private orbitRingsGroup: THREE.Group;

  private geometrySet: GlobeGeometrySet | null = null;
  private hexTexture: THREE.CanvasTexture | null = null;

  // State
  private endpointsById: Map<string, GeoEndpoint>;
  private relations: GeoRelation[];
  private selectedRelationId: string | null;
  private colorMode: GlobeColorMode;
  private visualPreset: GlobeVisualPreset;
  private showBorders: boolean;
  private autoOrbit: boolean;
  private reducedMotion: boolean;

  private onSelectRelation: (id: string | null) => void;
  private onHoverChange: (
    relationId: string | null,
    clusterKey: string | null,
    clientPos: { x: number; y: number } | null
  ) => void;

  // Interaction & camera
  private currentRotX = 0.18;
  private currentRotY = -1.75;
  private targetRotX = 0.18;
  private targetRotY = -1.75;
  private zoom = 1.05;
  private isDragging = false;
  private dragDistance = 0;
  private lastPointerPos = { x: 0, y: 0 };
  private hoveredRelationId: string | null = null;
  private hoveredClusterKey: string | null = null;

  // Animation
  private animPhase = 0;
  private rafId: number | null = null;
  private isDestroyed = false;

  // Raycasting hit targets: pillar meshes & arc tubes
  private raycaster = new THREE.Raycaster();
  private raycastTargets: THREE.Object3D[] = [];

  constructor(opts: WebScanGlobeThreeOptions) {
    this.canvas = opts.canvas;
    this.container = opts.container;
    this.endpointsById = opts.endpointsById;
    this.relations = opts.relations;
    this.selectedRelationId = opts.selectedRelationId;
    this.colorMode = opts.colorMode;
    this.visualPreset = opts.visualPreset;
    this.showBorders = opts.showBorders;
    this.autoOrbit = opts.autoOrbit;
    this.reducedMotion = opts.reducedMotion;
    this.onSelectRelation = opts.onSelectRelation;
    this.onHoverChange = opts.onHoverChange;

    // 1. Initialize WebGL Renderer
    try {
      this.renderer = new THREE.WebGLRenderer({
        canvas: this.canvas,
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.setSize(this.container.clientWidth || 640, this.container.clientHeight || 460);
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    } catch (e) {
      opts.onError?.(e as Error);
      throw e;
    }

    // 2. Scene & Camera
    this.scene = new THREE.Scene();
    const aspect = (this.container.clientWidth || 640) / (this.container.clientHeight || 460);
    this.camera = new THREE.PerspectiveCamera(38, aspect, 10, 2000);
    this.camera.position.set(0, 0, 285 / this.zoom);
    this.camera.lookAt(0, 0, 0);

    // 3. Globe Root Container with Euler XYZ
    this.globeRoot = new THREE.Group();
    this.globeRoot.rotation.order = "XYZ";
    this.scene.add(this.globeRoot);

    // 4. Sub-groups
    this.telemetryGroup = new THREE.Group();
    this.telemetryGroup.renderOrder = 4;
    this.globeRoot.add(this.telemetryGroup);

    this.graticuleGroup = new THREE.Group();
    this.graticuleGroup.renderOrder = 0;
    this.globeRoot.add(this.graticuleGroup);

    this.orbitRingsGroup = new THREE.Group();
    this.scene.add(this.orbitRingsGroup);

    // 5. Lighting
    this.setupLighting();

    // 6. Base Sphere & Atmosphere
    this.setupBaseSphereAndAtmosphere();
    this.setupGraticules();
    this.setupOrbitRings();

    // 7. Event listeners
    this.setupEventListeners();

    // 8. Start rendering loop
    this.startAnimationLoop();
  }

  private setupLighting(): void {
    // Balanced studio lighting: key directional light + soft ambient
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.15);
    this.scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 2.2);
    dirLight1.position.set(200, 150, 300);
    this.scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x38bdf8, 0.85);
    dirLight2.position.set(-200, -100, -200);
    this.scene.add(dirLight2);
  }

  private setupBaseSphereAndAtmosphere(): void {
    const style = PRESET_STYLES[this.visualPreset];
    this.hexTexture = createHexMatrixTexture();

    // 1. Ocean Sphere (R = 100.00, renderOrder = 0)
    const oceanGeom = new THREE.SphereGeometry(R_OCEAN, 64, 48);
    const oceanMat = new THREE.MeshStandardMaterial({
      color: style.oceanColor,
      emissive: style.oceanEmissive,
      roughness: style.oceanRoughness,
      metalness: style.oceanMetalness,
      map: this.hexTexture,
    });
    this.oceanMesh = new THREE.Mesh(oceanGeom, oceanMat);
    this.oceanMesh.renderOrder = 0;
    this.globeRoot.add(this.oceanMesh);

    // 2. Custom GLSL Fresnel Atmosphere Shader
    const atmosphereGeom = new THREE.SphereGeometry(R_OCEAN * 1.14, 64, 48);
    const atmosphereMat = new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vPosition;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        uniform float uIntensity;
        varying vec3 vNormal;
        varying vec3 vPosition;
        void main() {
          vec3 viewDir = normalize(-vPosition);
          float fresnel = dot(viewDir, vNormal);
          fresnel = clamp(1.0 - fresnel, 0.0, 1.0);
          float glow = pow(fresnel, 2.8) * uIntensity;
          gl_FragColor = vec4(uColor, glow);
        }
      `,
      uniforms: {
        uColor: { value: style.atmosphereColor },
        uIntensity: { value: style.atmosphereIntensity },
      },
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false,
    });
    this.atmosphereMesh = new THREE.Mesh(atmosphereGeom, atmosphereMat);
    this.scene.add(this.atmosphereMesh);
  }

  private setupGraticules(): void {
    const DEG = Math.PI / 180;
    const points: THREE.Vector3[] = [];

    // Equator with highlighted signal accent
    for (let lon = -180; lon < 180; lon += 3) {
      const p1 = latLonToVec3(0, lon, R_OCEAN + 0.08);
      const p2 = latLonToVec3(0, lon + 3, R_OCEAN + 0.08);
      points.push(p1, p2);
    }

    // Parallels every 30 deg
    for (const lat of [-60, -30, 30, 60]) {
      for (let lon = -180; lon < 180; lon += 4) {
        const p1 = latLonToVec3(lat, lon, R_OCEAN + 0.08);
        const p2 = latLonToVec3(lat, lon + 4, R_OCEAN + 0.08);
        points.push(p1, p2);
      }
    }

    // Meridians every 30 deg
    for (let lon = -180; lon < 180; lon += 30) {
      for (let lat = -80; lat < 80; lat += 4) {
        const p1 = latLonToVec3(lat, lon, R_OCEAN + 0.08);
        const p2 = latLonToVec3(lat + 4, lon, R_OCEAN + 0.08);
        points.push(p1, p2);
      }
    }

    const geom = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({
      color: 0x78837f,
      transparent: true,
      opacity: 0.12,
      depthWrite: false,
    });
    const graticules = new THREE.LineSegments(geom, mat);
    graticules.renderOrder = 0;
    this.graticuleGroup.add(graticules);
  }

  private setupOrbitRings(): void {
    // Subtle telemetry compass / orbit calibration ring around the globe
    const curve = new THREE.EllipseCurve(0, 0, R_OCEAN * 1.35, R_OCEAN * 1.35, 0, Math.PI * 2, false, 0);
    const pts = curve.getPoints(128).map((p) => new THREE.Vector3(p.x, 0, p.y));
    const geom = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.18,
      depthWrite: false,
    });
    const ring = new THREE.Line(geom, mat);
    ring.rotation.x = Math.PI * 0.22;
    ring.rotation.z = Math.PI * 0.08;
    this.orbitRingsGroup.add(ring);
  }

  /**
   * Applies the tessellated Real-Earth geometry set.
   * Merges landMesh, coastlineMesh, and countryBordersMesh into single geometries.
   */
  public applyGeometries(geometries: GlobeGeometrySet): void {
    if (this.geometrySet) {
      disposeGlobeGeometries(this.geometrySet);
    }
    this.geometrySet = geometries;

    const style = PRESET_STYLES[this.visualPreset];

    // 1. Merged Land Mesh (R = 100.32, renderOrder = 1, polygonOffset -1/-1)
    if (this.landMesh) {
      this.globeRoot.remove(this.landMesh);
      this.landMesh.geometry.dispose();
      (this.landMesh.material as THREE.Material).dispose();
    }
    const landMat = new THREE.MeshStandardMaterial({
      color: style.landColor,
      emissive: style.landEmissive,
      roughness: style.landRoughness,
      metalness: style.landMetalness,
      polygonOffset: true,
      polygonOffsetFactor: -1,
      polygonOffsetUnits: -1,
    });
    this.landMesh = new THREE.Mesh(geometries.land, landMat);
    this.landMesh.renderOrder = 1;
    this.globeRoot.add(this.landMesh);

    // 2. Merged Country Borders (R = 100.40, renderOrder = 2)
    if (this.countryBordersMesh) {
      this.globeRoot.remove(this.countryBordersMesh);
      this.countryBordersMesh.geometry.dispose();
      (this.countryBordersMesh.material as THREE.Material).dispose();
    }
    if (geometries.borders) {
      const borderMat = new THREE.LineBasicMaterial({
        color: style.borderColor,
        transparent: true,
        opacity: style.borderOpacity,
        depthWrite: false,
      });
      this.countryBordersMesh = new THREE.LineSegments(geometries.borders, borderMat);
      this.countryBordersMesh.renderOrder = 2;
      this.countryBordersMesh.visible = this.showBorders;
      this.globeRoot.add(this.countryBordersMesh);
    }

    // 3. Merged Coastlines (R = 100.46, renderOrder = 3)
    if (this.coastlineMesh) {
      this.globeRoot.remove(this.coastlineMesh);
      this.coastlineMesh.geometry.dispose();
      (this.coastlineMesh.material as THREE.Material).dispose();
    }
    const coastMat = new THREE.LineBasicMaterial({
      color: style.coastColor,
      transparent: true,
      opacity: style.coastOpacity,
      depthWrite: false,
    });
    this.coastlineMesh = new THREE.LineSegments(geometries.coastline, coastMat);
    this.coastlineMesh.renderOrder = 3;
    this.globeRoot.add(this.coastlineMesh);
  }

  /**
   * Rebuilds 3D telemetry overlays:
   *   - Hexagonal pillars for target clusters (proportional to log2(record_count))
   *   - Shockwave radar ripple rings for active findings
   *   - Source executor tripod
   *   - 3D Great-Circle Slerp tube arcs with parabolic altitude profile
   *   - Floating 3D data packet pulse particles
   */
  public updateTelemetry(
    endpointsById: Map<string, GeoEndpoint>,
    relations: GeoRelation[],
    selectedRelationId: string | null,
    colorMode: GlobeColorMode,
    findings: { id: string; severity: Severity }[]
  ): void {
    this.endpointsById = endpointsById;
    this.relations = relations;
    this.selectedRelationId = selectedRelationId;
    this.colorMode = colorMode;

    // Clear old telemetry meshes
    while (this.telemetryGroup.children.length > 0) {
      const obj = this.telemetryGroup.children[0];
      this.telemetryGroup.remove(obj);
      if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose();
      if ((obj as THREE.Mesh).material) {
        const mat = (obj as THREE.Mesh).material;
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else mat.dispose();
      }
    }
    this.raycastTargets = [];

    const findingSeveritiesById = new Map<string, Severity>();
    for (const f of findings) {
      findingSeveritiesById.set(f.id, f.severity);
    }

    const clusters = clusterTargetEndpoints(relations, endpointsById, findingSeveritiesById);

    // 1. Target Clusters: Hexagonal Pillars + Radar Rings
    for (const cluster of clusters) {
      const relIds = cluster.relations.map((r) => r.id);
      const isSelected = selectedRelationId !== null && relIds.includes(selectedRelationId);
      const isHovered =
        this.hoveredClusterKey === cluster.clusterKey ||
        (this.hoveredRelationId !== null && relIds.includes(this.hoveredRelationId));

      const primaryRel = cluster.relations[0];
      const style = resolveRelationVisualStyle(primaryRel, colorMode, findingSeveritiesById);

      const surfacePos = latLonToVec3(cluster.latitude, cluster.longitude, R_LAND);
      const height = Math.min(22, 4 + Math.log2(cluster.totalRecords + 1) * 3.5);
      const pillarRadius = isSelected || isHovered ? 2.6 : 1.8;

      // Hexagonal cylinder pillar (6 radial segments)
      const pillarGeom = new THREE.CylinderGeometry(pillarRadius, pillarRadius * 0.8, height, 6);
      pillarGeom.translate(0, height / 2, 0); // Ground at base
      const pillarMat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(style.stroke),
        emissive: new THREE.Color(style.stroke),
        emissiveIntensity: isSelected || isHovered ? 0.9 : 0.45,
        roughness: 0.3,
        metalness: 0.8,
        transparent: true,
        opacity: 0.92,
      });

      const pillarMesh = new THREE.Mesh(pillarGeom, pillarMat);
      pillarMesh.position.copy(surfacePos);
      pillarMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), surfacePos.clone().normalize());
      pillarMesh.userData = {
        type: "cluster",
        clusterKey: cluster.clusterKey,
        relationIds: relIds,
        primaryRelationId: primaryRel.id,
      };

      this.telemetryGroup.add(pillarMesh);
      this.raycastTargets.push(pillarMesh);

      // Radar Shockwave Ring around base
      const ringGeom = new THREE.RingGeometry(pillarRadius * 1.5, pillarRadius * 2.2, 32);
      const ringMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(style.stroke),
        transparent: true,
        opacity: isSelected || isHovered ? 0.8 : 0.4,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const ringMesh = new THREE.Mesh(ringGeom, ringMat);
      ringMesh.position.copy(surfacePos.clone().multiplyScalar(1.002));
      ringMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), surfacePos.clone().normalize());
      this.telemetryGroup.add(ringMesh);
    }

    // 2. Source Executor: Blue Tripod Pin
    const sourceEndpoints = Array.from(endpointsById.values()).filter(
      (ep) => ep.role === "source" && ep.location
    );
    for (const srcEp of sourceEndpoints) {
      if (!srcEp.location) continue;
      const srcPos = latLonToVec3(srcEp.location.latitude, srcEp.location.longitude, R_LAND);
      const coneGeom = new THREE.ConeGeometry(2.2, 7, 4);
      coneGeom.translate(0, 3.5, 0);
      const coneMat = new THREE.MeshStandardMaterial({
        color: 0x3b82f6,
        emissive: 0x1d4ed8,
        emissiveIntensity: 0.8,
        roughness: 0.3,
      });
      const coneMesh = new THREE.Mesh(coneGeom, coneMat);
      coneMesh.position.copy(srcPos);
      coneMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), srcPos.clone().normalize());
      this.telemetryGroup.add(coneMesh);
    }

    // 3. Great-Circle 3D Slerp Tubes & Data Packet Pulses
    for (const rel of relations) {
      const srcEp = endpointsById.get(rel.source_endpoint_id);
      const tgtEp = endpointsById.get(rel.target_endpoint_id);
      if (!srcEp?.location || !tgtEp?.location) continue;

      const isSelected = rel.id === selectedRelationId;
      const isHovered = rel.id === this.hoveredRelationId;
      const style = resolveRelationVisualStyle(rel, colorMode, findingSeveritiesById);

      // Great-Circle Curve with Parabolic Altitude Profile
      const curvePoints = this.buildCurvePoints(
        srcEp.location.latitude,
        srcEp.location.longitude,
        tgtEp.location.latitude,
        tgtEp.location.longitude,
        48
      );

      const curve = new THREE.CatmullRomCurve3(curvePoints);
      const tubeRadius = isSelected || isHovered ? 0.75 : 0.42;
      const tubeGeom = new THREE.TubeGeometry(curve, 48, tubeRadius, 6, false);
      const tubeMat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(style.stroke),
        emissive: new THREE.Color(style.stroke),
        emissiveIntensity: isSelected || isHovered ? 0.85 : 0.35,
        transparent: true,
        opacity: isSelected || isHovered ? 0.95 : 0.72,
        roughness: 0.4,
      });

      const tubeMesh = new THREE.Mesh(tubeGeom, tubeMat);
      tubeMesh.userData = {
        type: "relation",
        relationId: rel.id,
      };

      this.telemetryGroup.add(tubeMesh);
      this.raycastTargets.push(tubeMesh);

      // Packet Pulse Sphere
      const packetCount = Math.min(3, Math.max(1, Math.ceil(Math.log10(rel.record_count + 1))));
      for (let pIdx = 0; pIdx < packetCount; pIdx++) {
        const progress = this.reducedMotion
          ? 0.65
          : (this.animPhase * style.pulseSpeed + pIdx / packetCount) % 1;
        const pt = curve.getPointAt(progress);

        const packetGeom = new THREE.SphereGeometry(isSelected || isHovered ? 1.4 : 0.9, 12, 12);
        const packetMat = new THREE.MeshBasicMaterial({
          color: 0xffffff,
          transparent: true,
          opacity: 0.95,
        });
        const packetMesh = new THREE.Mesh(packetGeom, packetMat);
        packetMesh.position.copy(pt);
        this.telemetryGroup.add(packetMesh);
      }
    }
  }

  private buildCurvePoints(
    lat1: number,
    lon1: number,
    lat2: number,
    lon2: number,
    segments = 48
  ): THREE.Vector3[] {
    const DEG = Math.PI / 180;
    const phi1 = lat1 * DEG;
    const lam1 = lon1 * DEG;
    const phi2 = lat2 * DEG;
    const lam2 = lon2 * DEG;

    const v1: Vec3 = {
      x: Math.cos(phi1) * Math.sin(lam1),
      y: Math.sin(phi1),
      z: Math.cos(phi1) * Math.cos(lam1),
    };
    const v2: Vec3 = {
      x: Math.cos(phi2) * Math.sin(lam2),
      y: Math.sin(phi2),
      z: Math.cos(phi2) * Math.cos(lam2),
    };

    const dot = Math.max(-1, Math.min(1, v1.x * v2.x + v1.y * v2.y + v1.z * v2.z));
    const omega = Math.acos(dot);
    const maxAltitude = Math.min(R_LAND * 0.32, Math.max(R_LAND * 0.06, R_LAND * 0.24 * (omega / Math.PI)));

    const pts: THREE.Vector3[] = [];
    for (let i = 0; i <= segments; i++) {
      const t = i / segments;
      const { point } = slerpUnitVec3(v1, v2, t);
      const alt = 4 * t * (1 - t) * maxAltitude;
      const r = R_LAND + alt;
      pts.push(new THREE.Vector3(point.x * r, point.y * r, point.z * r));
    }
    return pts;
  }

  // Visual Preset Switcher
  public setVisualPreset(preset: GlobeVisualPreset): void {
    if (this.visualPreset === preset) return;
    this.visualPreset = preset;
    const style = PRESET_STYLES[preset];

    if (this.oceanMesh) {
      const m = this.oceanMesh.material as THREE.MeshStandardMaterial;
      m.color.setHex(style.oceanColor);
      m.emissive.setHex(style.oceanEmissive);
      m.roughness = style.oceanRoughness;
      m.metalness = style.oceanMetalness;
    }
    if (this.landMesh) {
      const m = this.landMesh.material as THREE.MeshStandardMaterial;
      m.color.setHex(style.landColor);
      m.emissive.setHex(style.landEmissive);
      m.roughness = style.landRoughness;
      m.metalness = style.landMetalness;
    }
    if (this.coastlineMesh) {
      const m = this.coastlineMesh.material as THREE.LineBasicMaterial;
      m.color.setHex(style.coastColor);
      m.opacity = style.coastOpacity;
    }
    if (this.countryBordersMesh) {
      const m = this.countryBordersMesh.material as THREE.LineBasicMaterial;
      m.color.setHex(style.borderColor);
      m.opacity = style.borderOpacity;
    }
    if (this.atmosphereMesh) {
      const m = this.atmosphereMesh.material as THREE.ShaderMaterial;
      m.uniforms.uColor.value = style.atmosphereColor;
      m.uniforms.uIntensity.value = style.atmosphereIntensity;
    }
  }

  // Country Borders Toggle
  public setBordersVisible(visible: boolean): void {
    this.showBorders = visible;
    if (this.countryBordersMesh) {
      this.countryBordersMesh.visible = visible;
    }
  }

  // Camera Fly-To (Euler XYZ: rotY = -lonRad, rotX = latRad)
  public flyTo(latDeg: number, lonDeg: number): void {
    const DEG = Math.PI / 180;
    this.targetRotY = -lonDeg * DEG;
    this.targetRotX = latDeg * DEG;

    if (this.reducedMotion) {
      this.currentRotY = this.targetRotY;
      this.currentRotX = this.targetRotX;
    }
  }

  // Region Jumps
  public jumpToRegion(region: "nusantara" | "asia_pacific" | "europe" | "americas"): void {
    switch (region) {
      case "nusantara":
        this.flyTo(-2.5, 118.0);
        break;
      case "asia_pacific":
        this.flyTo(15.0, 120.0);
        break;
      case "europe":
        this.flyTo(50.0, 15.0);
        break;
      case "americas":
        this.flyTo(25.0, -90.0);
        break;
    }
  }

  /**
   * Keyboard/gamepad rotation nudge. `dYaw` is added to the yaw target and
   * `dPitch` to the pitch target (clamped to +-1.4 rad so the pole never flips).
   */
  public setRotationTargetDelta(dYaw: number, dPitch: number): void {
    this.targetRotY += dYaw;
    if (dPitch !== 0) {
      this.targetRotX = Math.max(-1.4, Math.min(1.4, this.targetRotX + dPitch));
    }
  }

  public setZoom(zoom: number): void {
    this.zoom = Math.max(0.65, Math.min(2.4, zoom));
    this.camera.position.z = 285 / this.zoom;
  }

  public getZoom(): number {
    return this.zoom;
  }

  public setAutoOrbit(orbit: boolean): void {
    this.autoOrbit = orbit;
  }

  public resetCamera(): void {
    this.targetRotX = 0.18;
    this.targetRotY = -1.75;
    this.setZoom(1.05);
    if (this.reducedMotion) {
      this.currentRotX = 0.18;
      this.currentRotY = -1.75;
    }
  }

  public resize(width: number, height: number): void {
    if (width <= 0 || height <= 0) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  // Pointer & Raycasting
  private setupEventListeners(): void {
    const canvas = this.canvas;

    const onPointerDown = (e: MouseEvent) => {
      this.isDragging = true;
      this.dragDistance = 0;
      this.lastPointerPos = { x: e.clientX, y: e.clientY };
    };

    const onPointerMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const mouseX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const mouseY = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      if (this.isDragging) {
        const dx = e.clientX - this.lastPointerPos.x;
        const dy = e.clientY - this.lastPointerPos.y;
        this.dragDistance += Math.hypot(dx, dy);
        this.lastPointerPos = { x: e.clientX, y: e.clientY };

        const sensitivity = 0.005;
        this.targetRotY += dx * sensitivity;
        this.targetRotX = Math.max(-1.4, Math.min(1.4, this.targetRotX + dy * sensitivity));

        this.onHoverChange(null, null, null);
        return;
      }

      // 3D Raycasting
      this.raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), this.camera);
      const intersects = this.raycaster.intersectObjects(this.raycastTargets, false);

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const data = hit.userData;
        if (data.type === "cluster") {
          this.hoveredRelationId = data.primaryRelationId;
          this.hoveredClusterKey = data.clusterKey;
          this.onHoverChange(data.primaryRelationId, data.clusterKey, {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
          });
          canvas.style.cursor = "pointer";
          return;
        }
        if (data.type === "relation") {
          this.hoveredRelationId = data.relationId;
          this.hoveredClusterKey = null;
          this.onHoverChange(data.relationId, null, {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
          });
          canvas.style.cursor = "pointer";
          return;
        }
      }

      if (this.hoveredRelationId !== null || this.hoveredClusterKey !== null) {
        this.hoveredRelationId = null;
        this.hoveredClusterKey = null;
        this.onHoverChange(null, null, null);
        canvas.style.cursor = "grab";
      }
    };

    const onPointerUp = () => {
      this.isDragging = false;
    };

    const onPointerLeave = () => {
      this.isDragging = false;
      this.hoveredRelationId = null;
      this.hoveredClusterKey = null;
      this.onHoverChange(null, null, null);
    };

    const onClick = (e: MouseEvent) => {
      if (this.dragDistance > 6) return;
      const rect = canvas.getBoundingClientRect();
      const mouseX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const mouseY = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      this.raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), this.camera);
      const intersects = this.raycaster.intersectObjects(this.raycastTargets, false);

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const data = hit.userData;
        const relId = data.type === "cluster" ? data.primaryRelationId : data.relationId;
        if (relId) {
          this.onSelectRelation(relId === this.selectedRelationId ? null : relId);
        }
      }
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.12 : -0.12;
      this.setZoom(this.zoom + delta);
    };

    canvas.addEventListener("mousedown", onPointerDown);
    window.addEventListener("mousemove", onPointerMove);
    window.addEventListener("mouseup", onPointerUp);
    canvas.addEventListener("mouseleave", onPointerLeave);
    canvas.addEventListener("click", onClick);
    canvas.addEventListener("wheel", onWheel, { passive: false });

    (this as any)._cleanupHandlers = () => {
      canvas.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("mousemove", onPointerMove);
      window.removeEventListener("mouseup", onPointerUp);
      canvas.removeEventListener("mouseleave", onPointerLeave);
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("wheel", onWheel);
    };
  }

  // Animation Loop
  private startAnimationLoop(): void {
    let lastTime = performance.now();

    const renderFrame = (now: number) => {
      if (this.isDestroyed) return;

      const dt = (now - lastTime) / 1000;
      lastTime = now;
      this.animPhase = (this.animPhase + dt) % 1000;

      // Auto-Orbit
      if (this.autoOrbit && !this.isDragging) {
        this.targetRotY += dt * 0.16;
      }

      // Smooth camera dampening (Euler XYZ)
      if (this.reducedMotion) {
        this.currentRotX = this.targetRotX;
        this.currentRotY = this.targetRotY;
      } else {
        const factor = Math.min(1, dt * 10);
        let dy = ((this.targetRotY - this.currentRotY + Math.PI) % (Math.PI * 2)) - Math.PI;
        if (dy < -Math.PI) dy += Math.PI * 2;
        this.currentRotY += dy * factor;
        this.currentRotX += (this.targetRotX - this.currentRotX) * factor;
      }

      this.globeRoot.rotation.x = this.currentRotX;
      this.globeRoot.rotation.y = this.currentRotY;

      // Gentle counter-drift on outer telemetry ring
      if (!this.reducedMotion) {
        this.orbitRingsGroup.rotation.y -= dt * 0.05;
      }

      this.renderer.render(this.scene, this.camera);
      this.rafId = requestAnimationFrame(renderFrame);
    };

    this.rafId = requestAnimationFrame(renderFrame);
  }

  public destroy(): void {
    this.isDestroyed = true;
    if (this.rafId) cancelAnimationFrame(this.rafId);
    if ((this as any)._cleanupHandlers) (this as any)._cleanupHandlers();

    if (this.geometrySet) disposeGlobeGeometries(this.geometrySet);
    if (this.hexTexture) this.hexTexture.dispose();

    this.renderer.dispose();
  }
}
