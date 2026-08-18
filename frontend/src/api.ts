import type {
  Edge,
  HitRatioTimeseriesPoint,
  LatencyRow,
  OriginFile,
  OriginStatus,
  RegionChoice,
  RequestLogRow,
  TopFile,
} from "./types";

const LB_URL = import.meta.env.VITE_LB_URL ?? "http://localhost:8080";

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${LB_URL}${path}`);
  if (!resp.ok) throw new Error(`${path} -> ${resp.status}`);
  return resp.json() as Promise<T>;
}

export const api = {
  base: LB_URL,
  edges: () => getJSON<Edge[]>("/edges"),
  origin: () => getJSON<OriginStatus>("/origin"),
  regions: () => getJSON<{ geoip_enabled: boolean; regions: RegionChoice[] }>("/regions"),
  files: () => getJSON<OriginFile[]>("/dashboard/files"),
  uploadFile: async (file: File, key?: string): Promise<OriginFile> => {
    const form = new FormData();
    form.append("upload", file);
    const q = key ? `?key=${encodeURIComponent(key)}` : "";
    const resp = await fetch(`${LB_URL}/dashboard/files${q}`, { method: "POST", body: form });
    if (!resp.ok) throw new Error(`upload failed (${resp.status}): ${await resp.text()}`);
    return resp.json() as Promise<OriginFile>;
  },
  deleteFile: async (key: string): Promise<void> => {
    const resp = await fetch(`${LB_URL}/dashboard/files/${encodeURIComponent(key)}`, { method: "DELETE" });
    if (!resp.ok) throw new Error(`delete failed (${resp.status}): ${await resp.text()}`);
  },
  recentLogs: (sinceId = 0, limit = 50) =>
    getJSON<RequestLogRow[]>(`/dashboard/logs/recent?since_id=${sinceId}&limit=${limit}`),
  hitRatio: () => getJSON<{ counts: Record<string, number>; total: number; hit_ratio: number }>("/dashboard/stats/hit-ratio"),
  hitRatioTimeseries: () => getJSON<HitRatioTimeseriesPoint[]>("/dashboard/stats/hit-ratio-timeseries"),
  latency: () => getJSON<LatencyRow[]>("/dashboard/stats/latency"),
  topFiles: (limit = 10) => getJSON<TopFile[]>(`/dashboard/stats/top-files?limit=${limit}`),
  edgeRequests: () => getJSON<{ edge: string; region: string; requests: number }[]>("/dashboard/stats/edge-requests"),
  streamUrl: () => `${LB_URL}/dashboard/stream`,
  fetchFile: (key: string, region?: string) => {
    const q = region ? `?region=${encodeURIComponent(region)}` : "";
    return fetch(`${LB_URL}/fetch/${encodeURIComponent(key)}${q}`);
  },
};

// The region list is served by the load balancer (GET /regions), not duplicated
// here — it resolves each choice through the same rank_edges() the real /fetch
// path uses, so the dropdown can't promise a route that routing wouldn't take.
