// NDJSON over fetch: one JSON event per line, delivered as soon as a full line arrives (chunk boundaries can fall anywhere).
export async function readNdjson(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    buf += decoder.decode(value || new Uint8Array(), { stream: !done });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onEvent(JSON.parse(line));
    }
    if (done) break;
  }
  if (buf.trim()) onEvent(JSON.parse(buf));
}
