import React from "react";
import { applyTheme, loadTheme, saveTheme, Theme } from "./theme";

export default function ThemeControls() {
  const [theme, setTheme] = React.useState<Theme>(() => loadTheme());
  React.useEffect(() => { applyTheme(theme); saveTheme(theme); }, [theme]);

  return (
    <div style={{
      display:"flex", alignItems:"center", gap:10, padding:8,
      border:"1px solid var(--border)", borderRadius:8, background:"var(--card)"
    }}>
      <span style={{fontSize:12, color:"var(--muted)"}}>Theme</span>
      <select
        value={theme.mode}
        onChange={e => setTheme(t => ({...t, mode: e.target.value as Theme["mode"]}))}
        style={{fontSize:12, padding:"4px 8px", background:"var(--bg)", color:"var(--fg)", border:"1px solid var(--border)", borderRadius:6}}
      >
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
      <span style={{fontSize:12, color:"var(--muted)"}}>Accent</span>
      <input
        type="color"
        value={theme.accent}
        onChange={e => setTheme(t => ({...t, accent: (e.target as HTMLInputElement).value}))}
        style={{width:28, height:20, padding:0, border:"1px solid var(--border)", borderRadius:4, background:"var(--bg)"}}
        title="Pick accent color"
      />
      <div style={{marginLeft:"auto", fontSize:11, color:"var(--muted)"}}>
        UI colors are saved locally
      </div>
    </div>
  );
}
