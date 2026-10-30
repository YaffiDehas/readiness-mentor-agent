import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import Header from "./components/Header.jsx";
import Help from "./components/Help.jsx";
import KeyCard from "./components/KeyCard.jsx";
import PromptCard from "./components/PromptCard.jsx";
import TaskForm from "./components/TaskForm.jsx";
import Timeline from "./components/Timeline.jsx";
import { createDemoTransport } from "./lib/demo.js";
import { TOPIC_STATUS } from "./lib/format.js";
import { nodeLabel } from "./lib/phases.js";
import { buildSummary } from "./lib/summary.js";
import { historyEntry, initialState, reducer } from "./lib/reducer.js";
import { realTransport } from "./lib/transport.js";

const DEMO_ONLY = typeof import.meta !== "undefined" && import.meta.env?.VITE_DEMO_ONLY === "1";
const wantsDemo = () => DEMO_ONLY || (typeof location !== "undefined" && new URLSearchParams(location.search).has("demo"));

function loadTheme() {
  try { return localStorage.getItem("rm-theme") || "light"; } catch { return "light"; }   // light unless the developer chose dark
}

function Intro() {
  return (
    <section className="card" aria-label="איך זה עובד">
      <h2>איך זה עובד</h2>
      <ol className="steps">
        <li>הסוכן קורא את הפרויקט ושואל כמה שאלות ארכיטקטורה: איפה כבר קיים דבר דומה, אילו ספריות ורכיבים בשימוש.</li>
        <li>לא יודעים? מקבלים הכוונה לאן לחפש. אחרי החיפוש: נתיב, "אין" (ייווצר חדש), "יש חשד" (לחפש לפני יצירה) או "לא יודע" (הצעות לבחירתכם).</li>
        <li>כתובת API או הרשאה שאי אפשר להסיק מהקוד: הסוכן לא ממציא, ומחזיר שאלה מדויקת למנטור (בלי פרומפט). אחרת מקבלים פרומפט מקצועי, כולל סעיף "לפני שמתחילים".</li>
      </ol>
    </section>
  );
}

function save(name, text, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const TopicList = ({ topics }) => (
  <ul className="list" aria-label="ממצאי ארכיטקטורה">
    {topics.map((t) => {
      const [label, tone] = TOPIC_STATUS[t.status] || [t.status, "muted"];
      return (
        <li key={t.id}>
          <span className={`chip ${tone}`}>{label}</span> <span dir="auto">{t.title}</span>
          {t.paths?.length > 0 && <div>{t.paths.map((f) => <span className="pathchip" key={f}>{f}</span>)}</div>}
        </li>
      );
    })}
  </ul>
);

export function Finished({ result, onReset, onSummary }) {
  const summaryBtn = onSummary && <button className="btn" onClick={onSummary}>הורדת תקציר שיחה</button>;
  if (result?.cancelled || result?.in_scope === false) {
    return (
      <section className="card">
        <h2>{result.cancelled ? "ההרצה בוטלה" : "המשימה מחוץ לתחום"}</h2>
        <p className="lead" dir="auto">{result.final_message}</p>
        <div className="row end">{summaryBtn}<button className="btn primary" onClick={onReset}>משימה חדשה</button></div>
      </section>
    );
  }
  const topics = result?.topics || [];
  if (result?.outcome === "needs_mentor") {
    const blocked = result.blocked || [];
    const questions = blocked.map((b, i) => `${i + 1}. ${b.question}`).join("\n");
    return (
      <section className="hero warn" aria-label="תוצאה">
        <span className="code">needs_mentor</span>
        <p className="big">לא הופק פרומפט · חסר מידע שאי אפשר להסיק</p>
        <p>הסוכן לא ממציא כתובות או הרשאות. יש לברר מול המנטור לפני שמתחילים לממש. השאלות מוכנות:</p>
        <ol className="steps">{blocked.map((b) => <li key={b.id} dir="auto">{b.question}</li>)}</ol>
        {topics.length > 0 && <TopicList topics={topics} />}
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn" onClick={() => navigator.clipboard?.writeText(questions)}>העתקת השאלות</button>
          {result.session_out && <button className="btn" onClick={() => save("readiness-session.json", JSON.stringify(result.session_out, null, 2), "application/json")}>הורדת קובץ המשך</button>}
          {summaryBtn}
          <span className="spacer" />
          <button className="btn primary" onClick={onReset}>משימה חדשה</button>
        </div>
        <p className="empty" dir="auto">כשתקבלו תשובה, פתחו את הקובץ בטופס המשימה ("המשך מקובץ") והסוכן יבקש רק את תשובות המנטור.</p>
      </section>
    );
  }
  return (
    <section className="hero ok" aria-label="תוצאה">
      <span className="code">{result?.brief_accepted ? "prompt_ready" : "prompt_unaccepted"}</span>
      <p className="big">{result?.brief_accepted ? "הפרומפט המקצועי מוכן" : "הפרומפט לא עבר את הבדיקה"}</p>
      <p dir="auto">{result?.final_message}</p>
      {topics.length > 0 && <TopicList topics={topics} />}
      {result?.final_prompt && <pre className="quote mono" dir="auto" style={{ whiteSpace: "pre-wrap", maxHeight: 360, overflow: "auto" }}>{result.final_prompt}</pre>}
      <div className="row" style={{ marginTop: 8 }}>
        {result?.final_prompt && <button className="btn" onClick={() => navigator.clipboard?.writeText(result.final_prompt)}>העתקת הפרומפט</button>}
        {result?.final_prompt && <button className="btn" onClick={() => save("implementation-prompt.md", result.final_prompt, "text/markdown")}>הורדה כ-Markdown</button>}
        {summaryBtn}
        <span className="spacer" />
        <button className="btn primary" onClick={onReset}>משימה חדשה</button>
      </div>
    </section>
  );
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [mode, setMode] = useState(wantsDemo() ? "demo" : "live");
  const [serverDown, setServerDown] = useState(false);
  const [theme, setTheme] = useState(loadTheme);
  const [help, setHelp] = useState(false);
  const abort = useRef(null);
  const busy = useRef(false);
  const transport = useMemo(() => (mode === "demo" ? createDemoTransport() : realTransport), [mode]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("rm-theme", theme); } catch { /* private mode: keep the in-memory choice */ }
  }, [theme]);

  useEffect(() => {
    let alive = true;
    setServerDown(false);
    transport.config().then((config) => alive && dispatch({ type: "config", config })).catch(() => alive && setServerDown(true));
    return () => { alive = false; };
  }, [transport]);

  const emit = useCallback((event) => dispatch({ type: "event", event, at: Date.now() }), []);

  const run = useCallback(async (fn) => {
    abort.current?.abort();
    abort.current = new AbortController();
    busy.current = true;
    try { await fn(abort.current.signal); } finally { busy.current = false; }
  }, []);

  const start = useCallback((body) => {
    dispatch({ type: "start", task: body.task, project: body.project });
    run((signal) => transport.start(body, emit, signal));
  }, [run, transport, emit]);

  const answer = useCallback((value) => {
    if (busy.current || !state.prompt) return;               // ignore double key presses while a request is in flight
    dispatch({ type: "answered", entry: historyEntry(state.prompt, value) });
    run((signal) => transport.resume(state.runId, value, emit, signal));
  }, [run, transport, emit, state.prompt, state.runId]);

  const reset = useCallback(() => { abort.current?.abort(); busy.current = false; dispatch({ type: "reset" }); }, []);
  const last = state.nodes.length ? state.nodes[state.nodes.length - 1].name : null;
  const downloadSummary = useCallback(() => save("readiness-summary.md", buildSummary({ task: state.task, project: state.project, history: state.history, result: state.result, usage: state.usage }), "text/markdown"),
    [state.task, state.project, state.history, state.result, state.usage]);
  const needsKey = mode === "live" && state.config && state.config.has_key === false;
  const saveKey = useCallback(async (key) => {
    await transport.saveKey(key);
    dispatch({ type: "config", config: { ...state.config, has_key: true } });
  }, [transport, state.config]);

  return (
    <div className="shell">
      <Header config={state.config} demo={mode === "demo"} theme={theme} onTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} onHelp={() => setHelp(true)} />
      {mode === "demo" && <div className="banner demo" role="note">מצב הדגמה: התהליך והנתונים כאן לדוגמה, ולא הרצה אמיתית של הסוכן.</div>}
      {serverDown && mode === "live" && (
        <div className="banner err" role="alert">
          לא ניתן להתחבר לשרת המקומי. הריצו <span className="mono">python -m agent.server</span> ורעננו, או{" "}
          <button className="example" onClick={() => setMode("demo")}>נסו את מצב ההדגמה</button>
        </div>
      )}
      <div className="grid">
        <main className="stack" aria-live="polite">
          {state.status === "idle" && needsKey && <KeyCard onSave={saveKey} />}
          {state.status === "idle" && !needsKey && <TaskForm key={mode} project={state.project} demo={mode === "demo"} samples={state.config?.samples} onStart={start} />}
          {state.status === "running" && (
            <section className="card" aria-busy="true">
              <h2>עובדים על זה…</h2>
              <p className="lead" dir="auto">{state.task}</p>
              <div className="now"><span className="spinner" aria-hidden="true" /><span>{last ? nodeLabel(last) : "מתחיל"}</span></div>
            </section>
          )}
          {state.status === "prompt" && state.prompt && <PromptCard prompt={state.prompt} onSubmit={answer} />}
          {state.status === "done" && <Finished result={state.result} onReset={reset} onSummary={downloadSummary} />}
          {state.status === "error" && (
            <section className="card">
              <h2>משהו השתבש</h2>
              <div className="banner err" role="alert" dir="auto" style={{ whiteSpace: "pre-wrap" }}>{state.error}</div>
              <div className="row end"><button className="btn primary" onClick={reset}>חזרה להתחלה</button></div>
            </section>
          )}
        </main>
        <aside className="side">
          {state.status === "idle" ? <Intro /> : <Timeline status={state.status} nodes={state.nodes} usage={state.usage} />}
        </aside>
      </div>
      {help && <Help onClose={() => setHelp(false)} />}
    </div>
  );
}
