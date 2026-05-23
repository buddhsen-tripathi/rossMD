"use client";
import dynamic from "next/dynamic";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API } from "@/lib/ross";
import type { RossState } from "@/lib/ross";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

type GNode = {
  id: string;
  cite: string;
  title: string;
  regime: string;
  type: string;
  deg: number;
  web?: boolean;
};
type GraphData = {
  nodes: GNode[];
  links: { source: string; target: string; kind?: string }[];
};

// same spectrum as the corpus map + agent palette
const REGIME_COLOR: Record<string, string> = {
  "Stark Law": "#d98a4a",
  "Anti-Kickback": "#e0556b",
  "False Claims Act": "#4f86e8",
  HIPAA: "#3fb878",
  EMTALA: "#6d6af2",
  "Civil Penalties": "#e0894f",
  "42 CFR Part 2": "#2bb6bf",
  Exclusion: "#8892a6",
  "OIG Guidance": "#c98a2b",
  "Insurance & Payer": "#e07ba8",
};
const HIT_CORPUS = "#f2a900"; // retrieved corpus authority — saturated amber-gold
const HIT_WEB = "#10b8a6"; // retrieved live-web source — saturated teal

/**
 * The corpus knowledge graph, lighting up live as the research agents retrieve.
 * Every authority is a real node from /api/graph; the doc_ids in the run's
 * `researcher/retrieved` events are those node ids, so we highlight exactly what
 * the agent pulled — corpus (gold) and freshly-fetched web sources (teal) — and
 * illuminate their reference edges while the rest of the corpus dims back.
 *
 * Memoized on `state.research` so the heavy canvas doesn't repaint on every SSE
 * token/log event — only when the retrieved set actually changes.
 */
// session cache — the corpus graph is "determined" once and reused across tab
// switches / runs (the backend also caches /api/graph until the corpus changes)
let _graphCache: GraphData | null = null;

function RetrievalGraphImpl({ state }: { state: RossState }) {
  const [data, setData] = useState<GraphData | null>(_graphCache);
  const [size, setSize] = useState({ w: 600, h: 600 });
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);

  // doc_ids the researchers have pulled this run (corpus + web)
  const retrieved = useMemo(() => {
    const s = new Set<string>();
    for (const r of Object.values(state.research))
      for (const a of r.authorities) s.add(a.doc_id);
    return s;
  }, [state.research]);
  const hitRef = useRef(retrieved);
  hitRef.current = retrieved;

  useEffect(() => {
    if (_graphCache) {
      setData(_graphCache);
      return;
    }
    fetch(`${API}/api/graph`)
      .then((r) => r.json())
      .then((g) => {
        _graphCache = g; // cache once determined
        setData(g);
      })
      .catch(() => {});
  }, []);

  // size the canvas off the container, measured on mount + window resize only.
  // (A ResizeObserver here causes a scrollbar feedback loop → flicker.)
  useEffect(() => {
    const measure = () => {
      const el = wrapRef.current;
      if (!el) return;
      setSize((prev) => {
        const w = el.clientWidth, h = el.clientHeight;
        return w > 0 && h > 0 && (w !== prev.w || h !== prev.h) ? { w, h } : prev;
      });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [data]);

  // repaint highlights when new authorities arrive — WITHOUT reheating physics
  // (reheat restarts motion across 1,900 nodes and reads as flicker)
  useEffect(() => {
    fgRef.current?.refresh?.();
  }, [retrieved.size]);

  const graph = useMemo(
    () =>
      data
        ? { nodes: data.nodes.map((n) => ({ ...n })), links: data.links.map((l) => ({ ...l })) }
        : { nodes: [], links: [] },
    [data]
  );

  // stable accessors (read the live retrieved set via ref) so react-force-graph
  // isn't handed new function identities on every parent render
  const endId = (e: any) => (typeof e === "object" ? e.id : e);
  const touchesHit = (l: any) =>
    hitRef.current.has(endId(l.source)) || hitRef.current.has(endId(l.target));

  const nodeVal = useCallback(
    (n: any) => (n.type === "regime" ? 0.01 : hitRef.current.has(n.id) ? 5 : 1),
    []
  );
  const nodeColor = useCallback((n: any) => {
    if (n.type === "regime") return "rgba(0,0,0,0)";
    if (hitRef.current.has(n.id)) return n.web ? HIT_WEB : HIT_CORPUS;
    return (REGIME_COLOR[n.regime] ?? "#7a715f") + "40"; // dim un-retrieved corpus
  }, []);
  const nodeLabel = useCallback(
    (n: any) => (n.type === "regime" ? "" : `${n.cite ? n.cite + " — " : ""}${n.title}`),
    []
  );
  // lit reference edges blink (pulse) to signal active retrieval; unused paths
  // sit ~5% more saturated than before so the corpus structure reads
  const linkColor = useCallback(
    (l: any) =>
      touchesHit(l)
        ? `rgba(242,169,0,${(0.45 + 0.4 * Math.abs(Math.sin(Date.now() / 380))).toFixed(3)})`
        : "rgba(120,110,95,0.13)",
    []
  );
  const linkWidth = useCallback((l: any) => (touchesHit(l) ? 2.4 : 0.4), []);
  // animated flow along the retrieved authorities' reference edges
  const linkParticles = useCallback((l: any) => (touchesHit(l) ? 3 : 0), []);
  const linkParticleWidth = useCallback((l: any) => (touchesHit(l) ? 2.6 : 0), []);
  const particleColor = useCallback((l: any) => {
    const a = endId(l.source), b = endId(l.target);
    // teal flow when a live-web source is involved, gold otherwise
    return hitRef.current.has(a) || hitRef.current.has(b) ? "#f2c200" : HIT_CORPUS;
  }, []);
  const paintAfter = useCallback(() => "after", []);
  const nodePaint = useCallback((n: any, ctx: any) => {
    if (n.type === "regime" || !hitRef.current.has(n.id)) return;
    // glow ring that blinks in sync with the lit paths
    const pulse = 0.4 + 0.45 * Math.abs(Math.sin(Date.now() / 380));
    ctx.beginPath();
    ctx.arc(n.x, n.y, 7.5, 0, 2 * Math.PI);
    ctx.strokeStyle = n.web ? HIT_WEB : HIT_CORPUS;
    ctx.globalAlpha = pulse;
    ctx.lineWidth = 1.4;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }, []);

  return (
    <div ref={wrapRef} className="relative h-full w-full overflow-hidden">
      {!data && (
        <div className="flex h-full items-center justify-center text-[13px] text-[var(--ink-faint)]">
          <span className="blink">loading the knowledge graph…</span>
        </div>
      )}
      {data && (
        <ForceGraph2D
          ref={fgRef}
          width={size.w}
          height={size.h}
          graphData={graph}
          backgroundColor="rgba(0,0,0,0)"
          nodeRelSize={3}
          cooldownTicks={120}
          warmupTicks={20}
          nodeVal={nodeVal}
          nodeColor={nodeColor}
          nodeLabel={nodeLabel}
          linkColor={linkColor}
          linkWidth={linkWidth}
          linkDirectionalParticles={linkParticles}
          linkDirectionalParticleWidth={linkParticleWidth}
          linkDirectionalParticleSpeed={0.006}
          linkDirectionalParticleColor={particleColor}
          nodeCanvasObjectMode={paintAfter}
          nodeCanvasObject={nodePaint}
        />
      )}

      {/* overlay */}
      <div className="pointer-events-none absolute left-4 top-4 z-10">
        <div className="serif text-[15px] text-[var(--ink-1)]">The agent&apos;s memory, lighting up</div>
        <div className="mt-0.5 text-[11px] text-[var(--ink-dim)]">
          {retrieved.size} {retrieved.size === 1 ? "authority" : "authorities"} retrieved from ClickHouse
        </div>
        <div className="mt-2 flex gap-3 text-[10.5px] text-[var(--ink-faint)]">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ background: HIT_CORPUS }} /> corpus
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ background: HIT_WEB }} /> live web
          </span>
        </div>
      </div>
    </div>
  );
}

// only re-render when the retrieved set changes — not on every token/log event
export const RetrievalGraph = memo(
  RetrievalGraphImpl,
  (a, b) => a.state.research === b.state.research && a.state.running === b.state.running
);
