import { create } from "zustand";
import {
  ScanFinding,
  ScanJob,
  ScanObservation,
  ScanSnapshot,
  WebScanEvent,
} from "./webScanTypes";

export interface WebScanStore {
  activeJob: ScanJob | null;
  snapshot: ScanSnapshot | null;
  findings: ScanFinding[];
  observations: ScanObservation[];
  events: WebScanEvent[];
  isScanning: boolean;
  progressPercent: number;
  currentModule: string | null;
  selectedFinding: ScanFinding | null;
  error: string | null;
  history: ScanJob[];
  historyTotal: number;

  setActiveJob: (job: ScanJob | null) => void;
  setSnapshot: (snapshot: ScanSnapshot | null) => void;
  setFindings: (findings: ScanFinding[]) => void;
  upsertFinding: (finding: ScanFinding) => void;
  addObservation: (obs: ScanObservation) => void;
  addEvent: (event: WebScanEvent) => void;
  setProgress: (percent: number, moduleName?: string) => void;
  setSelectedFinding: (finding: ScanFinding | null) => void;
  setError: (err: string | null) => void;
  setHistory: (jobs: ScanJob[], total: number) => void;
  reset: () => void;
}

export const useWebScanStore = create<WebScanStore>((set) => ({
  activeJob: null,
  snapshot: null,
  findings: [],
  observations: [],
  events: [],
  isScanning: false,
  progressPercent: 0,
  currentModule: null,
  selectedFinding: null,
  error: null,
  history: [],
  historyTotal: 0,

  setActiveJob: (job) =>
    set((state) => {
      const isScan = job?.status ? ["pending", "queued", "scanning"].includes(job.status) : false;
      return {
        activeJob: job,
        isScanning: isScan,
        progressPercent: job?.status === "completed" ? 100 : state.progressPercent,
        error: null,
      };
    }),

  setSnapshot: (snapshot) =>
    set((state) => {
      const isScan = snapshot?.job?.status ? ["pending", "queued", "scanning"].includes(snapshot.job.status) : false;
      return {
        snapshot,
        activeJob: snapshot ? snapshot.job : state.activeJob,
        isScanning: isScan,
        progressPercent: snapshot?.job?.status === "completed" ? 100 : state.progressPercent,
      };
    }),

  setFindings: (findings) => set({ findings }),

  upsertFinding: (finding) =>
    set((state) => {
      const idx = state.findings.findIndex((f) => f.fingerprint === finding.fingerprint);
      if (idx >= 0) {
        const next = [...state.findings];
        next[idx] = finding;
        return { findings: next };
      }
      return { findings: [finding, ...state.findings] };
    }),

  addObservation: (obs) =>
    set((state) => ({
      observations: [obs, ...state.observations].slice(0, 300),
    })),

  addEvent: (event) =>
    set((state) => ({
      events: [...state.events, event].slice(-500),
    })),

  setProgress: (percent, moduleName) =>
    set((state) => ({
      progressPercent:
        typeof percent === "number" && !isNaN(percent)
          ? Math.min(100, Math.max(0, percent))
          : state.progressPercent,
      currentModule: moduleName !== undefined ? moduleName : state.currentModule,
    })),

  setSelectedFinding: (finding) => set({ selectedFinding: finding }),

  setError: (error) => set({ error }),

  setHistory: (history, historyTotal) => set({ history, historyTotal }),

  reset: () =>
    set({
      activeJob: null,
      snapshot: null,
      findings: [],
      observations: [],
      events: [],
      isScanning: false,
      progressPercent: 0,
      currentModule: null,
      selectedFinding: null,
      error: null,
    }),
}));
