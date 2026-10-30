// Presentation metadata. Statuses mirror the agent (agent/arch.py, agent/nodes.py LABEL).
export const TOPIC_STATUS = {
  verified: ["אומת בפרויקט", "ok"],
  reported: ["דיווח שלך · לא אומת", "warn"],
  mock_ok: ["Mock זמני · הנחה", "info"],
  mentor_answered: ["אישור מנטור · לא אומת בקוד", "info"],
  mentor_needed: ["לברר מול המנטור", "bad"],
  absent: ["אין כזה · ייווצר חדש", "info"],
  suspected: ["חשד שקיים · לחפש לפני יצירה", "warn"],
  unknown: ["לא ידוע · החלטת המפתח", "muted"],
  open: ["פתוח", "muted"],
};

export const money = (n) => (n < 0.00001 ? "$0" : `$${n.toFixed(n < 0.01 ? 5 : 4)}`);
export const tokens = (n) => new Intl.NumberFormat("he-IL").format(Math.round(n || 0));
