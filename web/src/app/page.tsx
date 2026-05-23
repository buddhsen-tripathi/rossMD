"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRoss, AgentState, Authority, API, RossEvent } from "@/lib/ross";
import { CitationDrawer } from "@/components/CitationDrawer";

const PIPELINE = [
  { key: "intake", label: "Intake", sub: "the arrangement & money flow", color: "#6d6af2" },
  { key: "issue_spotter", label: "Issue Spotter", sub: "Stark · AKS · FCA · HIPAA", color: "#4f86e8" },
  { key: "researcher", label: "Researchers", sub: "statutes, regs & OIG opinions", color: "#2bb6bf" },
  { key: "strategist", label: "Strategist", sub: "structure it to comply", color: "#3fb878" },
  { key: "adversary", label: "Adversary", sub: "DOJ · OIG · qui tam relator", color: "#e0894f" },
  { key: "drafter", label: "Drafter", sub: "the work product", color: "#d98a4a" },
  { key: "harvey", label: "Harvey", sub: "the regulatory partner", color: "#c98a2b" },
];

const EXAMPLES = [
  {
    chip: "🩺 UnitedHealthcare — inpatient denied 'not medically necessary'",
    text: "UnitedHealthcare denied our client hospital's claim for a 4-day inpatient cardiac admission as 'not medically necessary,' downgrading it to observation and citing MCG care guidelines. The patient had chest pain, elevated troponins, and a positive stress test. The plan is ERISA self-funded; we're at internal appeal with the deadline in 12 days. Build the appeal to overturn the denial.",
  },
  {
    chip: "🧬 Aetna — therapy denied 'experimental / investigational'",
    text: "Aetna denied prior authorization for proton beam therapy for our client's pediatric CNS tumor patient as 'experimental and investigational,' citing its clinical policy bulletin. Build the appeal packet to overturn the denial and preserve external-review rights.",
  },
  {
    chip: "💳 ERISA emergency out-of-network denial",
    text: "An ERISA self-funded plan denied our client hospital's $180,000 claim for emergency out-of-network care as 'not medically necessary.' Internal appeals are exhausted. What's our move under ERISA, the No Surprises Act, and the plan's claims-procedure obligations?",
  },
  {
    chip: "🏥 Stark / Anti-Kickback arrangement",
    text: "A hospital wants to pay a 6-physician cardiology group a fixed annual fee to serve as medical directors of its new cath lab. The cardiologists refer Medicare and Medicaid patients to the hospital for cardiac procedures. Proposed pay is above the local median for the role. How do we structure this to comply with Stark and the Anti-Kickback Statute?",
  },
  {
    chip: "⚖ Qui tam / DOJ investigation",
    text: "A former billing manager filed a qui tam alleging our client, a physician group, billed Medicare for services referred under a kickback arrangement with an outside lab. DOJ just issued a Civil Investigative Demand. Build our defense.",
  },
];

const COLOR: Record<AgentState, string> = {
  idle: "var(--ink-faint)",
  active: "var(--ross)",
  done: "var(--green)",
  reject: "var(--red)",
};

const AGENT_COLOR: Record<string, string> = {
  intake: "#6d6af2",
  issue_spotter: "#4f86e8",
  researcher: "#2bb6bf",
  strategist: "#3fb878",
  adversary: "#e0894f",
  drafter: "#d98a4a",
  harvey: "#c98a2b",
  orchestrator: "#8892a6",
};
const AGENT_NAME: Record<string, string> = {
  intake: "Intake",
  issue_spotter: "Issue Spotter",
  researcher: "Researcher",
  strategist: "Strategist",
  adversary: "Adversary",
  drafter: "Drafter",
  harvey: "Harvey",
  orchestrator: "Ross",
};

// ── ONE vibrant gradient spectrum (Nimu-style), shared by every page ──
// each base color → a richer linear gradient for nodes/cards/pills.
const GRAD: Record<string, string> = {
  "#6d6af2": "linear-gradient(145deg,#8b7cf6,#6d6af2)",
  "#4f86e8": "linear-gradient(145deg,#5fa0f2,#4f86e8)",
  "#2bb6bf": "linear-gradient(145deg,#34cfd4,#2bb6bf)",
  "#3fb878": "linear-gradient(145deg,#52cf8c,#3fb878)",
  "#e0894f": "linear-gradient(145deg,#f0a55f,#e0894f)",
  "#d98a4a": "linear-gradient(145deg,#ecb95a,#d98a4a)",
  "#c98a2b": "linear-gradient(145deg,#e8b23e,#c98a2b)",
};
const grad = (c: string) => GRAD[c] ?? c;

// turn a raw event into a human line for the live feed (or null to skip)
function describe(ev: RossEvent): { text: string; mono?: string } | null {
  const p = ev.payload || {};
  switch (`${ev.agent}/${ev.event}`) {
    case "intake/start":
      return { text: "Reading the file — parties, money flow, referrals" };
    case "intake/done":
      return {
        text: `Extracted the facts${p.missing?.length ? ` · flagged ${p.missing.length} open questions` : ""}`,
      };
    case "issue_spotter/start":
      return { text: "Spotting every angle of regulatory exposure…" };
    case "issue_spotter/done":
      return {
        text: `Spotted ${p.issues?.length ?? 0} issues: ${(p.issues ?? [])
          .map((i: any) => i.label)
          .slice(0, 6)
          .join(" · ")}`,
      };
    case "orchestrator/fan_out":
      return { text: `Fanning out ${p.n} researchers — in parallel` };
    case "researcher/route":
      if (p.decision === "human_needed") return { text: `Needs the client: ${p.reason}` };
      if (p.decision === "clickhouse") return null; // corpus-only — no need to narrate
      return { text: `Going to the web — ${p.reason}` };
    case "researcher/web_search":
      return {
        text: `Live web search — ${p.n} source${p.n === 1 ? "" : "s"}${
          p.sources?.length ? `: ${p.sources.map((s: any) => s.title).slice(0, 2).join(" · ")}` : ""
        }`,
      };
    case "researcher/human_needed":
      return { text: `Flagged for counsel — ${p.reason}` };
    case "researcher/retrieved":
      return { text: `Pulled ${p.authorities?.length ?? 0} authorities for “${p.label ?? p.issue_id}”` };
    case "researcher/done":
      return p.bottom_line ? { text: `Research: ${p.bottom_line}` } : null;
    case "strategist/start":
      return { text: "Building the theory of the case…" };
    case "strategist/done":
      return { text: `Theory set — posture: ${p.posture ?? "—"}` };
    case "adversary/start":
      return { text: "Opposing counsel attacking the position…" };
    case "adversary/done":
      return { text: `${p.n_attacks ?? 0} government attacks anticipated and pre-empted` };
    case "drafter/start":
      return { text: p.revision ? "Revising the work product on Harvey's notes…" : "Drafting the work product…" };
    case "drafter/done":
      return { text: "Draft ready" };
    case "harvey/start":
      return { text: `Reviewing the draft (round ${p.round ?? 1})…` };
    case "harvey/verdict":
      return {
        text: `${p.verdict === "approve" ? "APPROVED" : "REVISE"} — “${p.one_liner ?? ""}”`,
      };
    case "orchestrator/run_done":
      return { text: "Work product complete" };
    case "intake/llm_call":
    case "issue_spotter/llm_call":
    case "strategist/llm_call":
    case "adversary/llm_call":
    case "drafter/llm_call":
    case "harvey/llm_call":
      return p.completion_tokens
        ? { text: "", mono: `${(p.model || "").split("/").pop()} · ${p.completion_tokens} tok` }
        : null;
    default:
      return null;
  }
}

export default function Home() {
  const { state, run } = useRoss();
  // pre-fill the hero payer-denial scenario so the demo is one click ("Build the case")
  const [input, setInput] = useState(EXAMPLES[0].text);
  const [tab, setTab] = useState<"activity" | "work" | "adversary" | "observability">("work");
  const [ddSite, setDdSite] = useState("");
  const sawDraft = useRef(false);
  const pinnedTab = useRef(false);

  useEffect(() => {
    fetch(`${API}/api/health`)
      .then((r) => r.json())
      .then((h) => setDdSite(h.dd_site || ""))
      .catch(() => {});
  }, []);
  const [drawer, setDrawer] = useState<{ cite: string; docId?: string; by?: string } | null>(
    null
  );

  const started = state.log.length > 0 || state.running;

  const citeIndex = useMemo(() => {
    const idx: Record<string, Authority> = {};
    for (const r of Object.values(state.research))
      for (const a of r.authorities) if (a.citation) idx[a.citation.toLowerCase()] = a;
    return idx;
  }, [state.research]);

  const lookupCite = (cite: string): Authority | undefined => {
    const c = cite.toLowerCase();
    if (citeIndex[c]) return citeIndex[c];
    for (const [k, v] of Object.entries(citeIndex))
      if (c.includes(k) || k.includes(c)) return v;
    return undefined;
  };

  function go(text: string) {
    const s = text.trim();
    if (!s) return;
    setInput(s);
    sawDraft.current = false;
    setTab("activity"); // watch the agents work while the draft builds
    run(s);
  }

  // when the draft first lands, swap from the live feed to the work product
  // (unless a ?tab= deep-link pinned the view)
  useEffect(() => {
    if (state.draft && !sawDraft.current && !pinnedTab.current) {
      sawDraft.current = true;
      setTab("work");
    }
  }, [state.draft]);

  // post-workflow follow-up: re-analyze with the original scenario + new context
  function askFollowUp(q: string) {
    go(`${input}\n\nATTORNEY FOLLOW-UP / ADDED FACTS: ${q}`);
  }

  async function replayLast(speed?: number) {
    sawDraft.current = false;
    if (!pinnedTab.current) setTab("activity");
    try {
      const r = await fetch(`${API}/api/last-run`).then((x) => x.json());
      if (r.run_id) {
        setInput(r.scenario || "Recorded run");
        run("", r.run_id, speed);
      }
    } catch {
      /* no-op */
    }
  }

  // deep-link: /?replay=last (optionally &speed=80) auto-starts a replay
  const autoFired = useRef(false);
  useEffect(() => {
    if (autoFired.current) return;
    const p = new URLSearchParams(window.location.search);
    const t = p.get("tab");
    if (t === "activity" || t === "work" || t === "adversary" || t === "observability") {
      pinnedTab.current = true;
      setTab(t);
    }
    if (p.get("replay")) {
      autoFired.current = true;
      const speed = Number(p.get("speed")) || undefined;
      replayLast(speed);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen">
      {started && (
        <Header tokens={state.tokens} posture={state.strategy?.posture} running={state.running} />
      )}

      {!started ? (
        <Landing input={input} setInput={setInput} go={go} replayLast={replayLast} />
      ) : (
        <div className="mx-auto grid max-w-[1500px] grid-cols-[330px_1fr_380px] gap-4 px-4 pt-6 pb-10">
          <Theater state={state} />
          <main className="panel flex h-[84vh] flex-col overflow-hidden">
            <Tabs
              tab={tab}
              setTab={setTab}
              nAttacks={state.adversary?.n_attacks}
              running={state.running}
              ddOn={!!ddSite}
            />
            <div className="min-h-0 flex-1 overflow-y-auto">
              {tab === "activity" ? (
                <ActivityFeed state={state} />
              ) : tab === "observability" ? (
                <Observability state={state} ddSite={ddSite} />
              ) : tab === "work" ? (
                <WorkProduct
                  draft={state.draft}
                  running={state.running}
                  onCite={(cite) => {
                    const a = lookupCite(cite);
                    setDrawer({ cite, docId: a?.doc_id, by: "Researcher" });
                  }}
                />
              ) : (
                <AdversaryPanel state={state} />
              )}
            </div>
            {tab === "work" && state.draft && !state.running && (
              <FollowUp facts={state.facts} onAsk={askFollowUp} />
            )}
          </main>
          <RightRail
            state={state}
            onCite={(cite, a) => setDrawer({ cite, docId: a?.doc_id, by: "Researcher" })}
          />
        </div>
      )}

      <CitationDrawer
        open={!!drawer}
        cite={drawer?.cite ?? ""}
        docId={drawer?.docId}
        surfacedBy={drawer?.by}
        onClose={() => setDrawer(null)}
      />
    </div>
  );
}

function Header({
  tokens,
  posture,
  running,
}: {
  tokens: number;
  posture?: string;
  running: boolean;
}) {
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between border-b border-[var(--line)] bg-[var(--bg)]/90 px-5 py-3 backdrop-blur">
      <div className="flex items-baseline gap-3">
        <span className="serif text-xl font-semibold tracking-tight">Ross MD</span>
        <span className="text-xs text-[var(--ink-faint)]">healthcare regulatory</span>
        {running && <span className="blink text-xs text-[var(--ross)]">● working</span>}
      </div>
      <div className="flex items-center gap-4 text-xs text-[var(--ink-dim)]">
        <a
          href="/corpus"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--ink-dim)] hover:text-[var(--gold)]"
        >
          The corpus ↗
        </a>
        {posture && (
          <span className="rounded border border-[var(--gold-dim)] px-2 py-0.5 text-[var(--gold)]">
            {posture}
          </span>
        )}
        {tokens > 0 && <span className="mono tabnum">{tokens.toLocaleString()} tok</span>}
      </div>
    </header>
  );
}

const HERO_PILLS = [
  { label: "Payer denials", glyph: "⊘", color: "#d98a4a" },
  { label: "Appeal rights", glyph: "◆", color: "#4f86e8" },
  { label: "Medical necessity", glyph: "✦", color: "#3fb878" },
];

// The 5 process steps — same motif as the workspace agent theater.
const PHASES = [
  { n: "01", title: "Reads the arrangement", desc: "Parties, money flow, referrals, federal program", color: "#6d6af2" },
  { n: "02", title: "Spots the exposure", desc: "Stark, AKS, FCA, HIPAA, EMTALA — and the exceptions", color: "#4f86e8" },
  { n: "03", title: "Pulls the authority", desc: "Statutes, CFR safe harbors & OIG advisory opinions", color: "#2bb6bf" },
  { n: "04", title: "Structures & stress-tests", desc: "Fits a safe harbor, then DOJ attacks it", color: "#e0894f" },
  { n: "05", title: "Drafts it — Harvey signs off", desc: "Papered so the government never asks", color: "#c98a2b" },
];

/** Hero graphic = a live-feeling preview of the exact pipeline the workspace runs. */
function PipelinePreview() {
  return (
    <div className="relative mx-auto w-full max-w-[400px]">
      <div className="absolute bottom-6 left-[27px] top-6 w-px bg-[var(--warm-line-2)]" />
      <div className="flex flex-col gap-3">
        {PHASES.map((p, i) => (
          <div
            key={p.n}
            className="landing-card relative flex items-center gap-4 p-4"
            style={{ animation: `step-glow 5s ease-in-out ${i * 0.6}s infinite` }}
          >
            <span
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white"
              style={{ background: grad(p.color), boxShadow: `0 0 0 4px ${p.color}22` }}
            >
              {i + 1}
            </span>
            <div className="min-w-0">
              <div className="serif text-[16px] leading-tight text-[var(--ink-1)]">{p.title}</div>
              <div className="text-[12.5px] text-[var(--ink-3)]">{p.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Landing({
  input,
  setInput,
  go,
  replayLast,
}: {
  input: string;
  setInput: (s: string) => void;
  go: (s: string) => void;
  replayLast: () => void;
}) {
  return (
    <div className="landing">
      {/* nav */}
      <nav className="mx-auto flex max-w-[1180px] items-center justify-between px-6 py-6">
        <div className="flex items-baseline gap-2.5">
          <span className="serif text-xl font-semibold tracking-tight text-[var(--ink-1)]">Ross MD</span>
          <span className="text-xs text-[var(--ink-3)]">healthcare regulatory</span>
        </div>
        <div className="flex items-center gap-5 text-sm text-[var(--ink-2)]">
          <Link href="/corpus" className="hidden hover:text-[var(--ink-1)] sm:inline">
            The corpus
          </Link>
          <button
            onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}
            className="hidden hover:text-[var(--ink-1)] sm:inline"
          >
            How it works
          </button>
          <button onClick={replayLast} className="btn-dark px-4 py-2 text-sm font-medium">
            See it work
          </button>
        </div>
      </nav>

      {/* hero */}
      <div className="mx-auto grid max-w-[1180px] grid-cols-1 items-center gap-10 px-6 pt-10 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <div className="mb-3 text-xs font-medium uppercase tracking-[0.18em] text-[var(--accent)]">
            Refusal Rescue · payer denial → cited appeal packet
          </div>
          <h1 className="serif text-balance text-[clamp(2.6rem,5vw,4.4rem)] font-light leading-[1.02] tracking-[-0.02em] text-[var(--ink-1)]">
            Read the denial.
            <br />
            Win the{" "}
            <span className="relative inline-block italic" style={{ color: "var(--accent)" }}>
              appeal
            </span>
            .
          </h1>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            {HERO_PILLS.map((p) => (
              <span key={p.label} className="pill text-[15px] text-[var(--ink-1)]">
                <span style={{ color: p.color, fontWeight: 600 }}>{p.glyph}</span>
                {p.label}
              </span>
            ))}
            <span className="text-[15px] text-[var(--ink-2)]">— from the denial letter.</span>
          </div>

          <p className="mt-6 max-w-md text-[15px] leading-relaxed text-[var(--ink-2)]">
            A payer refused the claim. Drop in the denial — Aetna, UnitedHealthcare, an ERISA plan. A
            team of agents reads it, pulls the member's appeal rights (ERISA, ACA external review, the
            No Surprises Act) and the payer's own policy, and builds a cited appeal packet that
            reverses it. Federal healthcare law. For counsel — not advice.
          </p>

          {/* input */}
          <div className="landing-card mt-7 p-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              aria-label="Describe the situation for Ross to analyze"
              placeholder="UnitedHealthcare denied our hospital's claim for a 4-day cardiac admission as 'not medically necessary,' citing MCG criteria — the patient had chest pain and elevated troponins. Build the appeal."
              className="h-28 w-full resize-none rounded-xl bg-transparent p-3 text-[14px] leading-relaxed text-[var(--ink-1)] outline-none placeholder:text-[var(--ink-3)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") go(input);
              }}
            />
            <div className="flex items-center justify-between gap-3 px-1 pb-1">
              <button onClick={replayLast} className="px-2 py-1 text-[13px] text-[var(--ink-2)] hover:text-[var(--ink-1)]">
                ▶ Replay a recorded run
              </button>
              <button onClick={() => go(input)} className="btn-dark px-5 py-2.5 text-sm font-medium">
                Build the case  ⌘↵
              </button>
            </div>
          </div>

          {/* scenario cards — full query, not just a label */}
          <div className="mt-5">
            <div className="mono mb-2 text-[10px] uppercase tracking-widest text-[var(--ink-3)]">
              or try a scenario
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {EXAMPLES.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => go(ex.text)}
                  className="btn-ghost p-3 text-left"
                >
                  <div className="text-[12.5px] font-semibold text-[var(--ink-1)]">{ex.chip}</div>
                  <div className="mt-1 text-[11.5px] leading-relaxed text-[var(--ink-2)]">{ex.text}</div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* hero graphic — preview of the live pipeline */}
        <div className="hidden lg:block">
          <PipelinePreview />
        </div>
      </div>

      {/* how it works */}
      <div id="how" className="mx-auto mt-16 max-w-[1180px] scroll-mt-10 px-6 pb-20">
        <div className="border-t border-[var(--warm-line)] pt-10">
          <div className="serif mb-1 text-2xl text-[var(--ink-1)]">How Ross MD works</div>
          <p className="mb-7 text-[14px] text-[var(--ink-2)]">
            One arrangement in. A compliant structure out. Seven specialized agents, in concert.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {PHASES.map((p, i) => (
              <div key={p.n} className="landing-card p-4">
                <div className="mb-2 flex items-center gap-2">
                  <span
                    className="flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold text-white"
                    style={{ background: grad(p.color) }}
                  >
                    {i + 1}
                  </span>
                  <span className="serif text-[15px] text-[var(--ink-1)]">{p.title}</span>
                </div>
                <p className="text-[12.5px] leading-relaxed text-[var(--ink-2)]">{p.desc}</p>
              </div>
            ))}
          </div>
          <div className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px] text-[var(--ink-3)]">
            <span>Stark · AKS · FCA · HIPAA · EMTALA indexed</span>
            <span>·</span>
            <span>Every citation clickable & verifiable</span>
            <span>·</span>
            <span>Work product for healthcare counsel — not advice</span>
          </div>

          {/* ClickHouse pitch — the agent's memory layer */}
          <div className="mt-6 rounded-xl border border-[var(--warm-line)] bg-[var(--panel-2,transparent)] p-4 text-[13.5px] leading-relaxed text-[var(--ink-2)]">
            <span className="font-semibold text-[var(--accent)]">ClickHouse</span> is the agent's
            legal memory: <span className="text-[var(--ink-1)]">vector retrieval</span>,{" "}
            <span className="text-[var(--ink-1)]">authority graph</span>,{" "}
            <span className="text-[var(--ink-1)]">source cache</span>, and{" "}
            <span className="text-[var(--ink-1)]">replayable reasoning trace</span> in one system.{" "}
            <Link href="/corpus" className="text-[var(--accent)] hover:underline">
              See the memory →
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function Theater({ state }: { state: ReturnType<typeof useRoss>["state"] }) {
  return (
    <aside className="panel h-fit p-4">
      <div className="mono mb-3 text-[11px] uppercase tracking-widest text-[var(--ink-faint)]">
        agent theater
      </div>
      <div className="relative">
        <div className="absolute bottom-5 left-[26px] top-5 w-px bg-[var(--line)]" />
        <div className="space-y-1">
          {PIPELINE.map((a, i) => {
            const st: AgentState = state.agents[a.key] ?? "idle";
            const active = st === "active";
            return (
              <div key={a.key}>
                <div className="relative flex items-center gap-3 rounded-lg p-2 transition-colors"
                  style={{ background: active ? "var(--panel-2)" : "transparent" }}>
                  <span
                    className={`relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold transition-colors ${active ? "pulsing" : ""}`}
                    style={{
                      background: st === "idle" ? `${a.color}1f` : grad(a.color),
                      color: st === "idle" ? a.color : "#fff",
                      boxShadow: st === "idle" ? `inset 0 0 0 1px ${a.color}55` : `0 0 0 4px ${a.color}22`,
                    }}
                  >
                    {st === "done" ? "✓" : st === "reject" ? "↻" : i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium"
                        style={{ color: st === "idle" ? "var(--ink-faint)" : "var(--ink)" }}>
                        {a.label}
                      </span>
                      {active && <span className="blink text-[10px]" style={{ color: a.color }}>working…</span>}
                      {st === "reject" && <span className="text-[10px] text-[var(--red)]">revising</span>}
                    </div>
                    <div className="text-[11px] text-[var(--ink-faint)]">{a.sub}</div>
                  </div>
                </div>
                {a.key === "researcher" && state.issues.length > 0 && (
                  <div className="ml-[34px] mt-1 mb-1 space-y-1">
                    {state.issues.map((is) => {
                      const done = !!state.research[is.id]?.bottom_line;
                      const sc =
                        is.strength === "strong"
                          ? "var(--green)"
                          : is.strength === "speculative"
                          ? "var(--ink-faint)"
                          : "var(--amber)";
                      return (
                        <div key={is.id} className="text-[10.5px]">
                          <div className="flex items-center gap-1.5">
                            <span
                              className="h-1.5 w-1.5 shrink-0 rounded-full"
                              style={{ background: done ? "var(--green)" : sc }}
                            />
                            <span className="truncate text-[var(--ink-dim)]" title={is.theory || is.label}>
                              {is.label}
                            </span>
                          </div>
                          {is.safe_harbor && (
                            <div className="ml-3 truncate text-[9.5px] text-[var(--ink-faint)]" title={is.safe_harbor}>
                              {is.safe_harbor}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {state.facts?.summary && (
        <div className="mt-4 border-t border-[var(--line)] pt-3">
          <div className="serif mb-1.5 text-[13px] text-[var(--ink-dim)]">Facts as Ross sees them</div>
          <p className="text-[12.5px] leading-relaxed text-[var(--ink-dim)]">{state.facts.summary}</p>
          {!!state.facts.missing?.length && <MissingFacts items={state.facts.missing} />}
        </div>
      )}
    </aside>
  );
}

function MissingFacts({ items }: { items: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-[11px] text-[var(--amber)] hover:brightness-125"
      >
        <span>{open ? "▾" : "▸"}</span>
        {items.length} open questions to confirm
      </button>
      {open && (
        <ul className="mt-2 space-y-1 border-l border-[var(--line-2)] pl-3">
          {items.map((m, i) => (
            <li key={i} className="text-[11px] leading-relaxed text-[var(--ink-faint)]">
              {m.replace(/\.$/, "")}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Tabs({
  tab,
  setTab,
  nAttacks,
  running,
  ddOn,
}: {
  tab: string;
  setTab: (t: "activity" | "work" | "adversary" | "observability") => void;
  nAttacks?: number;
  running: boolean;
  ddOn: boolean;
}) {
  const tabs = [
    { k: "activity", label: "Agent Activity" },
    { k: "work", label: "Work Product" },
    { k: "adversary", label: `Adversary's Best Shot${nAttacks ? ` (${nAttacks})` : ""}` },
    ...(ddOn ? [{ k: "observability", label: "Observability" }] : []),
  ];
  return (
    <div className="flex border-b border-[var(--line)]">
      {tabs.map((t) => (
        <button
          key={t.k}
          onClick={() => setTab(t.k as "activity" | "work" | "adversary" | "observability")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-xs ${
            tab === t.k
              ? "border-b-2 border-[var(--gold)] text-[var(--ink)]"
              : "text-[var(--ink-faint)] hover:text-[var(--ink-dim)]"
          }`}
        >
          {t.k === "activity" && running && (
            <span className="blink h-1.5 w-1.5 rounded-full bg-[var(--ross)]" />
          )}
          {t.label}
        </button>
      ))}
    </div>
  );
}

function Observability({
  state,
  ddSite,
}: {
  state: ReturnType<typeof useRoss>["state"];
  ddSite: string;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const t0 = state.log.find((e) => e._ts)?._ts ?? 0;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [state.log.length]);

  const ddUrl =
    ddSite && state.runId
      ? `https://${ddSite}/logs?query=${encodeURIComponent(`service:ross-agents run:${state.runId}`)}`
      : ddSite
      ? `https://${ddSite}/logs?query=service:ross-agents`
      : "";

  const sev = (ev: RossEvent): string => {
    if (ev.event === "error") return "var(--red)";
    if (ev.payload?.verdict === "revise" || ev.event === "harvey_reject") return "var(--amber)";
    if (ev.event === "llm_call") return "var(--ink-faint)";
    return AGENT_COLOR[ev.agent] ?? "var(--ink-dim)";
  };
  const tags = (ev: RossEvent): string => {
    const p = ev.payload || {};
    const bits: string[] = [];
    if (p.model) bits.push(p.model.split("/").pop());
    if (p.completion_tokens) bits.push(`${p.completion_tokens}tok`);
    if (p.posture) bits.push(`posture:${p.posture}`);
    if (p.verdict) bits.push(`verdict:${p.verdict}`);
    if (p.n_attacks != null) bits.push(`attacks:${p.n_attacks}`);
    if (p.n != null) bits.push(`fanout:${p.n}`);
    if (Array.isArray(p.authorities)) bits.push(`authorities:${p.authorities.length}`);
    if (Array.isArray(p.issues)) bits.push(`issues:${p.issues.length}`);
    return bits.join(" ");
  };

  return (
    <div className="flex h-full flex-col">
      {/* datadog bar */}
      <div className="flex items-center justify-between border-b border-[var(--line)] bg-[var(--panel-2)] px-5 py-2.5">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="h-2 w-2 rounded-full" style={{ background: "#774aa4" }} />
          <span className="text-[var(--ink)]">Datadog</span>
          <span className="text-[var(--ink-faint)]">· service:ross-agents{ddSite ? ` · ${ddSite}` : ""}</span>
          <span className="text-[var(--ink-faint)]">· {state.log.length} events · {state.tokens.toLocaleString()} tok</span>
        </div>
        {ddUrl && (
          <a href={ddUrl} target="_blank" className="text-[11px] text-[var(--ross)] hover:underline">
            Open in Datadog ↗
          </a>
        )}
      </div>
      <div className="mono min-h-0 flex-1 overflow-y-auto p-4 text-[11px] leading-relaxed">
        {state.log.length === 0 && (
          <div className="text-[var(--ink-faint)]">Telemetry streams here — same events shipped to Datadog.</div>
        )}
        {state.log.map((ev, i) => {
          const dt = ev._ts && t0 ? ((ev._ts - t0) / 1000).toFixed(2) : "0.00";
          const tg = tags(ev);
          return (
            <div key={i} className="flex gap-2 whitespace-pre-wrap">
              <span className="shrink-0 tabnum text-[var(--ink-faint)]">{dt.padStart(6)}s</span>
              <span className="shrink-0" style={{ color: sev(ev), width: 96 }}>
                {(AGENT_NAME[ev.agent] ?? ev.agent).toLowerCase()}
              </span>
              <span className="shrink-0 text-[var(--ink-dim)]" style={{ width: 90 }}>
                {ev.event}
              </span>
              {tg && <span className="text-[var(--ink-faint)]">{tg}</span>}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function ActivityFeed({
  state,
}: {
  state: ReturnType<typeof useRoss>["state"];
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const items = useMemo(
    () => state.log.map((ev) => ({ ev, d: describe(ev) })).filter((x) => x.d),
    [state.log]
  );
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items.length]);

  const nAuth = useMemo(
    () => new Set(Object.values(state.research).flatMap((r) => r.authorities.map((a) => a.doc_id))).size,
    [state.research]
  );

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="serif text-lg text-[var(--ink)]">Ross is working the file</div>
          <div className="text-[12px] text-[var(--ink-dim)]">
            Seven specialized agents · {state.issues.length || "…"} issues · {nAuth} authorities pulled ·{" "}
            {state.tokens.toLocaleString()} tokens reasoned
          </div>
        </div>
        {state.running && <span className="blink text-[11px] text-[var(--ross)]">● live</span>}
      </div>

      <div className="relative pl-4">
        <div className="absolute bottom-2 left-[7px] top-2 w-px bg-[var(--line)]" />
        <div className="space-y-2.5">
          {items.map(({ ev, d }, i) => {
            const color = AGENT_COLOR[ev.agent] ?? "var(--ink-faint)";
            if (d!.text === "" && d!.mono)
              return (
                <div key={i} className="fade-up flex items-center gap-2 pl-3 text-[10.5px] text-[var(--ink-faint)]">
                  <span className="mono">{d!.mono}</span>
                </div>
              );
            return (
              <div key={i} className="fade-up relative flex gap-3">
                <span
                  className="absolute left-[-13px] top-[5px] h-2 w-2 rounded-full"
                  style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                />
                <div className="min-w-0">
                  <span className="text-[11px] font-semibold" style={{ color }}>
                    {AGENT_NAME[ev.agent] ?? ev.agent}
                  </span>
                  <span className="ml-2 text-[12.5px] text-[var(--ink-dim)]">{d!.text}</span>
                </div>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}

function FollowUp({
  facts,
  onAsk,
}: {
  facts?: { summary?: string; missing?: string[] };
  onAsk: (q: string) => void;
}) {
  const [q, setQ] = useState("");
  const open = (facts?.missing ?? []).slice(0, 4);
  return (
    <div className="border-t border-[var(--line)] bg-[var(--panel-2)] p-4">
      {open.length > 0 && (
        <div className="mb-2.5">
          <div className="serif mb-1.5 text-[12px] text-[var(--gold)]">
            Ross needs to know — answer to tighten the analysis
          </div>
          <div className="flex flex-wrap gap-1.5">
            {open.map((m, i) => (
              <button
                key={i}
                onClick={() => setQ(m.replace(/[.;]$/, "") + ": ")}
                title={m}
                className="max-w-[260px] truncate rounded-full border border-[var(--line-2)] px-2.5 py-1 text-[11px] text-[var(--ink-dim)] hover:border-[var(--gold)] hover:text-[var(--ink)]"
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && q.trim()) {
              onAsk(q.trim());
              setQ("");
            }
          }}
          aria-label="Ask Ross a follow-up or add facts to re-analyze"
          placeholder="Answer a question, add facts, or ask a follow-up — Ross re-analyzes with the new context"
          className="mono min-w-0 flex-1 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--ross)] focus-visible:ring-2 focus-visible:ring-[var(--gold)]"
        />
        <button
          onClick={() => {
            if (q.trim()) {
              onAsk(q.trim());
              setQ("");
            }
          }}
          className="shrink-0 rounded-lg bg-[var(--gold)] px-4 py-2 text-[13px] font-semibold text-black hover:brightness-110"
        >
          Re-analyze ↵
        </button>
      </div>
    </div>
  );
}

type Tier = "corpus" | "web" | "none";
const TIER_COLOR: Record<Tier, string> = {
  corpus: "var(--green)",
  web: "var(--amber)",
  none: "var(--ink-faint)",
};

function WorkProduct({
  draft,
  running,
  onCite,
}: {
  draft?: { doc_type?: string; title?: string; body_markdown?: string };
  running: boolean;
  onCite: (cite: string) => void;
}) {
  const body = draft?.body_markdown;
  const [tiers, setTiers] = useState<Record<string, Tier>>({});

  // resolve every inline [Cite:] against the corpus in ONE batch request → tag tier
  useEffect(() => {
    if (!body) return;
    const cites = [
      ...new Set([...body.matchAll(/\[Cite:\s*([^\]]+)\]/g)].map((m) => m[1].trim())),
    ];
    if (!cites.length) return;
    let cancelled = false;
    fetch(`${API}/api/cites`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ queries: cites }),
    })
      .then((r) => r.json())
      .then((map: Record<string, { tier: Tier; found: boolean }>) => {
        if (cancelled) return;
        const out: Record<string, Tier> = {};
        for (const c of cites) out[c] = map[c]?.tier ?? "none";
        setTiers(out);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [body]);

  if (!body)
    return (
      <div className="flex h-[60vh] items-center justify-center text-sm text-[var(--ink-faint)]">
        {running ? (
          <span className="blink">Ross is building the work product…</span>
        ) : (
          "Work product will render here."
        )}
      </div>
    );

  const counts = { corpus: 0, web: 0, none: 0 };
  Object.values(tiers).forEach((t) => (counts[t] += 1));
  const total = Object.keys(tiers).length;

  return (
    <div className="p-7">
      {draft?.doc_type && (
        <div className="mono mb-2 text-[10px] uppercase tracking-widest text-[var(--gold)]">
          {draft.doc_type.replace("_", " ")}
        </div>
      )}
      <h2 className="serif mb-3 text-2xl font-semibold leading-tight">{draft?.title}</h2>
      {total > 0 && (
        <div className="mb-5 flex flex-wrap items-center gap-3 border-y border-[var(--line)] py-2 text-[11px]">
          <span className="text-[var(--ink-faint)]">{total} citations</span>
          {counts.corpus > 0 && (
            <span style={{ color: "var(--green)" }}>● {counts.corpus} verified</span>
          )}
          {counts.web > 0 && <span style={{ color: "var(--amber)" }}>● {counts.web} web</span>}
          {counts.none > 0 && (
            <span className="text-[var(--ink-faint)]">● {counts.none} unverified</span>
          )}
        </div>
      )}
      <Markdown text={body} onCite={onCite} tiers={tiers} />
    </div>
  );
}

function Markdown({
  text,
  onCite,
  tiers,
}: {
  text: string;
  onCite: (c: string) => void;
  tiers: Record<string, Tier>;
}) {
  const lines = text.split("\n");
  return (
    <div className="space-y-2 text-[13.5px] leading-relaxed text-[var(--ink)]">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-2" />;
        if (line.startsWith("### "))
          return (
            <h4 key={i} className="serif mt-4 text-[15px] font-semibold">
              {inline(line.slice(4), onCite, tiers)}
            </h4>
          );
        if (line.startsWith("## "))
          return (
            <h3 key={i} className="serif mt-5 text-lg font-semibold">
              {inline(line.slice(3), onCite, tiers)}
            </h3>
          );
        if (line.startsWith("# "))
          return (
            <h2 key={i} className="serif mt-5 text-xl font-semibold">
              {inline(line.slice(2), onCite, tiers)}
            </h2>
          );
        if (/^\s*[-*]\s/.test(line))
          return (
            <div key={i} className="flex gap-2 pl-3">
              <span className="text-[var(--ink-faint)]">·</span>
              <span>{inline(line.replace(/^\s*[-*]\s/, ""), onCite, tiers)}</span>
            </div>
          );
        return <p key={i}>{inline(line, onCite, tiers)}</p>;
      })}
    </div>
  );
}

function inline(
  s: string,
  onCite: (c: string) => void,
  tiers: Record<string, Tier>
): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /\[Cite:\s*([^\]]+)\]|\*\*([^*]+)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    if (m[1]) {
      const cite = m[1].trim();
      const tier = tiers[cite];
      const color = tier ? TIER_COLOR[tier] : "var(--ross)";
      out.push(
        <span
          key={k++}
          className="cite"
          onClick={() => onCite(cite)}
          title={
            tier === "corpus"
              ? "verified — in corpus"
              : tier === "web"
              ? "fetched from web — not verified"
              : tier === "none"
              ? "not in corpus — verify"
              : "resolving…"
          }
          style={{ color, borderBottomColor: color }}
        >
          {cite}
        </span>
      );
    } else if (m[2]) {
      out.push(
        <strong key={k++} className="font-semibold">
          {m[2]}
        </strong>
      );
    }
    last = re.lastIndex;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}

const SEV_COLOR: Record<string, string> = {
  fatal: "var(--red)",
  serious: "var(--amber)",
  annoying: "var(--ink-faint)",
};

function AdversaryPanel({ state }: { state: ReturnType<typeof useRoss>["state"] }) {
  const adv = state.adversary;
  return (
    <div className="p-7">
      <p className="mb-5 text-sm text-[var(--ink-dim)]">
        How opposing counsel attacks this — and Ross&apos;s pre-emption. Battle-tested, not naive.
      </p>
      {adv?.weakest_link && (
        <div className="mb-5 rounded-lg border border-[var(--red)] bg-[color-mix(in_srgb,var(--red)_8%,transparent)] p-4">
          <div className="serif text-[13px] text-[var(--red)]">Weakest link</div>
          <div className="mt-1 text-[13.5px] leading-relaxed">{adv.weakest_link}</div>
        </div>
      )}
      {!adv && <div className="text-xs text-[var(--ink-faint)]">Adversary has not run yet.</div>}
      <div className="space-y-3">
        {adv?.attacks?.map((a, i) => (
          <div key={i} className="panel p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="serif text-[14px] leading-snug text-[var(--ink)]">
                <span className="text-[var(--red)]">⚔</span> {a.attack}
              </div>
              {a.severity && (
                <span
                  className="mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide"
                  style={{ color: SEV_COLOR[a.severity] ?? "var(--ink-faint)", border: `1px solid ${SEV_COLOR[a.severity] ?? "var(--line-2)"}` }}
                >
                  {a.severity}
                </span>
              )}
            </div>
            {a.basis && <div className="mt-1 text-[11px] text-[var(--ink-faint)]">{a.basis}</div>}
            {a.our_preemption && (
              <div className="mt-2.5 border-l-2 border-[var(--green)] pl-3 text-[12.5px] leading-relaxed text-[var(--ink-dim)]">
                <span className="text-[var(--green)]">Ross&apos;s answer — </span>
                {a.our_preemption}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function RightRail({
  state,
  onCite,
}: {
  state: ReturnType<typeof useRoss>["state"];
  onCite: (cite: string, a?: Authority) => void;
}) {
  const allAuthorities = useMemo(() => {
    const seen = new Set<string>();
    const out: Authority[] = [];
    for (const r of Object.values(state.research))
      for (const a of r.authorities)
        if (a.doc_id && !seen.has(a.doc_id)) {
          seen.add(a.doc_id);
          out.push(a);
        }
    return out;
  }, [state.research]);

  const strat = state.strategy;
  return (
    <aside className="flex flex-col gap-4">
      {strat?.killer_move && (
        <div className="panel p-4">
          <div className="mono mb-2 flex items-center justify-between text-[11px] uppercase tracking-widest text-[var(--ink-faint)]">
            <span>the play</span>
            {strat.posture && (
              <span
                className="rounded px-1.5 py-0.5 text-[10px]"
                style={{
                  color:
                    strat.posture === "compliant"
                      ? "var(--green)"
                      : strat.posture === "high-risk"
                      ? "var(--red)"
                      : "var(--gold)",
                  border: "1px solid currentColor",
                }}
              >
                {strat.posture}
              </span>
            )}
          </div>
          <div className="serif text-[10px] uppercase tracking-widest text-[var(--gold)]">killer move</div>
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--ink)]">{strat.killer_move}</p>
          {!!strat.structure?.length && (
            <ol className="mt-3 space-y-1.5 border-t border-[var(--line)] pt-3">
              {strat.structure.map((s, i) => (
                <li key={i} className="flex gap-2 text-[12px] text-[var(--ink-dim)]">
                  <span className="text-[var(--gold-dim)]">{i + 1}.</span>
                  <span>{s}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
      <div className="panel p-4">
        <div className="mono mb-2 flex items-center justify-between text-[11px] uppercase tracking-widest text-[var(--gold)]">
          <span>harvey</span>
          {state.harvey.verdict && (
            <span
              style={{
                color: state.harvey.verdict === "approve" ? "var(--green)" : "var(--amber)",
              }}
            >
              {state.harvey.verdict === "approve" ? "approved" : "revising"}
            </span>
          )}
        </div>
        <div className="space-y-2">
          {state.harveyLog.length === 0 && (
            <div className="text-xs text-[var(--ink-faint)]">Harvey hasn&apos;t weighed in yet.</div>
          )}
          {state.harveyLog.map((line, i) => (
            <div
              key={i}
              className="fade-up border-l-2 border-[var(--gold-dim)] pl-3 text-[13px] italic text-[var(--ink)]"
            >
              &ldquo;{line}&rdquo;
            </div>
          ))}
        </div>
        {state.harvey.assessment && (
          <div className="mt-3 border-t border-[var(--line)] pt-3 text-[12px] text-[var(--ink-dim)]">
            {state.harvey.assessment}
          </div>
        )}
      </div>

      <div className="panel p-4">
        <div className="mono mb-2 text-[11px] uppercase tracking-widest text-[var(--ink-faint)]">
          the weapons · {allAuthorities.length}
        </div>
        <div className="max-h-[40vh] space-y-1.5 overflow-y-auto">
          {allAuthorities.length === 0 && (
            <div className="text-xs text-[var(--ink-faint)]">
              Authorities appear as researchers pull them.
            </div>
          )}
          {allAuthorities.map((a) => (
            <button
              key={a.doc_id}
              onClick={() => onCite(a.citation || a.title, a)}
              className="fade-up block w-full rounded-md border border-[var(--line)] p-2 text-left hover:border-[var(--ross)]"
            >
              <div className="mono text-[11px] text-[var(--ross)]">{a.citation || "—"}</div>
              <div className="truncate text-[11px] text-[var(--ink-dim)]">{a.title}</div>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
