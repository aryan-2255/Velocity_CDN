import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { OriginFile } from "../types";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function FileManager({ onChange }: { onChange?: () => void }) {
  const [files, setFiles] = useState<OriginFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [customKey, setCustomKey] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    try {
      setFiles(await api.files());
    } catch {
      // transient — the next poll or action will pick it up
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, []);

  const upload = async (file: File) => {
    setBusy(true);
    setNote(null);
    try {
      const meta = await api.uploadFile(file, customKey.trim() || undefined);
      setNote({ ok: true, text: `Uploaded ${meta.key} (${formatBytes(meta.size_bytes)})` });
      setCustomKey("");
      if (inputRef.current) inputRef.current.value = "";
      await refresh();
      onChange?.();
    } catch (err) {
      setNote({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (key: string) => {
    setBusy(true);
    setNote(null);
    try {
      await api.deleteFile(key);
      setNote({ ok: true, text: `Deleted ${key} — purge pushed to all edges` });
      await refresh();
      onChange?.();
    } catch (err) {
      setNote({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <h2 className="mb-1 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        Origin files
      </h2>
      <p className="mb-3 text-xs" style={{ color: "var(--text-muted)" }}>
        Uploads go through the Origin API, which writes S3 and the metadata table together. Adding
        objects straight to the bucket leaves no row, and every fetch for that key 404s.
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          value={customKey}
          onChange={(e) => setCustomKey(e.target.value)}
          placeholder="optional key, e.g. assets/logo.png"
          className="min-w-[15rem] flex-1 rounded border px-2 py-1 text-sm"
          style={{ borderColor: "var(--border)", background: "var(--plane)", color: "var(--text-primary)" }}
        />
        <input
          ref={inputRef}
          type="file"
          disabled={busy}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
          }}
          className="text-sm"
          style={{ color: "var(--text-secondary)" }}
        />
      </div>

      {note && (
        <p
          className="mb-3 text-xs"
          style={{ color: note.ok ? "var(--status-good)" : "var(--status-critical)" }}
        >
          {note.text}
        </p>
      )}

      <div className="max-h-56 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
            <tr style={{ color: "var(--text-muted)" }}>
              <th className="pb-1 pr-3 font-medium">Key</th>
              <th className="pb-1 pr-3 font-medium">Size</th>
              <th className="pb-1 pr-3 font-medium">Type</th>
              <th className="pb-1 font-medium">v</th>
              <th className="pb-1" />
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.key} className="border-t" style={{ borderColor: "var(--gridline)" }}>
                <td className="max-w-[18rem] truncate py-1 pr-3" style={{ color: "var(--text-primary)" }} title={f.key}>
                  {f.key}
                </td>
                <td className="py-1 pr-3 tabular-nums" style={{ color: "var(--text-secondary)" }}>
                  {formatBytes(f.size_bytes)}
                </td>
                <td className="py-1 pr-3" style={{ color: "var(--text-secondary)" }}>
                  {f.content_type}
                </td>
                <td className="py-1 tabular-nums" style={{ color: "var(--text-secondary)" }}>
                  {f.version}
                </td>
                <td className="py-1 text-right">
                  <button
                    onClick={() => void remove(f.key)}
                    disabled={busy}
                    className="rounded px-1.5 py-0.5 text-[11px] disabled:opacity-40"
                    style={{ color: "var(--status-critical)" }}
                  >
                    delete
                  </button>
                </td>
              </tr>
            ))}
            {files.length === 0 && (
              <tr>
                <td colSpan={5} className="py-4 text-center" style={{ color: "var(--text-muted)" }}>
                  No files yet — upload one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
