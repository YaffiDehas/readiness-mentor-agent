// The whole UI is a function of this state. Pure, so the protocol handling is unit-tested without a browser.
export const initialState = {
  status: "idle", // idle | running | prompt | done | error
  task: "", project: "", runId: null, nodes: [], current: null, prompt: null,
  result: null, error: null, usage: null, history: [], config: null,
};

export function reducer(state, action) {
  switch (action.type) {
    case "config":
      return { ...state, config: action.config, project: state.project || action.config.project || "" };
    case "start":
      return { ...initialState, config: state.config, status: "running", task: action.task, project: action.project };
    case "answered": // the developer answered a prompt; waiting for the next event
      return { ...state, status: "running", prompt: null, history: action.entry ? [...state.history, action.entry] : state.history };
    case "event": {
      const ev = action.event;
      if (ev.type === "node") return { ...state, status: "running", current: ev.name, nodes: [...state.nodes, { name: ev.name, at: action.at }] };
      if (ev.type === "prompt") return { ...state, status: "prompt", runId: ev.run_id, prompt: ev.payload, usage: ev.usage, current: "waiting" };
      if (ev.type === "done") return { ...state, status: "done", result: ev.state, usage: ev.usage, prompt: null, current: "done" };
      if (ev.type === "error") return { ...state, status: "error", error: ev.message, prompt: null };
      return state;
    }
    case "reset":
      return { ...initialState, config: state.config, project: state.project };
    default:
      return state;
  }
}

// What the developer typed -> a readable transcript entry (null for prompts that are not part of the dialogue, e.g. save).
export const answerText = (prompt, value) => {
  if (prompt.type === "choice") {
    const n = Number(value);
    return prompt.options.find((o) => o.id === n)?.label ?? String(value);
  }
  return String(value);
};

export const historyEntry = (prompt, value) => {
  if (prompt.type === "text") return { question: prompt.kind === "mentor" ? `תשובת המנטור: ${prompt.question}` : prompt.question, answer: answerText(prompt, value) };
  if (prompt.type === "choice") return { question: prompt.question, answer: answerText(prompt, value) };
  return null;
};
