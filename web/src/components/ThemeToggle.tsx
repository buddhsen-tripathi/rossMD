"use client";
import { useEffect, useState } from "react";

type Theme = "dark" | "light";

/**
 * Dark/light theme toggle. The actual theme lives as `data-theme` on <html>
 * (set pre-paint by the inline script in layout.tsx) and is persisted to
 * localStorage. This button just flips it and keeps its icon in sync.
 *
 * `onChange` lets canvas pages (corpus) react — they can't read CSS variables.
 */
export function ThemeToggle({
  className = "",
  onChange,
}: {
  className?: string;
  onChange?: (t: Theme) => void;
}) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const current = (document.documentElement.getAttribute("data-theme") as Theme) || "dark";
    setTheme(current);
    setMounted(true);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("ross-theme", next);
    } catch {
      /* ignore (private mode) */
    }
    onChange?.(next);
  }

  const label = `Switch to ${theme === "dark" ? "light" : "dark"} mode`;
  return (
    <button
      onClick={toggle}
      aria-label={label}
      title={label}
      className={
        "flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line-2)] text-[13px] text-[var(--ink-dim)] transition-colors hover:border-[var(--gold)] hover:text-[var(--gold)] " +
        className
      }
    >
      {/* sun while dark (click → light), moon while light (click → dark) */}
      <span aria-hidden suppressHydrationWarning>
        {mounted ? (theme === "dark" ? "☀" : "☾") : "☀"}
      </span>
    </button>
  );
}
