import test from "node:test";
import assert from "node:assert/strict";
import { readNdjson } from "../src/lib/stream.js";
import { reducer, initialState, answerText, historyEntry } from "../src/lib/reducer.js";
import { parseMarkdown, parseInline, splitSections } from "../src/lib/markdown.js";
import { buildSummary } from "../src/lib/summary.js";
import { phaseOf, nodeLabel, PHASES } from "../src/lib/phases.js";
import { createDemoTransport } from "../src/lib/demo.js";

const fakeResponse = (bytes, size) => {
  let i = 0;
  return { body: { getReader: () => ({ read: async () => (i >= bytes.length ? { done: true } : { done: false, value: bytes.slice(i, (i += size)) }) }) } };
};

test("NDJSON: events survive any chunk boundary, including inside a multi-byte Hebrew character", async () => {
  const lines = [{ type: "node", name: "guardrails" }, { type: "prompt", payload: { question: "איך מסכים מקבלים נתונים?" } }, { type: "done", state: { x: 1 } }];
  const bytes = new TextEncoder().encode(lines.map((l) => JSON.stringify(l)).join("\n"));   // no trailing newline on purpose
  for (const size of [1, 2, 3, 7, 64, 10_000]) {
    const got = [];
    await readNdjson(fakeResponse(bytes, size), (e) => got.push(e));
    assert.deepEqual(got, lines, `chunk size ${size}`);
  }
});

test("NDJSON: a malformed line is reported, not silently dropped", async () => {
  await assert.rejects(readNdjson(fakeResponse(new TextEncoder().encode('{"type":"node"}\n{oops\n'), 5), () => {}));
});

test("reducer: node -> prompt -> answered -> done, config and project survive reset", () => {
  let s = reducer(initialState, { type: "config", config: { project: "/p", model: "m" } });
  s = reducer(s, { type: "start", task: "t", project: "/p" });
  assert.equal(s.status, "running");
  s = reducer(s, { type: "event", event: { type: "node", name: "guardrails" }, at: 1 });
  s = reducer(s, { type: "event", event: { type: "prompt", run_id: "r1", payload: { type: "text", id: "t1" }, usage: { total: {} } } });
  assert.deepEqual([s.status, s.runId, s.prompt.id], ["prompt", "r1", "t1"]);
  s = reducer(s, { type: "answered", entry: { question: "q", answer: "a" } });
  assert.deepEqual([s.status, s.prompt, s.history.length], ["running", null, 1]);
  s = reducer(s, { type: "event", event: { type: "done", state: { outcome: "prompt" }, usage: null } });
  assert.deepEqual([s.status, s.result.outcome], ["done", "prompt"]);
  s = reducer(s, { type: "reset" });
  assert.deepEqual([s.status, s.config.model, s.project], ["idle", "m", "/p"]);
});

test("reducer: an error event ends the run and clears the prompt; unknown events are ignored", () => {
  let s = reducer(initialState, { type: "event", event: { type: "prompt", run_id: "r", payload: { type: "save" }, usage: null } });
  s = reducer(s, { type: "event", event: { type: "error", message: "boom" } });
  assert.deepEqual([s.status, s.error, s.prompt], ["error", "boom", null]);
  assert.equal(reducer(s, { type: "event", event: { type: "mystery" } }), s);
});

test("transcript entries: free text, chosen option label, mentor answers; save prompts are not part of the dialogue", () => {
  const choice = { type: "choice", question: "איך לשלוף?", options: [{ id: 1, label: "React Query" }, { id: 2, label: "axios" }] };
  assert.equal(answerText(choice, "2"), "axios");
  assert.equal(answerText(choice, "useReducer"), "useReducer");
  assert.deepEqual(historyEntry({ type: "text", kind: "topic", question: "איפה?" }, "src/screens"), { question: "איפה?", answer: "src/screens" });
  assert.equal(historyEntry({ type: "text", kind: "mentor", question: "איפה?" }, "GET /api/x").question, "תשובת המנטור: איפה?");
  assert.deepEqual(historyEntry(choice, "1"), { question: "איך לשלוף?", answer: "React Query" });
  assert.equal(historyEntry({ type: "save" }, "y"), null);
});

test("markdown: structure, labels, and NO html interpretation", () => {
  const b = parseMarkdown("## כותרת\n\n- VERIFIED: **מודגש** ו-`code`\n- שני\n\n```\nraw <b>\n```\n\n<script>alert(1)</script>");
  assert.equal(b[0].type, "h");
  assert.equal(b[1].type, "list");
  assert.deepEqual(b[1].items[0].inline.map((s) => s.t), ["label", "text", "b", "text", "code"]);
  assert.deepEqual(b[2], { type: "code", text: "raw <b>" });
  assert.deepEqual(b[3].inline, [{ t: "text", v: "<script>alert(1)</script>" }]);       // stays inert text; React escapes it on render
  assert.deepEqual(parseInline('<img src=x onerror="a()">').map((s) => s.t), ["text"]);
});

test("markdown: an unterminated fence and empty input do not hang or throw", () => {
  assert.equal(parseMarkdown("```\nnever closed")[0].type, "code");
  assert.deepEqual(parseMarkdown(""), []);
  assert.deepEqual(parseMarkdown(null), []);
});

test("splitSections finds the agent's A-I sections", () => {
  const sec = splitSections("intro\n## A. Task and scope\nbody a\n## E. Developer understanding\nbody e\n## I. Readiness decision\nReadiness status: READY");
  assert.deepEqual(sec.map((s) => s.key), ["A", "E", "I"]);
  assert.equal(sec[2].body, "Readiness status: READY");
});

test("splitSections also finds the R (readiness) and J (risks) sections", () => {
  const sec = splitSections("## R. Readiness decision\nDecision: PROCEED WITH LIMITS\n## A. Task\nx\n## J. Risks, approvals and tests\n- none");
  assert.deepEqual(sec.map((s) => s.key), ["R", "A", "J"]);
});

test("summary: includes outcome, transcript, findings, open questions for the mentor, decisions and cost; survives an empty result", () => {
  const md = buildSummary({ task: "משימה", project: "/p", history: [{ question: "שאלה?", answer: "תשובה" }],
    result: { outcome: "prompt", topics: [{ id: "t1", title: "רכיב חיפוש", question: "האם יש רכיב חיפוש?", status: "suspected" }], blocked: [{ id: "t2", question: "מהו ה-endpoint?" }],
      decisions: [{ title: "שליפה", chosen: { label: "React Query" } }], final_message: "הודעה", final_prompt: "## A. x" },
    usage: { model: "m", total: { calls: 2, input_tokens: 10, output_tokens: 5, actual_usd: 0, theoretical_usd: 0.0001 } } });
  for (const part of ["הופק פרומפט", "שאלה?", "רכיב חיפוש: חשד שקיים", "1. האם יש רכיב חיפוש?", "1. מהו ה-endpoint?", "שליפה: React Query", "$0.00010", "## A. x"]) assert.ok(md.includes(part), part);
  assert.ok(buildSummary({}).includes("סיכום שיחה"));
});

test("phases: every phase is reachable and unknown nodes degrade gracefully", () => {
  assert.equal(phaseOf("ask_topic"), "architecture");
  assert.equal(phaseOf("unknown_node"), "intake");
  assert.equal(nodeLabel("unknown_node"), "unknown_node");
  assert.deepEqual(PHASES.map((p) => p.id).sort(), ["architecture", "checklist", "context", "done", "intake", "options", "prompt"]);
});

// ------------------------------------------------------------------------------ demo transport = same protocol as agent/server.py
const drive = () => {
  const t = createDemoTransport({ delay: 0 });
  const log = [];
  let runId = null, last = null;
  const emit = (e) => { log.push(e); if (e.type === "prompt") { runId = e.run_id; last = e.payload; } if (e.type === "done" || e.type === "error") last = null; };
  return { t, log, emit, start: () => t.start({}, emit), send: (v) => t.resume(runId, v, emit), get last() { return last; }, get done() { return log.at(-1)?.type === "done" ? log.at(-1) : null; } };
};

test("demo: the first prompt is a free-text architecture question without guidance", async () => {
  const d = drive();
  await d.start();
  assert.deepEqual([d.last.type, d.last.kind, d.last.id, d.last.guidance], ["text", "topic", "t1", null]);
  assert.ok(d.last.title && d.last.question && d.last.why);
});

test("demo: empty input re-asks the same question with an error", async () => {
  const d = drive();
  await d.start();
  await d.send("  ");
  assert.deepEqual([d.last.id, d.last.kind], ["t1", "topic"]);
  assert.match(d.last.error, /ריקה/);
});

test("demo: 'I don't know' gives guidance with real files, then a real path is verified", async () => {
  const d = drive();
  await d.start();
  await d.send("לא יודע");
  assert.equal(d.last.kind, "guidance");
  assert.ok(d.last.guidance.files.length && d.last.guidance.terms.length);
  await d.send("src/screens");
  assert.equal(d.last.id, "t2");
});

test("demo: a path that does not exist is recorded as developer-reported, not rejected and not asked again", async () => {
  const d = drive();
  await d.start();
  await d.send("src/pages/Nope.tsx");
  assert.equal(d.last.id, "t2");                                  // the dialogue simply continues
});

test("demo: a missing endpoint is never invented - one round of guidance, then NO prompt and a session; resuming asks only the mentor question", async () => {
  const d = drive();
  await d.start();
  for (const v of ["src/screens", "src/screens/VehicleListScreen.tsx", "src/components/ui/SearchInput.tsx", "לא יודע"]) await d.send(v);
  assert.equal(d.last.kind, "guidance");
  assert.match(d.last.note, /לא ממציא/);
  await d.send("לא יודע");
  assert.equal(d.last.kind, "session");
  await d.send("y");
  const st = d.done.state;
  assert.equal(st.outcome, "needs_mentor");
  assert.equal(st.final_prompt, undefined);
  assert.deepEqual(st.blocked.map((b) => b.id), ["t4"]);
  assert.match(st.blocked[0].question, /endpoint/);
  const r = drive();
  await r.t.start({ task: "x", session: st.session_out }, r.emit);
  assert.deepEqual([r.last.id, r.last.kind], ["t4", "mentor"]);          // settled topics are not asked again
  await r.send("GET /api/v2/facilities");
  assert.equal(r.last.type, "choice");
  await r.send("1"); await r.send("1"); await r.send("n");
  assert.equal(r.done.state.topics[3].status, "mentor_answered");
  assert.ok(r.done.state.final_prompt.includes("MENTOR-CONFIRMED"));
});

test("demo: 'none exists' is double-checked once, a suspicion is kept, and the run still ends with a prompt", async () => {
  const d = drive();
  await d.start();
  await d.send("src/screens"); await d.send("src/screens/VehicleListScreen.tsx");
  assert.equal(d.last.id, "t3");
  await d.send("אין לנו רכיב חיפוש");                            // candidates exist -> "are you sure?"
  assert.equal(d.last.kind, "guidance");
  assert.match(d.last.note, /בטוחים שאין/);
  await d.send("יש חשד שקיים");
  assert.equal(d.last.id, "t4");
  await d.send("אין עדיין API");                                  // missing backend API -> labeled mock, no extra confirmation
  assert.equal(d.last.type, "choice");
  await d.send("9"); assert.match(d.last.error, /מחוץ לטווח/);
  await d.send("לא יודע"); assert.match(d.last.error, /החלטה שלכם/);
  await d.send("1");
  await d.send("המלצה");
  assert.equal(d.last.kind, "prompt");
  await d.send("n");
  const st = d.done.state;
  assert.equal(st.outcome, "prompt");
  assert.deepEqual(st.topics.map((t) => t.status), ["verified", "verified", "suspected", "mock_ok"]);
  assert.ok(st.final_prompt.includes("SUSPECTED EXISTING") && st.final_prompt.includes("MOCK") && st.decisions[1].chosen.recommended);
});

test("demo: not knowing twice leaves the topic unknown but never stops the run", async () => {
  const d = drive();
  await d.start();
  for (const v of ["לא יודע", "לא יודע", "src/screens/VehicleListScreen.tsx", "src/components/ui/SearchInput.tsx", "אין עדיין API", "1", "1", "n"]) await d.send(v);
  const st = d.done.state;
  assert.equal(st.outcome, "prompt");
  assert.equal(st.topics[0].status, "unknown");
  assert.match(st.final_message, /נשארו נושאים פתוחים/);
});

test("demo: quit cancels; an unknown run id is an error event", async () => {
  const d = drive();
  await d.start();
  await d.send("Q");
  assert.equal(d.done.state.cancelled, true);
  const events = [];
  await createDemoTransport({ delay: 0 }).resume("nope", "x", (e) => events.push(e));
  assert.equal(events[0].type, "error");
});

test("summary: the per-step cost table is included", () => {
  const md = buildSummary({ task: "t", usage: { model: "m", total: { calls: 1, input_tokens: 10, output_tokens: 5, actual_usd: 0, theoretical_usd: 0.001 },
    by_node: [{ node: "guardrails", calls: 1, input_tokens: 10, output_tokens: 5, actual_usd: 0, theoretical_usd: 0.001 }] } });
  assert.ok(md.includes("| guardrails | 1 | 10/5 | $0.00000 | $0.00100 |") && md.includes("| שלב |"));
});
