export default function Header({ config, demo, theme, onTheme, onHelp }) {
  return (
    <header className="header">
      <div className="logo" aria-hidden="true">🧭</div>
      <div>
        <h1 className="title">Readiness Mentor</h1>
        <p className="subtitle">בודקים שהמשימה ברורה לפני שכותבים קוד</p>
      </div>
      <div className="spacer" />
      <div className="chips">
        {demo && <span className="chip demo">מצב הדגמה · נתונים לדוגמה</span>}
        {config && !demo && <span className="chip mono" title="מודל">{config.model}</span>}
        {config && !demo && <span className={`chip ${config.langsmith ? "ok" : ""}`}>LangSmith {config.langsmith ? "פעיל" : "כבוי"}</span>}
      </div>
      <button className="iconbtn" onClick={onTheme} aria-label="החלפת ערכת נושא" title="ערכת נושא">{theme === "dark" ? "☀️" : "🌙"}</button>
      <button className="iconbtn" onClick={onHelp} aria-label="עזרה" title="עזרה">?</button>
    </header>
  );
}
