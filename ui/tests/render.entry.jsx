import { renderToString } from "react-dom/server";
import App, { Finished } from "../src/App.jsx";
import Header from "../src/components/Header.jsx";
import KeyCard from "../src/components/KeyCard.jsx";
import Help from "../src/components/Help.jsx";
import PromptCard from "../src/components/PromptCard.jsx";
import TaskForm from "../src/components/TaskForm.jsx";
import Timeline from "../src/components/Timeline.jsx";
import { createDemoTransport } from "../src/lib/demo.js";

const r = (el) => renderToString(el);

// Walk the demo run once and keep every distinct prompt payload plus the final state, so the cards are rendered with realistic data.
export async function collect() {
  const t = createDemoTransport({ delay: 0 });
  const prompts = [];
  let runId, done = null, usage = null;
  const emit = (e) => { if (e.type === "prompt") { runId = e.run_id; prompts.push(e.payload); usage = e.usage; } if (e.type === "done") { done = e; } };
  await t.start({}, emit);
  for (const v of ["לא יודע", "src/screens", "src/screens/VehicleListScreen.tsx", "יש חשד", "יש חשד", "אין עדיין API", "1", "המלצה", "n"]) { if (!done) await t.resume(runId, v, emit); }
  return { prompts, done, usage };
}

export const view = {
  app: () => r(<App />),
  header: (props) => r(<Header {...props} />),
  help: () => r(<Help onClose={() => {}} />),
  form: (props) => r(<TaskForm project="C:\\proj" demo={false} onStart={() => {}} {...props} />),
  prompt: (p) => r(<PromptCard prompt={p} onSubmit={() => {}} />),
  timeline: (props) => r(<Timeline {...props} />),
  finished: (result, extra = {}) => r(<Finished result={result} onReset={() => {}} {...extra} />),
  keycard: () => r(<KeyCard onSave={async () => {}} />),
};
