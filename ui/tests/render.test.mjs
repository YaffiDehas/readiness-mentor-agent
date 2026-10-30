// Server-side render smoke test: every screen/card renders with realistic data, escapes hostile text, and shows the key content.
// (Proves the components do not crash and render the right information; it cannot judge how they LOOK - see the screenshots/preview for that.)
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { mkdirSync, rmSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, ".build");
let m, data;

before(async () => {
  mkdirSync(out, { recursive: true });
  await build({ entryPoints: [path.join(here, "render.entry.jsx")], outfile: path.join(out, "entry.mjs"), bundle: true, format: "esm", platform: "node",
    jsx: "automatic", packages: "external", logLevel: "silent", loader: { ".js": "jsx" } });
  m = await import(pathToFileURL(path.join(out, "entry.mjs")).href + `?t=${Date.now()}`);
  data = await m.collect();
});
after(() => rmSync(out, { recursive: true, force: true }));

const byType = (t, pred = () => true) => data.prompts.find((p) => p.type === t && pred(p));
const clean = (html) => html.replace(/<!-- -->/g, "");          // React SSR separates adjacent text nodes with comments
const has = (html, ...parts) => parts.forEach((p) => assert.ok(clean(html).includes(p), `missing: ${p}`));

test("the whole app renders its idle state: form, intro, header", () => {
  const h = m.view.app();
  has(h, "Readiness Mentor", "על איזו משימה עובדים?", "התחלת בדיקה", "איך זה עובד", 'dir="auto"');
  assert.ok(/<button class="btn primary" disabled=""[^>]*>התחלת בדיקה/.test(h), "start is disabled until a task is typed");
});

test("header shows model/LangSmith for a live server and a demo badge in demo mode", () => {
  has(m.view.header({ config: { model: "x/model", langsmith: true }, demo: false, theme: "light" }), "x/model", "LangSmith פעיל");
  const d = m.view.header({ config: { model: "דוגמה" }, demo: true, theme: "dark" });
  has(d, "מצב הדגמה"); assert.ok(!d.includes("LangSmith"));
});

test("topic card: title, progress, why, the free-text field with a disabled send button, and the quick answers", () => {
  const p = byType("text", (x) => x.kind === "topic");
  const h = m.view.prompt(p);
  has(h, "ארכיטקטורה", `נושא ${p.n} מתוך ${p.total}`, p.title, p.question, "למה זה חשוב", "<textarea", "אין כזה", "לא יודע/ת", "שליחה");
  assert.ok(!h.includes("קריטי"));
  assert.ok(/<button class="btn primary" disabled=""[^>]*>שליחה/.test(h), "send is disabled until something is typed");
  assert.ok(!h.includes("איפה לחפש"));
});

test("guidance card: real-file suggestions are labeled as suggestions (not facts), with the three ways to go on", () => {
  const p = byType("text", (x) => x.kind === "guidance");
  assert.ok(p, "demo run must produce a guidance prompt");
  const h = m.view.prompt({ ...p, note: "הנתיב src/x.tsx לא קיים בפרויקט." });
  has(h, "איפה לחפש", "הצעות מהפרויקט · לא עובדות מאומתות", p.guidance.files[0], "מילות חיפוש", "לא קיים בפרויקט", "אין כזה · ליצור חדש", "יש חשד שקיים", "לא יודע/ת · הסוכן יחליט");
  assert.ok(!h.includes("מנטור"));
});

test("a blocking-fact card says the agent will not invent it, and offers 'backend not ready' or the mentor instead of 'none exists'", () => {
  const base = { ...byType("text"), blocker: true, category: "api_dependency", title: "API של החניונים" };
  const first = m.view.prompt({ ...base, kind: "topic", guidance: null });
  has(first, "עובדה שאי אפשר להסיק מהקוד", "GET /api/", "לא יודע/ת");
  assert.ok(!first.includes("אין כזה"));
  const g = m.view.prompt({ ...base, kind: "guidance", note: "ואני לא ממציא אותה", guidance: { why: "w", files: ["src/services/vehicles.ts"], terms: [], dirs: [], dependencies: [] } });
  has(g, "ה-API עדיין לא מוכן", "לא מצאתי · שאלה למנטור", "ואני לא ממציא אותה");
  assert.ok(!g.includes("אין כזה") && !g.includes("יש חשד שקיים"));
});

test("mentor card (resumed session) offers 'no answer yet'", () => {
  const h = m.view.prompt({ ...byType("text"), kind: "mentor" });
  has(h, "תשובת המנטור", "מה המנטור ענה?", "עדיין אין תשובה");
});

test("an input error is announced next to the question", () => {
  has(m.view.prompt({ ...byType("text"), error: "התשובה ריקה." }), 'role="alert"', "התשובה ריקה.");
});

test("hostile text from the agent or project is escaped, never rendered as HTML", () => {
  const evil = { ...byType("text"), title: "<img src=x onerror=alert(1)> נושא", guidance: { why: "<script>alert(2)</script>", files: ["<b>x</b>"], terms: [], dirs: [], dependencies: [] } };
  const h = m.view.prompt(evil);
  assert.ok(h.includes("&lt;img src=x onerror=alert(1)&gt;") && h.includes("&lt;script&gt;alert(2)&lt;/script&gt;") && h.includes("&lt;b&gt;x&lt;/b&gt;"));
  assert.ok(!h.includes("<img src=x") && !h.includes("<script>alert") && !h.includes("<b>x</b>"));
});

test("choice card: options with pros/cons, evidence, recommended and new-dependency markers, own-option field", () => {
  const p = byType("choice");
  const h = m.view.prompt(p);
  has(h, "בחירת פתרון", `החלטה ${p.n} מתוך ${p.total}`, p.question, "מומלץ", "מבוסס על", p.options[0].evidence[0], "או כתבו אפשרות משלכם", "קבלת ההמלצה");
  const n = m.view.prompt({ ...p, options: [{ ...p.options[0], new_dependency: true, recommended: false }] });
  has(n, "ספרייה חדשה · לא קיימת בפרויקט");
});

test("save cards: session vs prompt wording", () => {
  has(m.view.prompt({ type: "save", kind: "session", path: "briefs/session-x.json", error: null }), "להמשיך אחרי שהמנטור יענה", "briefs/session-x.json");
  has(m.view.prompt({ type: "save", kind: "prompt", path: "briefs/prompt-x.md", error: null }), "לשמור את הפרומפט", "briefs/prompt-x.md", "לא לשמור");
});

test("an unknown prompt type degrades to a visible message instead of crashing", () => {
  has(m.view.prompt({ type: "from_the_future" }), "סוג בקשה לא מוכר");
});

test("timeline: phases, current step, log and cost meter", () => {
  const h = m.view.timeline({ status: "running", nodes: [{ name: "guardrails", at: 0 }, { name: "context_retrieval", at: 1200 }], usage: data.usage });
  has(h, "קליטת משימה", "סריקת הפרויקט", "שאלות ארכיטקטורה", "קורא את קבצי הפרויקט", "context_retrieval", "+1.2s", "טוקנים", "עלות בפועל");
  has(m.view.timeline({ status: "prompt", nodes: [], usage: null }), "ממתין לתשובה שלך");
  has(m.view.timeline({ status: "done", nodes: [{ name: "deliver", at: 0 }], usage: null }), "הסתיים");
});

test("finished card: prompt ready (findings with source labels, copy/download), open items, cancelled and out-of-scope", () => {
  const ok = m.view.finished(data.done.state);
  has(ok, "הפרומפט המקצועי מוכן", "אומת בפרויקט", "חשד שקיים", "Mock זמני", "העתקת הפרומפט", "הורדה כ-Markdown", "משימה חדשה");
  assert.ok(!ok.includes("לא הופק פרומפט"));
  const stop = m.view.finished({ outcome: "needs_mentor", topics: [{ id: "t1", title: "API של החניונים", status: "mentor_needed", paths: [] }],
    blocked: [{ id: "t1", question: "מהו ה-endpoint המדויק?" }], session_out: { topics: [] } });
  has(stop, "לא הופק פרומפט", "לא ממציא", "מהו ה-endpoint המדויק?", "לברר מול המנטור", "העתקת השאלות", "הורדת קובץ המשך");
  assert.ok(!stop.includes("העתקת הפרומפט"));
  has(m.view.finished({ cancelled: true, final_message: "בוטל" }), "ההרצה בוטלה");
  has(m.view.finished({ in_scope: false, final_message: "מחוץ" }), "המשימה מחוץ לתחום");
});

test("help dialog explains the flow, shortcuts and the source labels", () => {
  has(m.view.help(), 'role="dialog"', "איך זה עובד", "קיצורי מקלדת", "הסוכן מחליט לבד", "לא ממציא", "לפני שמתחילים", "אומת בפרויקט", "חשד שקיים", "אין כזה", "אישור מנטור");
});

test("task form offers the bundled sample projects as one-click choices", () => {
  has(m.view.form({ samples: [{ name: "parking_app", path: "/x/evals/fixtures/parking_app" }] }), "פרויקט לדוגמה לניסוי", "parking_app");
  assert.ok(!m.view.form({}).includes("פרויקט לדוגמה לניסוי"));
});

test("task form renders the project path left-to-right and quick examples", () => {
  has(m.view.form({}), 'dir="ltr"', "C:\\proj", "מסך רשימת חניונים", "גררו לכאן", "המשך מקובץ");
});

test("timeline shows the cost of every step in a table, and Finished offers the conversation summary download", () => {
  const usage = { model: "m", total: { calls: 2, input_tokens: 1000, output_tokens: 200, actual_usd: 0.002, theoretical_usd: 0.003 },
    by_node: [{ node: "guardrails", calls: 1, input_tokens: 400, output_tokens: 20, actual_usd: 0.0004, theoretical_usd: 0.0005 }, { node: "compose_prompt", calls: 1, input_tokens: 600, output_tokens: 180, actual_usd: 0.0016, theoretical_usd: 0.0025 }] };
  const h = m.view.timeline({ status: "done", nodes: [{ name: "guardrails", at: 1 }], usage });
  has(h, "עלות לפי שלב", "guardrails", "compose_prompt", "$0.0016");
  const withBtn = (res) => m.view.finished(res, { onSummary: () => {} });
  for (const res of [{ outcome: "prompt", brief_accepted: true, final_prompt: "x", topics: [] }, { outcome: "needs_mentor", blocked: [], topics: [] }, { cancelled: true, final_message: "x" }])
    has(withBtn(res), "הורדת תקציר שיחה");
  assert.ok(!m.view.finished({ outcome: "prompt", final_prompt: "x", topics: [] }).includes("הורדת תקציר שיחה"), "no button without a handler");
});

test("the first-run key card is a password field, explains where the key is kept, and has a disabled save until something is typed", () => {
  const h = m.view.keycard();
  has(h, "OPENROUTER_API_KEY", 'type="password"', "נשמר רק אצלכם במחשב");
  assert.ok(/<button class="btn primary" disabled=""[^>]*>שמירה והמשך/.test(h));
});
