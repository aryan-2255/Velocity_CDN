import { useEffect, useState } from "react";
import { api } from "../api";
import { cacheResultColor } from "../colors";
import type { RegionChoice } from "../types";

interface FetchResult {
  ok: boolean;
  status: number;
  servedBy: string | null;
  cacheResult: string | null;
  failover: boolean;
  requestId: string | null;
  stale: boolean;
  bytes: number;
  contentType: string | null;
  elapsedMs: number;
  error: string | null;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function RegionSelector() {
  const [region, setRegion] = useState("");
  const [key, setKey] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FetchResult | null>(null);
  const [regions, setRegions] = useState<RegionChoice[]>([]);
  const [geoipEnabled, setGeoipEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.regions();
        if (!cancelled) {
          setRegions(data.regions);
          setGeoipEnabled(data.geoip_enabled);
        }
      } catch {
        // keep the last known list; the select still works with what's rendered
      }
    };
    poll();
    // Re-poll so the "→ edge-x" hints follow edges going unhealthy, matching
    // where a request would actually land right now.
    const id = setInterval(poll, 10000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.files();
        if (cancelled) return;
        const keys = data.map((f) => f.key);
        setFiles(keys);
        // Default to a key that actually exists, so Fetch works without typing.
        setKey((cur) => (cur === "" && keys.length > 0 ? keys[0] : cur));
      } catch {
        // leave whatever's typed; the fetch itself will surface the error
      }
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const runFetch = async () => {
    setLoading(true);
    setResult(null);
    // Client-side timing, so it includes the browser's own round trip — the
    // dashboard's charts show the server-side number the LB records instead.
    const started = performance.now();
    try {
      const resp = await api.fetchFile(key, region || undefined);
      const body = await resp.blob();
      const elapsedMs = Math.round(performance.now() - started);
      setResult({
        ok: resp.ok,
        status: resp.status,
        servedBy: resp.headers.get("x-served-by"),
        cacheResult: resp.headers.get("x-cache-result"),
        failover: resp.headers.get("x-failover") === "true",
        requestId: resp.headers.get("x-request-id"),
        stale: resp.headers.get("warning") !== null,
        bytes: body.size,
        contentType: resp.headers.get("content-type"),
        elapsedMs,
        error: resp.ok ? null : await new Response(body).text(),
      });
    } catch (err) {
      setResult({
        ok: false,
        status: 0,
        servedBy: null,
        cacheResult: null,
        failover: false,
        requestId: null,
        stale: false,
        bytes: 0,
        contentType: null,
        elapsedMs: Math.round(performance.now() - started),
        error: (err as Error).message,
      });
    } finally {
      setLoading(false);
    }
  };

  const withEdge = regions.filter((r) => r.has_local_edge);
  const withoutEdge = regions.filter((r) => !r.has_local_edge);
  const selected = regions.find((r) => r.value === region);

  return (
    <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}>
      <h2 className="mb-1 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        Try a request
      </h2>
      <p className="mb-3 text-xs" style={{ color: "var(--text-muted)" }}>
        Pick where the <em>client</em> is, not where a server is — cities with no local edge are the
        ones that exercise nearest-edge routing.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {/* Free text rather than a plain select: the suggestions cover the normal
            case, but typing a missing key is how you demo a 404. */}
        <input
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder={files.length ? "file key" : "no files uploaded yet"}
          list="available-files"
          className="min-w-[16rem] rounded border px-2 py-1 text-sm"
          style={{ borderColor: "var(--border)", background: "var(--plane)", color: "var(--text-primary)" }}
        />
        <datalist id="available-files">
          {files.map((f) => (
            <option key={f} value={f} />
          ))}
        </datalist>
        <select
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          className="rounded border px-2 py-1 text-sm"
          style={{ borderColor: "var(--border)", background: "var(--plane)", color: "var(--text-primary)" }}
        >
          <option value="">{geoipEnabled === false ? "Auto (GeoIP — disabled)" : "Auto (GeoIP)"}</option>
          {withEdge.length > 0 && (
            <optgroup label="Cities with an edge">
              {withEdge.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label} → {r.nearest_edge ?? "no healthy edge"}
                </option>
              ))}
            </optgroup>
          )}
          {withoutEdge.length > 0 && (
            <optgroup label="Cities with no edge (tests routing)">
              {withoutEdge.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label} → {r.nearest_edge ?? "no healthy edge"}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <button
          onClick={runFetch}
          disabled={loading}
          className="rounded px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
          style={{ background: "var(--series-1)" }}
        >
          {loading ? "Fetching…" : "Fetch"}
        </button>
      </div>
      {geoipEnabled === false && region === "" && (
        <p className="mt-2 text-xs" style={{ color: "var(--status-warning)" }}>
          No GeoLite2 database loaded — "Auto" can't resolve the real client location and falls back
          to the Origin's region. Pick a city above to exercise routing.
        </p>
      )}
      {selected && selected.nearest_edge && (
        <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
          A client in {selected.label} routes to <strong>{selected.nearest_edge}</strong>
          {selected.distance_km !== null && ` — ${selected.distance_km.toLocaleString()} km away`}.
        </p>
      )}
      {result && <ResultPanel result={result} />}
    </div>
  );
}

/** Everything about the last request, up front — no scrolling to the feed to
 *  find out what happened. */
function ResultPanel({ result }: { result: FetchResult }) {
  if (!result.ok) {
    return (
      <div
        className="mt-3 rounded border p-3 text-sm"
        style={{ borderColor: "var(--status-critical)", color: "var(--status-critical)" }}
      >
        <strong>{result.status || "Request failed"}</strong>
        {result.error && <span> · {result.error}</span>}
      </div>
    );
  }

  const cells: Array<[string, React.ReactNode]> = [
    [
      "Result",
      <span
        className="rounded px-1.5 py-0.5 text-[11px] font-medium text-white"
        style={{ background: cacheResultColor(result.cacheResult) }}
      >
        {result.cacheResult ?? "?"}
      </span>,
    ],
    ["Served by", result.servedBy ?? "—"],
    ["Round trip", `${result.elapsedMs} ms`],
    ["Size", formatBytes(result.bytes)],
    ["Type", result.contentType ?? "—"],
    ["Status", result.status],
  ];

  return (
    <div className="mt-3 rounded border p-3" style={{ borderColor: "var(--border)", background: "var(--plane)" }}>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-6">
        {cells.map(([label, value]) => (
          <div key={label}>
            <div className="text-[11px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              {label}
            </div>
            <div className="mt-0.5 text-sm" style={{ color: "var(--text-primary)" }}>
              {value}
            </div>
          </div>
        ))}
      </div>
      {(result.failover || result.stale) && (
        <div className="mt-2 flex gap-2 text-xs">
          {result.failover && (
            <span
              className="rounded px-1.5 py-0.5"
              style={{ background: "var(--status-warning)", color: "#000" }}
            >
              failed over — nearest edge was unavailable
            </span>
          )}
          {result.stale && (
            <span
              className="rounded px-1.5 py-0.5"
              style={{ background: "var(--status-warning)", color: "#000" }}
            >
              stale — served past TTL, Origin unreachable
            </span>
          )}
        </div>
      )}
      {result.requestId && (
        <div className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
          request id <span className="font-mono">{result.requestId}</span> — same id is logged at the
          load balancer, edge, and origin
        </div>
      )}
    </div>
  );
}
