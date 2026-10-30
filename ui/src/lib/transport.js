import { readNdjson } from "./stream.js";

const HEADERS = { "Content-Type": "application/json", "X-Readiness-UI": "1" }; // required by the local bridge (anti drive-by requests)

async function post(path, body, onEvent, signal) {
  let res;
  try {
    res = await fetch(path, { method: "POST", headers: HEADERS, body: JSON.stringify(body), signal });
  } catch (e) {
    if (e.name === "AbortError") return;
    onEvent({ type: "error", message: "לא ניתן להתחבר לשרת המקומי. הריצו: python -m agent.server" });
    return;
  }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    onEvent({ type: "error", message: j.error || `HTTP ${res.status}` });
    return;
  }
  try {
    await readNdjson(res, onEvent);
  } catch (e) {
    if (e.name !== "AbortError") onEvent({ type: "error", message: `החיבור נותק באמצע הריצה: ${e.message}` });
  }
}

export const realTransport = {
  demo: false,
  async config() {
    const r = await fetch("/api/config");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
  async saveKey(key) {
    const r = await fetch("/api/key", { method: "POST", headers: HEADERS, body: JSON.stringify({ key }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  },
  start: (body, onEvent, signal) => post("/api/run", body, onEvent, signal),
  resume: (runId, value, onEvent, signal) => post("/api/resume", { run_id: runId, value }, onEvent, signal),
};
