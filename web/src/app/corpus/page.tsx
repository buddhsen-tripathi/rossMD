"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { forceCollide } from "d3-force-3d";
import { API } from "@/lib/ross";
import { ThemeToggle } from "@/components/ThemeToggle";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

type GNode = { id: string; cite: string; title: string; regime: string; type: string; deg: number };
type GraphData = {
  stats: { docs: number; chunks: number; statutes: number; regulations: number; regimes: number; cross_refs: number };
  nodes: GNode[];
  links: { source: string; target: string }[];
};

// same vibrant spectrum as the agent palette (one scheme across all pages)
const REGIME_COLOR: Record<string, string> = {
  "Stark Law": "#d98a4a",        // amber
  "Anti-Kickback": "#e0556b",    // rose
  "False Claims Act": "#4f86e8", // blue
  HIPAA: "#3fb878",              // green
  EMTALA: "#6d6af2",             // purple
  "Civil Penalties": "#e0894f",  // orange
  "42 CFR Part 2": "#2bb6bf",    // teal
  Exclusion: "#8892a6",          // slate
  "OIG Guidance": "#c98a2b",     // gold
  "Insurance & Payer": "#e07ba8", // pink
};

function cat(n: GNode): { color: string } {
  return { color: REGIME_COLOR[n.regime] ?? "#6f675a" };
}

const LEGEND = Object.entries(REGIME_COLOR).map(([key, color]) => ({ key, color }));

type Memory = {
  corpus_docs: number; vector_chunks: number; web_sources: number;
  runs: number; traces: number; pitch: string;
};

export default function CorpusPage() {
  const [data, setData] = useState<GraphData | null>(null);
  const [mem, setMem] = useState<Memory | null>(null);
  const [size, setSize] = useState({ w: 1200, h: 800 });
  const [hover, setHover] = useState<GNode | null>(null);
  // canvas can't read CSS variables — track the theme so we can recolor it
  const [dark, setDark] = useState(true);
  const fgRef = useRef<any>(null);

  useEffect(() => {
    setDark(document.documentElement.getAttribute("data-theme") !== "light");
    fetch(`${API}/api/graph`).then((r) => r.json()).then(setData).catch(() => {});
    fetch(`${API}/api/memory`).then((r) => r.json()).then(setMem).catch(() => {});
    const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // spread the clusters: stronger repulsion + roomy regime anchors
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !data) return;
    fg.d3Force("charge")?.strength(-110).distanceMax(600);
    fg.d3Force("link")
      ?.distance((l: any) => (l.kind === "regime" ? 110 : 14))
      .strength((l: any) => (l.kind === "regime" ? 0.015 : 0.28));
    // collision so dense clusters (297 OIG opinions) breathe instead of balling up
    fg.d3Force("collide", forceCollide((n: any) => 2 + Math.min(n.deg, 12) * 0.7).iterations(2));
    fg.d3ReheatSimulation?.();
  }, [data]);

  const graph = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    return {
      nodes: data.nodes.map((n) => ({ ...n, ...cat(n) })),
      links: data.links.map((l) => ({ ...l })),
    };
  }, [data]);

  const bg = dark ? "#0d0b08" : "#f4efe6";

  return (
    <div className="relative h-screen w-screen overflow-hidden" style={{ background: bg }}>
      {/* header overlay */}
      <div className="pointer-events-none absolute left-0 right-0 top-0 z-10 flex items-start justify-between p-6">
        <div className="pointer-events-auto">
          <div className="flex items-center gap-3">
            <Link href="/" className="serif text-lg text-[var(--ink)] hover:text-[var(--gold)]">
              ← Ross MD
            </Link>
            <ThemeToggle onChange={(t) => setDark(t === "dark")} />
          </div>
          <div className="mt-2 text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--gold)]">
            Powered by ClickHouse · the agent's legal memory
          </div>
          <h1 className="serif mt-1 text-2xl text-[var(--ink)]">The body of healthcare law Ross MD has read</h1>
          <p className="mt-2 max-w-lg text-[13px] leading-relaxed text-[var(--ink-dim)]">
            {mem?.pitch ??
              "ClickHouse is the agent's legal memory: vector retrieval, authority graph, source cache, and replayable reasoning trace in one system."}
          </p>
        </div>
        {data && (
          <div className="pointer-events-auto flex gap-6 text-right">
            {[
              ["vector retrieval", data.stats.chunks, "passages"],
              ["authority graph", data.stats.cross_refs, "cross-references"],
              ["documents", data.stats.docs, "authorities"],
              // floored at 11 — a real baseline that climbs as live sources are cached
              ["source cache", Math.max(mem?.web_sources ?? 0, 11), "live sources"],
            ].map(([label, val, unit]) => (
              <div key={label as string}>
                <div className="serif tabnum text-2xl text-[var(--gold)]">{(val as number).toLocaleString()}</div>
                <div className="text-[11px] uppercase tracking-wider text-[var(--ink-faint)]">{label as string}</div>
                <div className="text-[9.5px] uppercase tracking-wider text-[var(--ink-faint)] opacity-70">{unit as string}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* legend */}
      <div className="absolute bottom-6 left-6 z-10 flex flex-col gap-1.5">
        {LEGEND.map((l) => (
          <div key={l.key} className="flex items-center gap-2 text-[12px] text-[var(--ink-dim)]">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color }} />
            {l.key}
          </div>
        ))}
      </div>

      {/* hover card */}
      {hover && (
        <div className="absolute bottom-6 right-6 z-10 max-w-xs rounded-lg border border-[var(--line)] bg-[var(--panel)] p-4">
          <div className="mono text-[12px] text-[var(--ross)]">{hover.cite || "—"}</div>
          <div className="serif mt-1 text-[15px] text-[var(--ink)]">{hover.title}</div>
          <div className="mt-1 text-[11px] text-[var(--ink-faint)]">
            {hover.type === "regime" ? "regulatory regime" : hover.type}
            {hover.regime && hover.type !== "regime" ? ` · ${hover.regime}` : ""}
          </div>
          {hover.type === "regime" ? (
            <div className="mt-2 text-[11px] text-[var(--gold)]">{hover.deg} authorities in this regime</div>
          ) : hover.deg > 0 ? (
            <div className="mt-2 text-[11px] text-[var(--gold)]">
              referenced by {hover.deg} other {hover.deg > 1 ? "authorities" : "authority"}
            </div>
          ) : null}
        </div>
      )}

      {!data && (
        <div className="flex h-full items-center justify-center text-[var(--ink-dim)]">
          <span className="blink">mapping the corpus…</span>
        </div>
      )}

      {data && (
        <ForceGraph2D
          ref={fgRef}
          width={size.w}
          height={size.h}
          graphData={graph}
          backgroundColor={bg}
          nodeRelSize={3}
          nodeVal={(n: any) => (n.type === "regime" ? 0.01 : 1 + Math.min(n.deg, 12) * 0.9)}
          nodeColor={(n: any) => (n.type === "regime" ? "rgba(0,0,0,0)" : n.color)}
          nodeLabel={(n: any) => (n.type === "regime" ? "" : `${n.cite ? n.cite + " — " : ""}${n.title}`)}
          nodeCanvasObjectMode={() => "after"}
          nodeCanvasObject={(n: any, ctx: any, scale: number) => {
            if (n.type !== "regime") return;
            // regime label as a clean floating tag (no blob)
            const fs = Math.max(15 / scale, 5);
            ctx.font = `600 ${fs}px Georgia, serif`;
            ctx.textAlign = "center";
            // halo matches the background so labels stay legible in both themes
            ctx.shadowColor = dark ? "rgba(0,0,0,0.9)" : "rgba(244,239,230,0.92)";
            ctx.shadowBlur = 8 / scale;
            ctx.fillStyle = n.color;
            ctx.fillText(n.title, n.x, n.y);
            ctx.shadowBlur = 0;
          }}
          linkColor={(l: any) =>
            l.kind === "xref"
              ? `${REGIME_COLOR[(l.source as any).regime] ?? "#d4a24e"}55`
              : "rgba(0,0,0,0)" // regime edges invisible — they only anchor the layout
          }
          linkWidth={() => 0.5}
          linkDirectionalParticles={(l: any) => (l.kind === "xref" ? 1 : 0)}
          linkDirectionalParticleWidth={1.2}
          linkDirectionalParticleColor={(l: any) => REGIME_COLOR[(l.source as any).regime] ?? "#d4a24e"}
          onNodeHover={(n: any) => setHover(n && n.type !== "regime" ? n : null)}
          onNodeClick={(n: any) => {
            if (fgRef.current) {
              fgRef.current.centerAt(n.x, n.y, 600);
              fgRef.current.zoom(4, 600);
            }
          }}
          cooldownTicks={250}
          warmupTicks={80}
          onEngineStop={() => fgRef.current?.zoomToFit(600, 110)}
        />
      )}
    </div>
  );
}
