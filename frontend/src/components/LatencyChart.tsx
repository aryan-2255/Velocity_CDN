import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { CACHE_RESULT_ORDER, cacheResultColor } from "../colors";
import type { LatencyRow } from "../types";

type RegionRow = { region: string } & Partial<Record<(typeof CACHE_RESULT_ORDER)[number], number>>;

function pivot(rows: LatencyRow[]): RegionRow[] {
  const byRegion = new Map<string, RegionRow>();
  for (const row of rows) {
    const region = row.region ?? "unresolved";
    const entry = byRegion.get(region) ?? { region };
    if (row.cache_result && row.avg_ms != null) {
      entry[row.cache_result as (typeof CACHE_RESULT_ORDER)[number]] = row.avg_ms;
    }
    byRegion.set(region, entry);
  }
  return [...byRegion.values()];
}

export function LatencyChart() {
  const [data, setData] = useState<RegionRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const rows = await api.latency();
        if (!cancelled) setData(pivot(rows));
      } catch {
        // keep last known series on transient failure
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
      <h2 className="mb-1 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        Avg latency by outcome, per region
      </h2>
      <p className="mb-3 text-xs" style={{ color: "var(--text-muted)" }}>
        Origin-direct baseline needs the Locust benchmark (see benchmark.md), not shown here.
      </p>
      {data.length === 0 ? (
        <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          No requests yet, traffic will populate this chart.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--gridline)" vertical={false} />
            <XAxis dataKey="region" tick={{ fill: "var(--text-muted)", fontSize: 11 }} stroke="var(--baseline)" />
            <YAxis
              tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`)}
              tick={{ fill: "var(--text-muted)", fontSize: 11 }}
              stroke="var(--baseline)"
              width={52}
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface-1)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                color: "var(--text-primary)",
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "var(--text-secondary)" }} />
            {CACHE_RESULT_ORDER.map((result) => (
              <Bar key={result} dataKey={result} fill={cacheResultColor(result)} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
