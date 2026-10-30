import { useRef, useState } from "react";
import { DEMO_TASK } from "../lib/demo.js";

const OK_EXT = /\.(txt|md|json|ya?ml|csv|sql|py|js|jsx|ts|tsx|graphql|gql|proto|java|kt|swift|cs|go|toml)$/i;
const MAX_BYTES = 200_000;
const EXAMPLES = ["מסך רשימת חניונים עם שם, שעת כניסה ויציאה וחיפוש אחרי 3 תווים", "להוסיף טאב התראות למסך פרטי החיישן", "ליצור טבלאות לקוחות והזמנות בבסיס הנתונים", "טבלה גנרית עם מיון, חיפוש ועימוד"];

export default function TaskForm({ project, demo, samples = [], onStart }) {
  const [task, setTask] = useState(demo ? DEMO_TASK : "");
  const [path, setPath] = useState(project || "");
  const [files, setFiles] = useState([]);
  const [over, setOver] = useState(false);
  const [note, setNote] = useState("");
  const [session, setSession] = useState(null);
  const sessionInput = useRef(null);
  const input = useRef(null);

  const loadSession = async (file) => {
    try {
      const s = JSON.parse(await file.text());
      if (!s || !Array.isArray(s.topics) || typeof s.task !== "string") throw new Error("bad");
      setSession(s);
      setTask(s.task);
      if (s.project) setPath(s.project);
      setNote("");
    } catch {
      setNote(`${file.name}: זה לא קובץ המשך תקין`);
    }
  };

  const addFiles = async (list) => {
    const notes = [], added = [];
    for (const f of Array.from(list)) {
      if (!OK_EXT.test(f.name)) { notes.push(`${f.name}: סוג קובץ לא נתמך (טקסט וקוד בלבד)`); continue; }
      if (f.size > MAX_BYTES) { notes.push(`${f.name}: גדול מדי (עד 200KB)`); continue; }
      if (files.length + added.length >= 5) { notes.push("אפשר לצרף עד 5 קבצים"); break; }
      added.push({ name: f.name, text: await f.text() });
    }
    setFiles((cur) => [...cur, ...added.filter((a) => !cur.some((c) => c.name === a.name))]);
    setNote(notes.join(" · "));
  };

  const submit = () => task.trim() && onStart({ task: task.trim(), project: path.trim(), attachments: files, ...(session ? { session } : {}) });

  return (
    <section className="card">
      <h2>על איזו משימה עובדים?</h2>
      <p className="lead">תארו במשפט או שניים מה צריך לבנות. הסוכן יבדוק שהכול ברור לפני שמתחילים.</p>

      <label className="field" htmlFor="task">תיאור המשימה</label>
      <textarea id="task" className="textarea" dir="auto" value={task} onChange={(e) => setTask(e.target.value)} placeholder="לדוגמה: מסך רשימת חניונים עם חיפוש"
        onKeyDown={(e) => (e.ctrlKey || e.metaKey) && e.key === "Enter" && submit()} />
      <div className="examples" aria-label="דוגמאות">
        {EXAMPLES.map((ex) => <button key={ex} type="button" className="example" onClick={() => setTask(ex)}>{ex}</button>)}
      </div>

      <label className="field" htmlFor="project">תיקיית הפרויקט <span className="empty">(אפשר להשאיר ריק: אז הסוכן לא סורק קבצים וכל מה שיכתוב יסומן כדברי הג'וניור)</span></label>
      <input id="project" className="input mono" dir="ltr" value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\projects\my-app" spellCheck={false} />

      {samples.length > 0 && (
        <div className="examples" aria-label="פרויקטים לדוגמה">
          <span className="empty">פרויקט לדוגמה לניסוי:</span>
          {samples.map((x) => <button key={x.path} type="button" className="example mono" dir="ltr" onClick={() => setPath(x.path)}>{x.name}</button>)}
        </div>
      )}

      <div className={`dropzone ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files); }}>
        גררו לכאן קובץ אפיון או תיאור משימה, או{" "}
        <button type="button" className="example" onClick={() => input.current?.click()}>בחרו קובץ</button>
        <input ref={input} type="file" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button type="button" className="example" onClick={() => sessionInput.current?.click()}>המשך מקובץ (אחרי שהמנטור ענה)</button>
        <input ref={sessionInput} type="file" accept=".json,application/json" hidden onChange={(e) => { e.target.files[0] && loadSession(e.target.files[0]); e.target.value = ""; }} />
        {session && <span className="chip info">נטען קובץ המשך · יישאלו רק תשובות המנטור</span>}
      </div>
      {note && <div className="banner warn" role="alert">{note}</div>}
      {files.length > 0 && (
        <div className="chips" style={{ marginTop: 10 }}>
          {files.map((f) => (
            <span className="filechip" key={f.name}>📎 <span dir="auto">{f.name}</span>
              <button type="button" aria-label={`הסרת ${f.name}`} onClick={() => setFiles((cur) => cur.filter((c) => c.name !== f.name))}>×</button>
            </span>
          ))}
        </div>
      )}

      <div className="row end" style={{ marginTop: 20 }}>
        <span className="empty"><span className="kbd">Ctrl</span> + <span className="kbd">Enter</span></span>
        <button className="btn primary" disabled={!task.trim()} onClick={submit}>התחלת בדיקה</button>
      </div>
    </section>
  );
}
