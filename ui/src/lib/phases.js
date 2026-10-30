// Graph node -> user-facing phase and a friendly "what is happening now" sentence (Hebrew).
export const PHASES = [
  { id: "intake", label: "קליטת משימה" },
  { id: "context", label: "סריקת הפרויקט" },
  { id: "checklist", label: "רשימת בדיקות למשימה" },
  { id: "architecture", label: "שאלות ארכיטקטורה" },
  { id: "options", label: "בחירת פתרון" },
  { id: "prompt", label: "הכנת הפרומפט" },
  { id: "done", label: "סיום" },
];

const NODE = {
  guardrails: ["intake", "בודק שהמשימה בתחום"],
  context_retrieval: ["context", "קורא את קבצי הפרויקט"],
  build_checklist: ["checklist", "בוחר מה צריך לבדוק במשימה הזו"],
  ask_topic: ["architecture", "מאמת את התשובה מול הפרויקט"],
  gate: ["architecture", "בודק אם חסר מידע קריטי"],
  stop_report: ["done", "מכין רשימת שאלות למנטור"],
  propose_options: ["options", "מציע אפשרויות שמבוססות על הפרויקט"],
  choose_option: ["options", "מעדכן את הבחירה"],
  compose_prompt: ["prompt", "כותב את הפרומפט"],
  eval_prompt: ["prompt", "בודק את הפרומפט מול הממצאים"],
  deliver: ["done", "מסכם"],
};

export const phaseOf = (node) => (NODE[node] ? NODE[node][0] : "intake");
export const nodeLabel = (node) => (NODE[node] ? NODE[node][1] : node);
export const knownNode = (node) => node in NODE;
