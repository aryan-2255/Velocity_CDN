import { useEffect, useState } from "react";
import { api } from "./api";
import { EdgeHealthPanel } from "./components/EdgeHealthPanel";
import { FileManager } from "./components/FileManager";
import { HitRatioChart } from "./components/HitRatioChart";
import { LatencyChart } from "./components/LatencyChart";
import { LiveFeed } from "./components/LiveFeed";
import { RegionSelector } from "./components/RegionSelector";
import { StatTile } from "./components/StatTile";
import { TopFilesTable } from "./components/TopFilesTable";
import type { Edge } from "./types";

export default function App() {
  const [hitRatio, setHitRatio] = useState<{
    total: number;
    hit_ratio: number;
    counts?: Record<string, number>;
  } | null>(null);
  const [edges, setEdges] = useState<Edge[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const [hr, edgeList] = await Promise.all([api.hitRatio(), api.edges()]);
        if (!cancelled) {
          setHitRatio(hr);
          setEdges(edgeList);
        }
      } catch {
        // transient, next poll will recover
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const healthyEdges = edges.filter((e) => e.status === "healthy").length;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6">
        <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
          Velocity CDN
        </h1>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Geo-distributed edge caching CDN simulator, live from the load balancer.
        </p>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Hit ratio" value={hitRatio ? `${(hitRatio.hit_ratio * 100).toFixed(0)}%` : "-"} />
        <StatTile label="Total requests" value={hitRatio ? `${hitRatio.total}` : "-"} />
        <StatTile label="Edges healthy" value={`${healthyEdges} / ${edges.length}`} />
        <StatTile
          label="Origin offload"
          value={hitRatio ? `${hitRatio.counts?.miss ?? 0}` : "-"}
          sublabel={
            hitRatio ? `of ${hitRatio.total} requests reached origin` : "requests that reached origin"
          }
        />
      </div>

      {/* items-start so neither panel stretches to the other's height */}
      <div className="mb-6 grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <RegionSelector />
        <FileManager />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <HitRatioChart />
        </div>
        <EdgeHealthPanel />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <LatencyChart />
        </div>
        <TopFilesTable />
      </div>

      <LiveFeed />
    </div>
  );
}
