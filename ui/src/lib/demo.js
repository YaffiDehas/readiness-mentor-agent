// Demo transport: a scripted run that speaks the SAME event protocol as agent/server.py, so the UI can be explored (and screenshotted/tested)
// with no server and no API key. The data is illustrative sample data, NOT the output of a real agent run - the UI labels it as such.
export const DEMO_TASK = "מסך רשימת חניונים: שם, שעת כניסה ויציאה, חיפוש אחרי 3 תווים, בעיצוב הקיים";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const FILES = ["src/screens/VehicleListScreen.tsx", "src/screens/ReportsScreen.tsx", "src/components/ui/SearchInput.tsx", "src/components/ui/ListRow.tsx",
  "src/hooks/useDebouncedValue.ts", "src/services/http.ts", "src/services/vehicles.ts", "src/theme/theme.ts"];

const TOPICS = [
  { id: "t1", title: "איפה נמצאים מסכי הרשימה", question: "באיזו תיקייה נמצאים מסכי הרשימה הקיימים?", why: "כדי להוסיף את המסך במקום שבו הפרויקט כבר שם מסכים", category: "placement" },
  { id: "t2", title: "מסך רשימה עם חיפוש", question: "איזה מסך קיים כבר מציג רשימה עם חיפוש?", why: "כדי לשחזר את אותו דפוס במקום להמציא חדש", category: "similar_implementation" },
  { id: "t3", title: "רכיב חיפוש קיים", question: "האם יש כבר רכיב חיפוש, או ספריית רכיבים שיש בה אחד?", why: "כדי להשתמש ברכיב קיים ולא ליצור כפילות", category: "reusable_components" },
  { id: "t4", title: "API של החניונים", question: "האם קיים API או חוזה לרשימת החניונים? איפה?", why: "כדי לדעת אם אפשר להתחבר לשרת או לעבוד מול Mock", category: "api_dependency", mockable: true, blocker: true },
];
const OPTIONS = [
  { id: "d1", title: "שליפת נתונים", question: "איך לשלוף את רשימת החניונים?", options: [
    { id: 1, label: "Hook של React Query כמו במסך הרכבים", description: "", pros: "זהה למסך הקיים", cons: "תלוי בכתובת ה-API", evidence: ["src/screens/VehicleListScreen.tsx"], dependency: "@tanstack/react-query", new_dependency: false, recommended: true },
    { id: 2, label: "קריאת axios ישירה דרך http", description: "", pros: "פשוט", cons: "בלי cache", evidence: ["src/services/http.ts"], dependency: "axios", new_dependency: false, recommended: false },
  ] },
  { id: "d2", title: "תיבת חיפוש", question: "איזה רכיב חיפוש להשתמש?", options: [
    { id: 1, label: "שימוש חוזר ב-SearchInput", description: "", pros: "עיצוב עקבי", cons: "אין", evidence: ["src/components/ui/SearchInput.tsx"], dependency: null, new_dependency: false, recommended: true },
    { id: 2, label: "רכיב חדש", description: "", pros: "גמישות", cons: "כפילות", evidence: [], dependency: null, new_dependency: true, recommended: false },
  ] },
];

const IDK = /לא יודע|לא יודעת|לא מצאתי|אין לי מושג|idk|don't know|^\s*\?+\s*$/i;
const SUSPECT = /חשד|נראה לי|כנראה|אולי|ייתכן|maybe|i think/i;
const ABSENT = /^\s*(?:\S+[,:]?\s+){0,2}?(אין|לא קיים)/;
const ENDPOINT = /https?:\/\/\S+|\b(?:GET|POST|PUT|PATCH|DELETE)\s+\/\S+|(?<![\w/.:-])\/[\w{}:-]+(?:\/[\w{}:.-]+)+|(?<![\w/.:-])api\/[\w{}:-]+/i;
const NO_API = /אין|לא קיים|עדיין לא|בפיתוח|not ready|doesn't exist/i;
const PATH = /[\w@.-]+(?:\/[\w@.-]+)+|[\w.-]+\.(?:tsx?|jsx?|ts)/g;
const exists = (p) => FILES.some((f) => f === p || f.startsWith(p.replace(/\/$/, "") + "/") || f.endsWith("/" + p));
const MENU = "אם מצאתם - כתבו נתיב או שם ספרייה. אם אחרי החיפוש אתם בטוחים שאין - כתבו 'אין' ונוסיף רכיב חדש. אם יש חשד שקיים אבל לא מצאתם - כתבו 'יש חשד' ונציין בפרומפט לחפש לפני שיוצרים. אם לא ברור - כתבו 'לא יודע/ת' ונציע פתרונות לבחירתכם.";
const FACT_NOTE = "זו עובדה שאי אפשר להסיק מהקוד, ואני לא ממציא אותה. הנה איפה לחפש (שירותים, תיעוד API). אם מצאתם - כתבו שיטה ונתיב (למשל GET /api/...) או נתיב לקובץ. אם ה-Backend עדיין לא מוכן - כתבו 'ה-API עדיין לא מוכן'. אחרת תקבלו שאלה מדויקת למנטור.";
const MENTOR_Q = "מהו ה-endpoint המדויק (שיטה + כתובת/נתיב), אילו פרמטרים הוא מקבל, מהו מבנה התשובה, והאם יש Swagger/OpenAPI או שירות קיים שכבר קורא אליו? אם ה-Backend עדיין לא מוכן: האם מותר להתקדם מול Mock, ומי מאשר את החוזה?";
const CANDIDATES = ["src/components/ui/SearchInput.tsx", "src/screens/VehicleListScreen.tsx"];

const USAGE = () => ({ model: "דוגמה · meta-llama/llama-3.3-70b-instruct:free", by_node: [{ node: "guardrails", calls: 1, input_tokens: 700, output_tokens: 30, actual_usd: 0, theoretical_usd: 0.00012 }, { node: "build_checklist", calls: 1, input_tokens: 3100, output_tokens: 600, actual_usd: 0, theoretical_usd: 0.0007 }, { node: "propose_options", calls: 1, input_tokens: 2400, output_tokens: 500, actual_usd: 0, theoretical_usd: 0.0006 }, { node: "compose_prompt", calls: 1, input_tokens: 3200, output_tokens: 970, actual_usd: 0, theoretical_usd: 0.0012 }], total: { calls: 4, input_tokens: 9400, output_tokens: 2100, actual_usd: 0, theoretical_usd: 0.0027, seconds: 9.4 } });

export function createDemoTransport({ delay = 380 } = {}) {
  const runs = new Map();
  const wait = () => (delay ? sleep(delay) : Promise.resolve());
  const nodes = async (names, emit) => { for (const n of names) { await wait(); emit({ type: "node", name: n }); } };
  const prompt = (r, payload) => ({ type: "prompt", run_id: r.id, usage: USAGE(), payload: { error: null, ...payload } });

  const textPrompt = (r, error = null, note = null) => {
    const t = TOPICS[r.i];
    const guidance = r.attempt && !r.mentor ? { why: t.why, files: FILES.slice(0, 3), terms: ["list", "search"], dirs: ["src"], dependencies: ["axios", "@tanstack/react-query"] } : null;
    return prompt(r, { type: "text", kind: r.mentor ? "mentor" : r.attempt ? "guidance" : "topic", id: t.id, n: r.i + 1, total: TOPICS.length, title: t.title, question: r.mentor ? `${t.title}: ${MENTOR_Q}` : t.question, why: t.why,
      category: t.category, blocker: !!t.blocker, note, guidance, error });
  };
  const choicePrompt = (r, error = null) => {
    const d = OPTIONS[r.j];
    return prompt(r, { type: "choice", id: d.id, n: r.j + 1, total: OPTIONS.length, title: d.title, question: d.question, options: d.options, error });
  };
  const done = (r, emit, extra) => emit({ type: "done", usage: USAGE(), state: { in_scope: true, cancelled: false, warnings: [], eval_issues: [], requirements: ["שם החניון", "שעת כניסה ויציאה", "חיפוש אחרי 3 תווים", "עיצוב קיים"], topics: r.topics, decisions: r.decisions, ...extra } });

  const blockedOf = (r) => r.topics.filter((t) => t.status === "mentor_needed").map((t) => ({ id: t.id, title: t.title, question: `${t.title}: ${MENTOR_Q}` }));

  async function afterTopics(r, emit) {
    await nodes(["gate"], emit);
    if (blockedOf(r).length) {
      await nodes(["stop_report"], emit);
      r.stage = "save-session";
      return emit(prompt(r, { type: "save", kind: "session", path: "briefs/session-demo.json" }));
    }
    await nodes(["propose_options"], emit);
    r.stage = "choice"; r.j = 0;
    return emit(choicePrompt(r));
  }

  async function nextTopic(r, emit) {
    r.i += 1; r.attempt = 0;
    while (r.i < TOPICS.length && !["open", "mentor_needed"].includes(r.topics[r.i].status)) r.i += 1;   // resumed session: settled topics are not asked again
    if (r.i < TOPICS.length) { r.mentor = r.topics[r.i].status === "mentor_needed"; return emit(textPrompt(r)); }
    return afterTopics(r, emit);
  }

  async function handle(r, value, emit) {
    const v = String(value).trim();
    if (/^(q|quit|exit|יציאה)$/i.test(v)) return emit({ type: "done", usage: USAGE(), state: { in_scope: true, cancelled: true, final_message: "ההרצה בוטלה - לא הופק פרומפט." } });
    if (r.stage === "topics") {
      const t = TOPICS[r.i], rec = r.topics[r.i];
      if (!v) return emit(textPrompt(r, "התשובה ריקה. כתבו תשובה, 'לא יודע/ת', או Q ליציאה."));
      if (r.mentor) {                                           // resumed session: the mentor's answer is a statement, not repository evidence
        if (/^(אין|עדיין|לא קיבלתי|none)/.test(v) || IDK.test(v)) { rec.notes = [...rec.notes, "עדיין אין תשובה מהמנטור"]; return nextTopic(r, emit); }
        Object.assign(rec, { status: "mentor_answered", answer: v, mentor: { answer: v, not_in_project: [] } });
        return nextTopic(r, emit);
      }
      const real = (v.match(PATH) || []).filter(exists);
      const finish = (status, extra = {}) => { Object.assign(rec, { status, ...extra }); return nextTopic(r, emit); };
      if (real.length) return finish("verified", { answer: v, paths: real });
      const kind = SUSPECT.test(v) && v.split(/\s+/).length <= 12 ? "suspect" : v.split(/\s+/).length <= 8 && IDK.test(v) ? "idk"
        : t.category === "api_dependency" && NO_API.test(v) ? "no_api" : v.split(/\s+/).length <= 10 && ABSENT.test(v) ? "absent" : "answer";
      if (kind === "no_api") return finish("mock_ok", { answer: v });
      if (t.blocker) {                                          // the endpoint is never invented: a URL/path, or one round of guidance, then the mentor
        if (kind === "answer" && ENDPOINT.test(v)) return finish("reported", { answer: v });
        if (r.attempt === 1) return finish("mentor_needed", { answer: kind === "answer" ? v : "", mentor_question: `${t.title}: ${MENTOR_Q}` });
        r.attempt = 1;
        return emit(textPrompt(r, null, FACT_NOTE));
      }
      if (kind === "answer") return finish("reported", { answer: v });
      if (kind === "absent" && (r.attempt === 1 || t.category === "api_dependency")) return finish("absent", { answer: v, candidates: CANDIDATES });
      if (r.attempt === 1) return finish(kind === "suspect" ? "suspected" : "unknown", { answer: kind === "idk" ? "" : v, candidates: CANDIDATES });
      r.attempt = 1;
      const note = kind === "absent" ? "אתם אומרים שאין, אבל בחיפוש בפרויקט מצאתי קבצים שאולי קשורים (למטה). בטוחים שאין? " + MENU
        : kind === "suspect" ? "יש חשד שקיים - הנה איפה לחפש. " + MENU : "אין בעיה - הנה איפה לחפש. " + MENU;
      return emit(textPrompt(r, null, note));
    }
    if (r.stage === "choice") {
      const d = OPTIONS[r.j];
      const n = /^\d+$/.test(v) ? Number(v) : null;
      if (!v) return emit(choicePrompt(r, `תשובה ריקה. בחרו מספר 1-${d.options.length}, כתבו אפשרות משלכם, או 'המלצה'.`));
      if (n !== null && (n < 1 || n > d.options.length)) return emit(choicePrompt(r, `המספר ${n} מחוץ לטווח 1-${d.options.length}.`));
      if (IDK.test(v) && v.split(/\s+/).length <= 4) return emit(choicePrompt(r, `בחירה היא החלטה שלכם. בחרו מספר 1-${d.options.length}, כתבו אפשרות משלכם, או 'המלצה'.`));
      const o = n !== null ? d.options[n - 1] : /המלצה/.test(v) ? d.options.find((x) => x.recommended) : { label: v, custom: true, evidence: [], recommended: false };
      r.decisions.push({ id: d.id, title: d.title, question: d.question, options: d.options, status: "chosen", chosen: { ...o, custom: !!o.custom } });
      r.j += 1;
      if (r.j < OPTIONS.length) return emit(choicePrompt(r));
      await nodes(["compose_prompt", "eval_prompt", "deliver"], emit);
      r.stage = "save-prompt";
      return emit(prompt(r, { type: "save", kind: "prompt", path: "briefs/prompt-demo.md" }));
    }
    if (r.stage === "save-session" || r.stage === "save-prompt") {
      const kind = r.stage === "save-session" ? "session" : "prompt", path = `briefs/${kind}-demo.${kind === "session" ? "json" : "md"}`;
      if (!/^(y|yes|n|no)$/i.test(v)) return emit(prompt(r, { type: "save", kind, path, error: `Invalid answer "${v}". Type Y or N.` }));
      const saved = /^y/i.test(v);
      if (kind === "session") {
        return done(r, emit, { outcome: "needs_mentor", blocked: blockedOf(r), saved_path: saved ? path : "",
          final_message: "לא הופק פרומפט: חסר מידע שהמשימה תלויה בו, ואני לא ממציא אותו. יש לברר מול המנטור/ית לפני שמתחילים לממש.",
          session_out: { version: 2, task: r.task, project: "evals/fixtures/parking_app", requirements: [], topics: r.topics } });
      }
      const open = r.topics.filter((t) => ["suspected", "unknown", "open"].includes(t.status));
      const E = r.topics.map((t) => t.status === "mock_ok" ? `- [${t.id}] ${t.title}: the backend/API does not exist yet. Work proceeds against a MOCK (ASSUMPTION).`
        : t.status === "suspected" ? `- [${t.id}] ${t.title}: SUSPECTED EXISTING. Search the project before creating anything new. Look first at: ${CANDIDATES.join(", ")}.`
        : t.status === "absent" ? `- [${t.id}] ${t.title}: the developer confirmed it does not exist, so a new one may be created (not verified).`
                : t.status === "reported" && t.blocker ? `- [${t.id}] ${t.title}: DEVELOPER-REPORTED endpoint - confirm it with the backend before integrating.`
        : t.status === "mentor_answered" ? `- [${t.id}] ${t.title}: MENTOR-CONFIRMED (a statement, not repository evidence) - re-check it in the code.`
        : t.status === "unknown" ? `- [${t.id}] ${t.title}: UNKNOWN to the developer - decided by the agent from the project (section C).` : null).filter(Boolean).join("\n") || "- none";
      return done(r, emit, { outcome: "prompt", brief_accepted: true, saved_path: saved ? "briefs/prompt-demo.md" : "",
        final_message: "הפרומפט המקצועי מוכן. הממצאים וההחלטות מסומנים לפי מקורם. לפני שמתחילים לכתוב קוד: קראו את סעיף H בפרומפט." + (open.length ? ` נשארו נושאים פתוחים (${open.map((t) => t.title).join(", ")}): הם מופיעים בפרומפט (סעיף E) כשאלות לבירור מול המנטור/ית.` : ""),
        final_prompt: `## A. Task, requirements and acceptance criteria\n\nמסך רשימת חניונים: שם, שעת כניסה ויציאה, חיפוש אחרי 3 תווים, בעיצוב הקיים.\n\n## B. Architecture findings\n\n${r.topics.map((t) => `- [${t.id}] ${t.title} - ${t.status}`).join("\n")}\n\n## C. Developer decisions\n\n${r.decisions.map((d) => `- [${d.id}] ${d.title}: ${d.chosen.label}`).join("\n")}\n\n## E. Provisional work and open items\n\n${E}\n\n## H. Before you start - what to pay attention to\n\n- Follow this project's own conventions; reuse existing code first (src/components/ui, src/hooks).\n- Do not write code just because it looks right; never invent an endpoint, a payload field or a permission.\n\n## G. Implementation prompt\n\nImplement the facilities list screen next to \`src/screens/VehicleListScreen.tsx\`, reusing \`src/components/ui/SearchInput.tsx\`. The API is a MOCK (ASSUMPTION) until the contract is agreed.` });
    }
  }

  return {
    demo: true,
    config: async () => ({ model: "מצב הדגמה", mentor: "המנטור/ית", langsmith: false, has_key: true, project: "evals/fixtures/parking_app" }),
    saveKey: async () => {},
    async start(body, onEvent) {
      const r = { id: `demo-${Math.random().toString(36).slice(2, 8)}`, task: body.task || DEMO_TASK, i: 0, j: 0, attempt: 0, stage: "topics", decisions: [], mentor: false,
        topics: body.session?.topics || TOPICS.map((t) => ({ ...t, status: "open", answer: "", paths: [], deps: [], notes: [], candidates: [], mentor: null, mentor_question: "", search_terms: [] })) };
      runs.set(r.id, r);
      await nodes(["guardrails", "context_retrieval", ...(body.session ? [] : ["build_checklist"]), "ask_topic"], onEvent);
      r.i = -1;
      return nextTopic(r, onEvent);
    },
    async resume(runId, value, onEvent) {
      const r = runs.get(runId);
      if (!r) return onEvent({ type: "error", message: "Unknown or finished run - start a new task." });
      await handle(r, value, onEvent);
    },
  };
}
