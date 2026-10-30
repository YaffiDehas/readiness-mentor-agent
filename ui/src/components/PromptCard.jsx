import { useEffect, useState } from "react";

const Err = ({ text }) => (text ? <div className="banner err" role="alert">{text}</div> : null);
const Path = ({ children }) => <span className="pathchip">{children}</span>;

function Guidance({ g }) {
  return (
    <div className="guide" role="note">
      <div className="gh">🔎 איפה לחפש <span className="chip warn">הצעות מהפרויקט · לא עובדות מאומתות</span></div>
      {g.why && <p dir="auto"><b>למה זה חשוב:</b> {g.why}</p>}
      {g.files?.length > 0 && <p>קבצים שאולי קשורים: {g.files.map((f) => <Path key={f}>{f}</Path>)}</p>}
      {g.terms?.length > 0 && <p>מילות חיפוש: {g.terms.map((t) => <Path key={t}>{t}</Path>)}</p>}
      {g.dirs?.length > 0 && <p>תיקיות ראשיות: {g.dirs.map((d) => <Path key={d}>{d}</Path>)}</p>}
      {g.dependencies?.length > 0 && <p>ספריות בפרויקט: {g.dependencies.map((d) => <Path key={d}>{d}</Path>)}</p>}
    </div>
  );
}

function Text({ p, onSubmit }) {
  const [text, setText] = useState("");
  const mentor = p.kind === "mentor";
  const send = (v = text.trim()) => v && onSubmit(v);
  return (
    <section className="card" key={`${p.id}-${p.kind}`}>
      <div className="qmeta">
        <span className="chip">{mentor ? "🧑‍🏫 תשובת המנטור" : p.blocker ? "🔌 עובדה שאי אפשר להסיק מהקוד" : "🏗️ ארכיטקטורה"}</span>
        <span className="empty">נושא {p.n} מתוך {p.total}</span>
        <div className="progress" aria-hidden="true"><i style={{ width: `${(p.n / p.total) * 100}%` }} /></div>
      </div>
      <h2 className="question" dir="auto">{p.title}</h2>
      <p className="lead" dir="auto">{p.question}</p>
      {p.why && p.kind === "topic" && <p className="purpose" dir="auto">למה זה חשוב: {p.why}</p>}
      {p.note && <div className="banner warn" role="status" dir="auto">{p.note}</div>}
      {p.guidance && <Guidance g={p.guidance} />}
      <Err text={p.error} />
      <label className="field" htmlFor="answer">{mentor ? "מה המנטור ענה?" : p.blocker ? "התשובה שלך (שיטה + נתיב, למשל GET /api/..., או נתיב לקובץ)" : "התשובה שלך (נתיב קובץ, שם ספרייה, או תיאור במילים שלך)"}</label>
      <textarea id="answer" className="textarea" dir="auto" value={text} onChange={(e) => setText(e.target.value)} autoFocus
        placeholder={mentor ? "לדוגמה: GET /api/v1/facilities" : p.blocker ? "לדוגמה: GET /api/parking/facilities" : "לדוגמה: src/screens/VehicleListScreen.tsx"}
        onKeyDown={(e) => (e.ctrlKey || e.metaKey) && e.key === "Enter" && send()} />
      <div className="row" style={{ marginTop: 14 }}>
        {mentor ? <button className="btn" onClick={() => send("אין")}>עדיין אין תשובה</button>
          : p.blocker ? (
            <>
              {p.guidance && <button className="btn" onClick={() => send("ה-API עדיין לא מוכן")} title="נמשיך מול Mock מתויג כהנחה">ה-API עדיין לא מוכן</button>}
              <button className="btn" onClick={() => send("לא יודע/ת")} title="לא נמציא: תקבלו שאלה מדויקת למנטור">{p.guidance ? "לא מצאתי · שאלה למנטור" : "לא יודע/ת"}</button>
            </>
          ) : p.guidance ? (
            <>
              <button className="btn" onClick={() => send("אין")} title="בדקתי ואין - ייווצר רכיב חדש">אין כזה · ליצור חדש</button>
              <button className="btn" onClick={() => send("יש חשד")} title="נציין בפרומפט לחפש לפני שיוצרים">יש חשד שקיים</button>
              <button className="btn" onClick={() => send("לא יודע/ת")} title="הסוכן יחליט לפי מה שקיים בפרויקט">לא יודע/ת · הסוכן יחליט</button>
            </>
          ) : (
            <>
              <button className="btn" onClick={() => send("אין")}>אין כזה</button>
              <button className="btn" onClick={() => send("לא יודע/ת")}>לא יודע/ת</button>
            </>
          )}
        <span className="spacer" />
        <button className="btn ghost danger" onClick={() => onSubmit("Q")}>יציאה</button>
        <button className="btn primary" disabled={!text.trim()} onClick={() => send()}>שליחה <span className="kbd">Ctrl+Enter</span></button>
      </div>
    </section>
  );
}

function Choice({ p, onSubmit }) {
  const [own, setOwn] = useState("");
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
      const o = p.options.find((x) => String(x.id) === e.key);
      if (o) onSubmit(String(o.id));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [p, onSubmit]);
  return (
    <section className="card" key={p.id}>
      <div className="qmeta">
        <span className="chip">🧭 בחירת פתרון</span>
        <span className="empty">החלטה {p.n} מתוך {p.total}</span>
        <div className="progress" aria-hidden="true"><i style={{ width: `${(p.n / p.total) * 100}%` }} /></div>
      </div>
      <h2 className="question" dir="auto">{p.title}</h2>
      <p className="lead" dir="auto">{p.question}</p>
      <Err text={p.error} />
      <div className="options" role="group" aria-label="אפשרויות">
        {p.options.map((o) => (
          <button key={o.id} className="option" onClick={() => onSubmit(String(o.id))}>
            <span className="key" aria-hidden="true">{o.id}</span>
            <span className="txt">
              <b dir="auto">{o.label}</b>
              {o.recommended && <span className="chip ok" style={{ marginInlineStart: 8 }}>מומלץ</span>}
              {o.new_dependency && <span className="chip bad" style={{ marginInlineStart: 8 }}>ספרייה חדשה · לא קיימת בפרויקט</span>}
              {o.description && <div className="empty" dir="auto">{o.description}</div>}
              <div className="empty" dir="auto">＋ {o.pros} · － {o.cons}</div>
              {(o.evidence?.length > 0 || o.dependency) && (
                <div>מבוסס על: {o.evidence.map((f) => <Path key={f}>{f}</Path>)}{o.dependency && <Path>{o.dependency}</Path>}</div>
              )}
            </span>
          </button>
        ))}
      </div>
      <label className="field" htmlFor="own">או כתבו אפשרות משלכם</label>
      <input id="own" className="input" dir="auto" value={own} onChange={(e) => setOwn(e.target.value)} placeholder="האפשרות שלכם (תסומן כלא מבוססת על הפרויקט)"
        onKeyDown={(e) => e.key === "Enter" && own.trim() && onSubmit(own.trim())} />
      <div className="row" style={{ marginTop: 14 }}>
        <button className="btn" onClick={() => onSubmit("המלצה")}>קבלת ההמלצה</button>
        <span className="spacer" />
        <button className="btn ghost danger" onClick={() => onSubmit("Q")}>יציאה</button>
        <button className="btn primary" disabled={!own.trim()} onClick={() => onSubmit(own.trim())}>אפשרות משלי</button>
      </div>
    </section>
  );
}

function YesNo({ title, lead, error, yes, no, yesValue, noValue, onSubmit }) {
  return (
    <section className="card">
      <h2 dir="auto">{title}</h2>
      {lead && <p className="lead">{lead}</p>}
      <Err text={error} />
      <div className="row end"><button className="btn" onClick={() => onSubmit(noValue)}>{no}</button><button className="btn primary" onClick={() => onSubmit(yesValue)}>{yes}</button></div>
    </section>
  );
}

export default function PromptCard({ prompt, onSubmit }) {
  switch (prompt.type) {
    case "text": return <Text p={prompt} onSubmit={onSubmit} />;
    case "choice": return <Choice p={prompt} onSubmit={onSubmit} />;
    case "save": return prompt.kind === "session"
      ? <YesNo title="לשמור את ההקשר כדי להמשיך אחרי שהמנטור יענה?" lead={<>הקובץ ייכתב אל <Path>{prompt.path}</Path></>} error={prompt.error} yes="שמירה" no="לא לשמור" yesValue="y" noValue="n" onSubmit={onSubmit} />
      : <YesNo title="לשמור את הפרומפט לקובץ?" lead={<>הקובץ ייכתב אל <Path>{prompt.path}</Path></>} error={prompt.error} yes="שמירה" no="לא לשמור" yesValue="y" noValue="n" onSubmit={onSubmit} />;
    default: return <section className="card"><Err text={`סוג בקשה לא מוכר: ${prompt.type}`} /></section>;
  }
}
