"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { forceCollide } from "d3-force-3d";
import { API } from "@/lib/ross";

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

export default function CorpusPage() {
  const [data, setData] = useState<GraphData | null>(null);
  const [size, setSize] = useState({ w: 1200, h: 800 });
  const [hover, setHover] = useState<GNode | null>(null);
  const fgRef = useRef<any>(null);

  useEffect(() => {
    fetch(`${API}/api/graph`).then((r) => r.json()).then(setData).catch(() => {});
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

  return (
    <div className="relative h-screen w-screen overflow-hidden" style={{ background: "#0d0b08" }}>
      {/* header overlay */}
      <div className="pointer-events-none absolute left-0 right-0 top-0 z-10 flex items-start justify-between p-6">
        <div className="pointer-events-auto">
          <Link href="/" className="serif text-lg text-[#efe9df] hover:text-[#d4a24e]">
            ← Ross MD
          </Link>
          <h1 className="serif mt-2 text-2xl text-[#efe9df]">The body of healthcare law Ross MD has read</h1>
          <p className="mt-1 max-w-md text-[13px] text-[#a59c8c]">
            Every node is a federal authority — a statute, a CFR section, an OIG opinion. They
            cluster into the regimes Ross works in: Stark, Anti-Kickback, the False Claims Act,
            HIPAA, EMTALA, and insurance/payer law — ERISA, ACA, the No Surprises Act.
          </p>
        </div>
        {data && (
          <div className="pointer-events-auto flex gap-6 text-right">
            {[
              ["authorities", data.stats.docs],
              ["embedded passages", data.stats.chunks],
              ["cross-references", data.stats.cross_refs],
              ["regimes", data.stats.regimes],
            ].map(([label, val]) => (
              <div key={label as string}>
                <div className="serif tabnum text-2xl text-[#d4a24e]">{(val as number).toLocaleString()}</div>
                <div className="text-[11px] uppercase tracking-wider text-[#6f675a]">{label}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* legend */}
      <div className="absolute bottom-6 left-6 z-10 flex flex-col gap-1.5">
        {LEGEND.map((l) => (
          <div key={l.key} className="flex items-center gap-2 text-[12px] text-[#a59c8c]">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color }} />
            {l.key}
          </div>
        ))}
      </div>

      {/* hover card */}
      {hover && (
        <div className="absolute bottom-6 right-6 z-10 max-w-xs rounded-lg border border-[#2c261d] bg-[#18140f] p-4">
          <div className="mono text-[12px] text-[#5aa9e6]">{hover.cite || "—"}</div>
          <div className="serif mt-1 text-[15px] text-[#efe9df]">{hover.title}</div>
          <div className="mt-1 text-[11px] text-[#6f675a]">
            {hover.type === "regime" ? "regulatory regime" : hover.type}
            {hover.regime && hover.type !== "regime" ? ` · ${hover.regime}` : ""}
          </div>
          {hover.type === "regime" ? (
            <div className="mt-2 text-[11px] text-[#d4a24e]">{hover.deg} authorities in this regime</div>
          ) : hover.deg > 0 ? (
            <div className="mt-2 text-[11px] text-[#d4a24e]">
              referenced by {hover.deg} other {hover.deg > 1 ? "authorities" : "authority"}
            </div>
          ) : null}
        </div>
      )}

      {!data && (
        <div className="flex h-full items-center justify-center text-[#a59c8c]">
          <span className="blink">mapping the corpus…</span>
        </div>
      )}

      {data && (
        <ForceGraph2D
          ref={fgRef}
          width={size.w}
          height={size.h}
          graphData={graph}
          backgroundColor="#0d0b08"
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
            ctx.shadowColor = "rgba(0,0,0,0.9)";
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
