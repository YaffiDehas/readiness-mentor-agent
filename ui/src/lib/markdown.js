// Minimal, SAFE markdown: parsed into plain data and rendered as React elements (never innerHTML), because the brief contains
// model output and text copied from project files.
const LABEL = /\b(VERIFIED|INFERRED|ASSUMPTION|UNKNOWN|CONFLICT)\b/g;

export function parseInline(text) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push(...labels(text.slice(last, m.index)));
    const tok = m[0];
    out.push(tok.startsWith("**") ? { t: "b", v: tok.slice(2, -2) } : { t: "code", v: tok.slice(1, -1) });
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(...labels(text.slice(last)));
  return out;
}

function labels(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(LABEL)) {
    if (m.index > last) out.push({ t: "text", v: text.slice(last, m.index) });
    out.push({ t: "label", v: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}

export function parseMarkdown(src) {
  const blocks = [];
  const lines = String(src || "").replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  const para = [];
  const flush = () => {
    if (para.length) blocks.push({ type: "p", inline: parseInline(para.join(" ")) });
    para.length = 0;
  };
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      flush();
      const code = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
      i++;
      blocks.push({ type: "code", text: code.join("\n") });
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      flush();
      blocks.push({ type: "h", level: h[1].length, inline: parseInline(h[2]) });
      i++;
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      flush();
      const items = [];
      const ordered = /^\s*\d+\./.test(line);
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        const m = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(lines[i]);
        items.push({ depth: Math.min(2, Math.floor(m[1].length / 2)), inline: parseInline(m[3]) });
        i++;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }
    if (/^\s*\|/.test(line)) {
      flush();
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      blocks.push({ type: "code", text: rows.join("\n") });
      continue;
    }
    if (!line.trim()) {
      flush();
      i++;
      continue;
    }
    para.push(line.trim());
    i++;
  }
  flush();
  return blocks;
}

// The agent builds the brief from sections "## A. ..." ... "## R. ..." (agent/nodes.py): split them for the collapsible view.
export function splitSections(brief) {
  const parts = String(brief || "").split(/^## ([A-Z])\.\s*(.*)$/m);
  const sections = [];
  for (let i = 1; i + 2 <= parts.length; i += 3) sections.push({ key: parts[i], title: parts[i + 1].trim(), body: parts[i + 2].trim() });
  return sections;
}
