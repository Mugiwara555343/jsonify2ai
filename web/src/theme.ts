export type ThemeMode = "light" | "dark";
export interface Theme { mode: ThemeMode; accent: string }

const STORAGE_KEY = "jsonify2ai.theme";

export function loadTheme(): Theme {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  const prefersDark = typeof window !== "undefined" && (window as any).matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  return { mode: "dark", accent: "#6366f1" };
}

export function saveTheme(t: Theme) { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(t)); } catch {} }

export function applyTheme(t: Theme) {
  const r = document.documentElement as HTMLElement;
  r.style.setProperty("--bg", t.mode === "dark" ? "#0f1115" : "#ffffff");
  r.style.setProperty("--fg", t.mode === "dark" ? "#e5e7eb" : "#111827");
  r.style.setProperty("--muted", t.mode === "dark" ? "#9ca3af" : "#6b7280");
  r.style.setProperty("--card", t.mode === "dark" ? "#111827" : "#f9fafb");
  r.style.setProperty("--border", t.mode === "dark" ? "#1f2937" : "#e5e7eb");
  r.style.setProperty("--accent", t.accent);
}
