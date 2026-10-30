import { useEffect } from "react";
export default function Help({ onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="help-title">איך זה עובד</h2>
        <ol className="steps">
          <li>מתארים משימה (אפשר לצרף קובץ אפיון) ובוחרים את תיקיית הפרויקט.</li>
          <li>הסוכן קורא את הפרויקט בעצמו ושואל כמה שאלות ארכיטקטורה: איפה נמצאים מסכים דומים, רכיבים, שכבת ה-API, ספריות.</li>
          <li>עונים במילים שלכם, עם נתיבים אמיתיים. הסוכן רק מסמן מה נמצא בפרויקט ומה דווח על ידכם. הוא לא מסיק מסקנות בעצמו ולא פוסל תשובות.</li>
          <li>לא יודעים? הסוכן מכוון לאן לחפש. אחרי החיפוש: נתיב שמצאתם, "אין" (ייווצר רכיב חדש), "יש חשד" (הפרומפט יורה לחפש לפני יצירה), או "לא יודע" (תקבלו הצעות ותחליטו).</li>
          <li>שאלות ארכיטקטורה שלא ידעתם (איפה למקם, איזה רכיב, איך שומרים נתונים): <b>הסוכן מחליט לבד</b> לפי מה שקיים בפרויקט, ומציין זאת בפרומפט.</li>
          <li>עובדה שאי אפשר להסיק מהקוד, כמו כתובת ה-REST או הרשאות: הסוכן <b>לא ממציא</b>. תקבלו שאלה מדויקת למנטור וקובץ להמשך, בלי פרומפט. אם ה-Backend עדיין לא מוכן אפשר להמשיך מול Mock.</li>
          <li>בפרומפט יש סעיף "לפני שמתחילים": סגנון הכתיבה בפרויקט, קוד קיים לשימוש חוזר, רכיבים שיידרשו בעתיד, איכות קוד, ומה לבדוק לפני שכותבים.</li>
        </ol>
        <h3>מקורות המידע בפרומפט</h3>
        <ul className="list">
          <li><span className="chip ok">אומת בפרויקט</span> <span className="empty">הנתיב או הספרייה קיימים וקשורים לנושא</span></li>
          <li><span className="chip warn">דיווח שלך · לא אומת</span> <span className="empty">תיאור במילים, בלי נתיב שאפשר לבדוק</span></li>
          <li><span className="chip info">אישור מנטור · לא אומת בקוד</span> <span className="empty">נרשם כהצהרה, לא כראיה</span></li>
          <li><span className="chip info">אין כזה · ייווצר חדש</span> <span className="empty">אתם מאשרים שאין. רכיבים אפשריים שנמצאו בחיפוש מצוינים בפרומפט</span></li>
          <li><span className="chip warn">חשד שקיים · לחפש לפני יצירה</span> <span className="empty">הפרומפט מורה לחפש לפני שיוצרים</span></li>
          <li><span className="chip muted">לא ידוע · החלטת המפתח</span> <span className="empty">הסוכן החליט לפי הפרויקט; כדאי לעבור על ההחלטה</span></li>
          <li><span className="chip info">Mock זמני · הנחה</span> <span className="empty">כשה-API עוד לא קיים. הסוכן ממשיך מול Mock מתויג</span></li>
        </ul>
        <h3>קיצורי מקלדת</h3>
        <p className="lead"><span className="kbd">Ctrl</span>+<span className="kbd">Enter</span> שליחה / התחלה · <span className="kbd">1</span> <span className="kbd">2</span> <span className="kbd">3</span> בחירת אפשרות</p>
        <div className="row end" style={{ marginTop: 16 }}>
          <button className="btn primary" onClick={onClose}>הבנתי</button>
        </div>
      </div>
    </div>
  );
}
