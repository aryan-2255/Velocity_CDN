export interface EdgeLive {
  status?: string;
  cache_policy?: string;
  occupancy_bytes?: number;
  occupancy_pct?: number;
  entry_count?: number;
  hit_ratio?: number;
  hits?: number;
  misses?: number;
  stale_serves?: number;
  errors?: number;
}

export interface Edge {
  id: string;
  name: string;
  region: string;
  base_url: string;
  lat: number | null;
  lon: number | null;
  status: string;
  cache_policy: string;
  live: EdgeLive;
}

export interface RequestLogRow {
  id: number;
  request_id: string;
  ts: string;
  client_ip: string | null;
  resolved_region: string | null;
  resolution_method: string | null;
  edge_id: string | null;
  file_key: string | null;
  cache_result: "hit" | "miss" | "stale" | "error" | null;
  latency_ms: number | null;
  status_code: number | null;
  bytes_served: number | null;
}

export interface LatencyRow {
  cache_result: string | null;
  region: string | null;
  avg_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  count: number;
}

export interface HitRatioTimeseriesPoint {
  ts: string;
  hit_ratio: number;
  total: number;
}

export interface TopFile {
  file_key: string;
  requests: number;
}

export interface OriginStatus {
  reachable: boolean;
  status: string;
  db?: boolean;
  s3?: boolean;
  region?: string;
  bucket?: string;
  file_count?: number | null;
  total_bytes?: number | null;
  error?: string;
}

export interface OriginFile {
  id: string;
  key: string;
  size_bytes: number;
  content_type: string;
  checksum: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface RegionChoice {
  value: string;
  label: string;
  lat: number;
  lon: number;
  nearest_edge: string | null;
  distance_km: number | null;
  has_local_edge: boolean;
}
