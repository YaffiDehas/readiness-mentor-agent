import { useState } from "react";

// First run of the desktop app: there is no .env, so the OpenRouter key is entered here. It is sent once to the local sidecar, stored for this user only,
// and never shown again (the server never returns it).
export default function KeyCard({ onSave }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!key.trim() || busy) return;
    setBusy(true);
    setError("");
    try { await onSave(key.trim()); setKey(""); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <section className="card" aria-label="מפתח OpenRouter">
      <h2>מפתח OpenRouter</h2>
      <p className="lead">הסוכן משתמש ב-OpenRouter. הדביקו את המפתח פעם אחת: הוא נשמר רק אצלכם במחשב ואינו מוצג שוב.</p>
      <label className="field" htmlFor="key">OPENROUTER_API_KEY</label>
      <input id="key" className="input mono" dir="ltr" type="password" autoComplete="off" spellCheck={false} placeholder="sk-or-v1-..." value={key}
        onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
      {error && <div className="banner err" role="alert" dir="auto">{error}</div>}
      <div className="row end"><button className="btn primary" disabled={!key.trim() || busy} onClick={submit}>שמירה והמשך</button></div>
    </section>
  );
}
