import { TOPIC_STATUS } from "./format.js";

// "Create conversation summary" (project spec, track B): a markdown file the developer downloads.
export function buildSummary({ task, project, history, result, usage }) {
  const r = result || {};
  const outcome = r.outcome === "prompt" ? "הופק פרומפט" : r.outcome === "needs_mentor" ? "חסר מידע שאי אפשר להסיק - לברר מול המנטור" : r.cancelled ? "בוטל" : "-";
  const L = [`# סיכום שיחה - Readiness Mentor`, "", `**משימה:** ${task || "-"}`, `**פרויקט:** ${project || "-"}`, `**תוצאה:** ${outcome}`, ""];
  if (history?.length) {
    L.push("## שאלות ותשובות", "");
    history.forEach((h, i) => L.push(`${i + 1}. ${h.question}  \n   תשובה: ${h.answer}`));
    L.push("");
  }
  if (r.topics?.length) L.push("## ממצאי ארכיטקטורה", "", ...r.topics.map((t) => `- ${t.title}: ${(TOPIC_STATUS[t.status] || [t.status])[0]}`), "");
  if (r.blocked?.length) L.push("## לברר מול המנטור (חוסם)", "", ...r.blocked.map((b, i) => `${i + 1}. ${b.question}`), "");
  const open = (r.topics || []).filter((t) => ["suspected", "unknown", "open"].includes(t.status));
  if (open.length) L.push("## פתוח - לבירור מול המנטור", "", ...open.map((t, i) => `${i + 1}. ${t.question}`), "");
  if (r.decisions?.length) L.push("## החלטות שנבחרו", "", ...r.decisions.filter((d) => d.chosen).map((d) => `- ${d.title}: ${d.chosen.label}`), "");
  if (r.final_message) L.push("## הודעה", "", r.final_message, "");
  const t = usage?.total;
  if (t) L.push("## שימוש ועלות", "", `- מודל: ${usage.model}`, `- קריאות: ${t.calls}, טוקנים: ${t.input_tokens + t.output_tokens}`, `- עלות בפועל: $${t.actual_usd.toFixed(5)}, עלות תיאורטית: $${t.theoretical_usd.toFixed(5)}`, "");
  if (usage?.by_node?.length) L.push("", "| שלב | קריאות | טוקנים (קלט/פלט) | עלות בפועל | עלות תיאורטית |", "|---|---|---|---|---|",
    ...usage.by_node.map((n) => `| ${n.node} | ${n.calls} | ${n.input_tokens}/${n.output_tokens} | $${n.actual_usd.toFixed(5)} | $${n.theoretical_usd.toFixed(5)} |`), "");
  if (r.final_prompt) L.push("---", "", r.final_prompt);
  return L.join("\n");
}
