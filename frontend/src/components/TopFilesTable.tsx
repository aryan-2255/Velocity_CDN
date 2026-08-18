import { useEffect, useState } from "react";
import { api } from "../api";
import type { TopFile } from "../types";

export function TopFilesTable() {
  const [files, setFiles] = useState<TopFile[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.topFiles(8);
        if (!cancelled) setFiles(data);
      } catch {
        // keep last known table on transient failure
      }
    };
    poll();
    const id = setInterval(poll, 8000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const max = Math.max(1, ...files.map((f) => f.requests));

  return (
    <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <h2 className="mb-3 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        Top requested files
      </h2>
      {files.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          No requests yet.
        </p>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <div key={f.file_key} className="text-sm">
              <div className="flex items-center justify-between">
                <span className="truncate" style={{ color: "var(--text-primary)" }}>
                  {f.file_key}
                </span>
                <span className="tabular-nums" style={{ color: "var(--text-secondary)" }}>
                  {f.requests}
                </span>
              </div>
              <div className="mt-0.5 h-1.5 rounded-full" style={{ background: "var(--gridline)" }}>
                <div
                  className="h-1.5 rounded-full"
                  style={{ width: `${(f.requests / max) * 100}%`, background: "var(--series-1)" }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
