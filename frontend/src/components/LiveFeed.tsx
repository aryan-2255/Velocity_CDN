import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { cacheResultColor } from "../colors";
import type { RequestLogRow } from "../types";

// The feed scrolls inside a fixed-height pane rather than growing the page, so
// a longer buffer costs nothing in layout.
const MAX_ROWS = 100;

export function LiveFeed() {
  const [rows, setRows] = useState<RequestLogRow[]>([]);
  const seen = useRef(new Set<number>());

  useEffect(() => {
    const source = new EventSource(api.streamUrl());
    source.onmessage = (event) => {
      const row: RequestLogRow = JSON.parse(event.data);
      if (seen.current.has(row.id)) return;
      seen.current.add(row.id);
      setRows((prev) => [row, ...prev].slice(0, MAX_ROWS));
    };
    return () => source.close();
  }, []);

  return (
    <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          Live request feed
          {rows.length > 0 && (
            <span className="ml-2 font-normal" style={{ color: "var(--text-muted)" }}>
              newest {rows.length}
            </span>
          )}
        </h2>
        <Legend />
      </div>
      <div className="max-h-[26rem] overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
            <tr style={{ color: "var(--text-muted)" }}>
              <th className="pb-1 pr-3 font-medium">Time</th>
              <th className="pb-1 pr-3 font-medium">Region</th>
              <th className="pb-1 pr-3 font-medium">Edge</th>
              <th className="pb-1 pr-3 font-medium">File</th>
              <th className="pb-1 pr-3 font-medium">Result</th>
              <th className="pb-1 pr-3 font-medium tabular-nums">Latency</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t" style={{ borderColor: "var(--gridline)" }}>
                <td className="py-1 pr-3 tabular-nums" style={{ color: "var(--text-secondary)" }}>
                  {new Date(row.ts).toLocaleTimeString()}
                </td>
                <td className="py-1 pr-3" style={{ color: "var(--text-secondary)" }}>
                  {row.resolved_region ?? "-"}
                </td>
                <td className="py-1 pr-3" style={{ color: "var(--text-secondary)" }}>
                  {row.edge_id ? row.edge_id.slice(0, 8) : "-"}
                </td>
                <td
                  className="max-w-[16rem] truncate py-1 pr-3"
                  style={{ color: "var(--text-primary)" }}
                  title={row.file_key ?? undefined}
                >
                  {row.file_key ?? "-"}
                </td>
                <td className="py-1 pr-3">
                  <span
                    className="rounded px-1.5 py-0.5 text-[11px] font-medium text-white"
                    style={{ background: cacheResultColor(row.cache_result) }}
                  >
                    {row.cache_result ?? "?"}
                  </span>
                </td>
                <td className="py-1 pr-3 tabular-nums" style={{ color: "var(--text-secondary)" }}>
                  {row.latency_ms != null ? `${row.latency_ms}ms` : "-"}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="py-4 text-center" style={{ color: "var(--text-muted)" }}>
                  Waiting for requests, try the fetch tester above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Legend() {
  const items: Array<[string, string]> = [
    ["hit", "var(--series-1)"],
    ["miss", "var(--series-2)"],
    ["stale", "var(--series-3)"],
    ["error", "var(--series-8)"],
  ];
  return (
    <div className="flex items-center gap-3 text-[11px]" style={{ color: "var(--text-muted)" }}>
      {items.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}
