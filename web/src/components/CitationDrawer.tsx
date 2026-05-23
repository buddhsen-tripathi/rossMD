"use client";
import { useEffect, useState } from "react";
import { API, Authority } from "@/lib/ross";

type Doc = {
  found: boolean;
  tier?: "corpus" | "web" | "none";
  verified?: boolean;
  doc_id?: string;
  doc_type?: string;
  title?: string;
  citation?: string;
  court?: string;
  url?: string;
  source_url?: string;
  text?: string;
};

export function CitationDrawer({
  open,
  cite,
  docId,
  surfacedBy,
  onClose,
}: {
  open: boolean;
  cite: string;
  docId?: string;
  surfacedBy?: string;
  onClose: () => void;
}) {
  const [doc, setDoc] = useState<Doc | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !cite) {
      setDoc(null);
      return;
    }
    setLoading(true);
    // resolve against the FULL corpus by the citation text (robust); docId is
    // only a hint — many inline cites won't be in the run's retrieved set.
    fetch(`${API}/api/cite?q=${encodeURIComponent(cite)}`)
      .then((r) => r.json())
      .then(setDoc)
      .catch(() => setDoc({ found: false }))
      .finally(() => setLoading(false));
  }, [open, cite]);

  // Esc closes the drawer (modal convention)
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Source for ${cite}`}
        className="panel relative h-full w-[560px] max-w-[92vw] overflow-y-auto overscroll-contain rounded-none border-l fade-up"
        style={{ background: "var(--panel-2)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-start justify-between gap-4 border-b border-[var(--line)] bg-[var(--panel-2)] p-5">
          <div>
            <div className="mono text-[11px] uppercase tracking-widest text-[var(--ink-faint)]">
              {doc?.doc_type ?? "authority"} · source
            </div>
            <div className="mono mt-1 text-[15px] text-[var(--gold)]">{cite}</div>
            {doc?.court && <div className="mt-1 text-xs text-[var(--ink-dim)]">{doc.court}</div>}
          </div>
          <button
            onClick={onClose}
            aria-label="Close source panel"
            className="text-[var(--ink-dim)] hover:text-[var(--ink)]"
          >
            ✕
          </button>
        </div>
        <div className="space-y-4 p-5">
          {surfacedBy && (
            <div className="text-xs text-[var(--ink-dim)]">
              Surfaced by{" "}
              <span className="text-[var(--ross)]">{surfacedBy}</span>
            </div>
          )}
          {loading && <div className="blink text-sm text-[var(--ink-dim)]">resolving citation…</div>}

          {doc && !doc.found && !loading && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm text-[var(--amber)]">
                <span className="rounded border border-[var(--amber)] px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                  not in corpus
                </span>
                Verify before relying on it.
              </div>
              <p className="text-[13px] leading-relaxed text-[var(--ink-dim)]">
                Ross flags any authority it can&apos;t pull from the corpus rather than asserting it
                blind. Confirm it at the source:
              </p>
              {doc.source_url && (
                <a
                  href={doc.source_url}
                  target="_blank"
                  className="inline-block rounded-md border border-[var(--line-2)] px-3 py-1.5 text-xs text-[var(--ross)] hover:border-[var(--ross)]"
                >
                  Look up “{cite}” ↗
                </a>
              )}
            </div>
          )}

          {doc?.found && (
            <>
              {doc.tier === "web" ? (
                <div className="flex items-center gap-2 rounded-md border border-[var(--amber)] bg-[color-mix(in_srgb,var(--amber)_8%,transparent)] px-2.5 py-1.5 text-[11px] text-[var(--amber)]">
                  <span className="font-semibold uppercase tracking-wide">⚠ fetched from web</span>
                  <span className="text-[var(--ink-dim)]">live primary source · not verified against corpus</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 rounded-md border border-[var(--green)] bg-[color-mix(in_srgb,var(--green)_8%,transparent)] px-2.5 py-1.5 text-[11px] text-[var(--green)]">
                  <span className="font-semibold uppercase tracking-wide">✓ verified</span>
                  <span className="text-[var(--ink-dim)]">primary-source text in Ross&apos;s corpus</span>
                </div>
              )}
              <div className="text-sm font-medium">{doc.title}</div>
              {doc.source_url && (
                <a
                  href={doc.source_url}
                  target="_blank"
                  className="inline-block rounded-md border border-[var(--line-2)] px-3 py-1.5 text-xs text-[var(--ross)] hover:border-[var(--ross)]"
                >
                  View original source ↗
                </a>
              )}
              <pre className="mono whitespace-pre-wrap text-[12px] leading-relaxed text-[var(--ink-dim)]">
                {doc.text?.slice(0, 12000)}
              </pre>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
