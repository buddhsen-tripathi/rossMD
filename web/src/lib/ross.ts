"use client";
import { useCallback, useRef, useState } from "react";

export const API = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

export type RossEvent = {
  agent: string;
  event: string;
  seq?: number;
  payload: Record<string, any>;
  _ts?: number; // client receive time (ms) — for the observability console
};

export type AgentState = "idle" | "active" | "done" | "reject";

export type Issue = {
  id: string;
  label: string;
  area?: string;
  strength?: string;
  safe_harbor?: string;
  theory?: string;
};
export type Authority = { doc_id: string; title: string; citation: string; url: string };

export type RossState = {
  running: boolean;
  runId?: string;
  agents: Record<string, AgentState>;
  facts?: { summary?: string; missing?: string[] };
  issues: Issue[];
  research: Record<string, { bottom_line?: string; authorities: Authority[] }>;
  strategy?: { posture?: string; killer_move?: string; strategy?: string; structure?: string[] };
  adversary?: {
    weakest_link?: string;
    n_attacks?: number;
    attacks?: { attack: string; basis?: string; severity?: string; our_preemption?: string }[];
  };
  draft?: { doc_type?: string; title?: string; body_markdown?: string };
  harvey: { round?: number; verdict?: string; one_liner: string; fixes?: string[]; assessment?: string };
  harveyLog: string[];
  tokens: number;
  log: RossEvent[];
};

const EMPTY: RossState = {
  running: false,
  agents: {},
  issues: [],
  research: {},
  harvey: { one_liner: "" },
  harveyLog: [],
  tokens: 0,
  log: [],
};

function reduce(s: RossState, ev: RossEvent): RossState {
  const n = { ...s, log: [...s.log, ev] };
  const { agent, event, payload } = ev;

  // generic agent lifecycle
  if (event === "start") n.agents = { ...n.agents, [agent]: "active" };
  if (event === "done" || event === "verdict") n.agents = { ...n.agents, [agent]: "done" };

  switch (`${agent}/${event}`) {
    case "orchestrator/run_start":
      n.runId = payload.run_id;
      break;
    case "intake/done":
      n.facts = { summary: payload.summary, missing: payload.missing };
      break;
    case "issue_spotter/done":
      n.issues = payload.issues ?? [];
      break;
    case "researcher/start":
      n.agents = { ...n.agents, researcher: "active" };
      break;
    case "researcher/retrieved":
      n.research = {
        ...n.research,
        [payload.issue_id]: {
          ...(n.research[payload.issue_id] ?? { authorities: [] }),
          authorities: payload.authorities ?? [],
        },
      };
      break;
    case "researcher/done":
      n.research = {
        ...n.research,
        [payload.issue_id]: {
          ...(n.research[payload.issue_id] ?? { authorities: [] }),
          bottom_line: payload.bottom_line,
        },
      };
      break;
    case "strategist/done":
      n.strategy = {
        posture: payload.posture,
        killer_move: payload.killer_move,
        strategy: payload.strategy,
        structure: payload.structure,
      };
      break;
    case "adversary/done":
      n.adversary = {
        weakest_link: payload.weakest_link,
        n_attacks: payload.n_attacks,
        attacks: payload.attacks ?? [],
      };
      break;
    case "drafter/done":
      n.draft = {
        doc_type: payload.doc_type,
        title: payload.title,
        body_markdown: payload.body_markdown,
      };
      break;
    case "harvey/verdict":
      n.harvey = {
        verdict: payload.verdict,
        one_liner: payload.one_liner,
        fixes: payload.fixes,
        assessment: payload.assessment,
      };
      if (payload.one_liner) n.harveyLog = [...n.harveyLog, payload.one_liner];
      break;
    case "orchestrator/harvey_reject":
      n.agents = { ...n.agents, drafter: "reject" };
      break;
    case "orchestrator/run_done":
      n.running = false;
      break;
  }

  if (event === "llm_call" && payload.completion_tokens) {
    n.tokens = s.tokens + (payload.prompt_tokens ?? 0) + (payload.completion_tokens ?? 0);
  }
  return n;
}

export function useRoss() {
  const [state, setState] = useState<RossState>(EMPTY);
  const esRef = useRef<EventSource | null>(null);

  const run = useCallback((scenario: string, replayId?: string, speed?: number) => {
    esRef.current?.close();
    setState({ ...EMPTY, running: true });
    const url = replayId
      ? `${API}/api/replay/${replayId}${speed ? `?speed=${speed}` : ""}`
      : `${API}/api/stream?scenario=${encodeURIComponent(scenario)}`;
    const es = new EventSource(url);
    esRef.current = es;
    es.onmessage = (e) => {
      const ev: RossEvent = JSON.parse(e.data);
      if (ev.event === "stream_end") {
        es.close();
        setState((s) => ({ ...s, running: false }));
        return;
      }
      ev._ts = Date.now();
      setState((s) => reduce(s, ev));
    };
    es.onerror = () => {
      es.close();
      setState((s) => ({ ...s, running: false }));
    };
  }, []);

  return { state, run };
}
