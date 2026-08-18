import { useEffect, useState } from "react";
import { api } from "../api";
import { statusColor } from "../colors";
import type { Edge, OriginStatus } from "../types";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function EdgeHealthPanel() {
  const [edges, setEdges] = useState<Edge[]>([]);
  const [origin, setOrigin] = useState<OriginStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const [edgeData, originData] = await Promise.all([api.edges(), api.origin()]);
        if (!cancelled) {
          setEdges(edgeData);
          setOrigin(originData);
        }
      } catch {
        // LB or origin briefly unreachable — keep showing the last known state
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <h2 className="mb-3 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        Infrastructure
      </h2>

      {/* Origin sits above the edges because that's the direction a cache miss
          travels — edges fall back to it, never the other way around. */}
      <OriginRow origin={origin} />

      <div
        className="mb-2 mt-3 border-t pt-3 text-[11px] uppercase tracking-wide"
        style={{ borderColor: "var(--gridline)", color: "var(--text-muted)" }}
      >
        Edges — serve clients, fall back to origin on miss
      </div>

      <div className="space-y-3">
        {edges.length === 0 && (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            No edges registered yet.
          </p>
        )}
        {edges.map((edge) => {
          const pct = edge.live?.occupancy_pct ?? 0;
          const hitRatio = edge.live?.hit_ratio;
          return (
            <div key={edge.id} className="text-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: statusColor(edge.status) }}
                  />
                  <span style={{ color: "var(--text-primary)" }}>{edge.name}</span>
                  <span style={{ color: "var(--text-muted)" }}>({edge.region})</span>
                </div>
                <span style={{ color: statusColor(edge.status) }}>{edge.status}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="h-1.5 flex-1 rounded-full" style={{ background: "var(--gridline)" }}>
                  <div
                    className="h-1.5 rounded-full"
                    style={{ width: `${Math.min(pct * 100, 100)}%`, background: "var(--series-1)" }}
                  />
                </div>
                <span className="tabular-nums" style={{ color: "var(--text-secondary)" }}>
                  {(pct * 100).toFixed(0)}%
                </span>
              </div>
              <div className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
                policy: {edge.cache_policy}
                {hitRatio !== undefined && ` · hit ratio: ${(hitRatio * 100).toFixed(0)}%`}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function OriginRow({ origin }: { origin: OriginStatus | null }) {
  if (!origin) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Checking origin…
      </p>
    );
  }

  // "degraded" = one of Postgres/S3 is down. Origin still answers, but every
  // cache miss will fail, so it earns a warning colour rather than red or green.
  const color =
    origin.status === "healthy"
      ? "var(--status-good)"
      : origin.status === "degraded"
        ? "var(--status-warning)"
        : "var(--status-critical)";

  return (
    <div className="text-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
          <span style={{ color: "var(--text-primary)" }}>origin</span>
          {origin.region && <span style={{ color: "var(--text-muted)" }}>({origin.region})</span>}
        </div>
        <span style={{ color }}>{origin.status}</span>
      </div>

      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs" style={{ color: "var(--text-muted)" }}>
        <Dep label="postgres" ok={origin.db} />
        <Dep label="s3" ok={origin.s3} />
        {origin.file_count != null && (
          <span>
            {origin.file_count} file{origin.file_count === 1 ? "" : "s"}
            {origin.total_bytes != null && ` · ${formatBytes(origin.total_bytes)}`}
          </span>
        )}
      </div>

      {!origin.reachable && (
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
          Edges keep serving cached copies while origin is down — expired entries fall back to{" "}
          <span style={{ color: "var(--series-3)" }}>stale</span> rather than failing.
        </p>
      )}
    </div>
  );
}

function Dep({ label, ok }: { label: string; ok?: boolean }) {
  if (ok === undefined) return null;
  return (
    <span className="flex items-center gap-1">
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ background: ok ? "var(--status-good)" : "var(--status-critical)" }}
      />
      {label}
    </span>
  );
}
