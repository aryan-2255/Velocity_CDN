// Fixed categorical assignment for cache_result — never cycled, reused everywhere
// this dimension appears (live feed badges, latency chart) so identity stays
// consistent across the dashboard. Slots pulled from the dataviz skill's
// validated categorical order (references/palette.md): 1=blue, 2=orange,
// 3=aqua, 8=red — non-contiguous by design, red reserved for the failure case.
const CACHE_RESULT_COLORS: Record<string, string> = {
  hit: "var(--series-1)",
  miss: "var(--series-2)",
  stale: "var(--series-3)",
  error: "var(--series-8)",
};

export function cacheResultColor(result: string | null | undefined): string {
  return CACHE_RESULT_COLORS[result ?? ""] ?? "var(--text-muted)";
}

export const CACHE_RESULT_ORDER = ["hit", "miss", "stale", "error"] as const;

export function statusColor(status: string | null | undefined): string {
  switch (status) {
    case "healthy":
      return "var(--status-good)";
    case "unhealthy":
      return "var(--status-critical)";
    default:
      return "var(--text-muted)"; // unknown | disabled
  }
}
