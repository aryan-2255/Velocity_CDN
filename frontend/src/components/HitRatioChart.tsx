import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { HitRatioTimeseriesPoint } from "../types";

export function HitRatioChart() {
  const [data, setData] = useState<HitRatioTimeseriesPoint[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const points = await api.hitRatioTimeseries();
        if (!cancelled) setData(points);
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
        Hit ratio over time
      </h2>
      <p className="mb-3 text-xs" style={{ color: "var(--text-muted)" }}>
        Climbs from a cold start as edges warm up.
      </p>
      {data.length === 0 ? (
        <EmptyState />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--gridline)" vertical={false} />
            <XAxis
              dataKey="ts"
              tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              tick={{ fill: "var(--text-muted)", fontSize: 11 }}
              stroke="var(--baseline)"
            />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(v) => `${Math.round(v * 100)}%`}
              tick={{ fill: "var(--text-muted)", fontSize: 11 }}
              stroke="var(--baseline)"
              width={40}
            />
            <Tooltip
              formatter={(value: number) => [`${(value * 100).toFixed(1)}%`, "Hit ratio"]}
              labelFormatter={(v) => new Date(v).toLocaleTimeString()}
              contentStyle={{
                background: "var(--surface-1)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                color: "var(--text-primary)",
                fontSize: 12,
              }}
            />
            <Line
              type="monotone"
              dataKey="hit_ratio"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <p className="py-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
      No requests yet — traffic will populate this chart.
    </p>
  );
}
