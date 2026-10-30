import { PHASES, nodeLabel, phaseOf } from "../lib/phases.js";
import { money, tokens } from "../lib/format.js";

export default function Timeline({ status, nodes, usage }) {
  const real = nodes.filter((n) => n.name);
  const last = real.length ? real[real.length - 1].name : null;
  const visited = new Set(real.map((n) => phaseOf(n.name)));
  const active = status === "done" ? null : last ? phaseOf(last) : "intake";
  const t0 = real.length ? real[0].at : 0;
  const total = usage?.total;
  const now = status === "prompt" ? "ממתין לתשובה שלך" : status === "done" ? "הסתיים" : status === "error" ? "נעצר בשגיאה" : last ? nodeLabel(last) : "מתחיל";

  return (
    <section className="card" aria-label="התקדמות">
      <h2>התקדמות</h2>
      <ol className="phases">
        {PHASES.map((p) => {
          const done = status === "done" || (visited.has(p.id) && p.id !== active);
          return (
            <li key={p.id} className={`phase ${done ? "done" : ""} ${p.id === active ? "active" : ""}`} aria-current={p.id === active ? "step" : undefined}>
              <span className="dot" aria-hidden="true">{done ? "✓" : ""}</span>
              {p.label}
            </li>
          );
        })}
      </ol>
      <div className="now" role="status" aria-live="polite">
        {status === "running" ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">{status === "prompt" ? "✋" : status === "done" ? "✅" : "•"}</span>}
        <span>{now}</span>
      </div>
      {real.length > 0 && (
        <ul className="log" aria-label="יומן שלבים">
          {real.slice(-5).map((n, i) => (
            <li key={`${n.name}-${i}`}>
              <span className="mono">{n.name}</span> · +{((n.at - t0) / 1000).toFixed(1)}s
            </li>
          ))}
        </ul>
      )}
      {total && total.calls > 0 && (
        <div className="meter" aria-label="שימוש ועלות">
          <div className="stat"><b>{tokens(total.input_tokens + total.output_tokens)}</b><span>טוקנים · {total.calls} קריאות</span></div>
          <div className="stat"><b>{money(total.actual_usd)}</b><span>עלות בפועל · תיאורטית {money(total.theoretical_usd)}</span></div>
        </div>
      )}
      {usage?.by_node?.length > 0 && (
        <details className="costs">
          <summary>עלות לפי שלב</summary>
          <table aria-label="עלות לפי שלב" dir="ltr">
            <thead><tr><th>node</th><th>calls</th><th>tokens in/out</th><th>actual</th><th>theoretical</th></tr></thead>
            <tbody>
              {usage.by_node.map((r) => (
                <tr key={r.node}><td className="mono">{r.node}</td><td>{r.calls}</td><td>{tokens(r.input_tokens)}/{tokens(r.output_tokens)}</td><td>{money(r.actual_usd)}</td><td>{money(r.theoretical_usd)}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  );
}
