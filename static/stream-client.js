/**
 * Consume NDJSON streaming API responses (progress + result).
 */

export async function consumeNdjsonStream(response, onEvent) {
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${response.status})`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Streaming not supported");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const ev = JSON.parse(trimmed);
      if (onEvent) onEvent(ev);
      if (ev.type === "result") result = ev.data;
      if (ev.type === "error") throw new Error(ev.detail || "Pipeline error");
    }
  }

  if (buffer.trim()) {
    const ev = JSON.parse(buffer.trim());
    if (onEvent) onEvent(ev);
    if (ev.type === "result") result = ev.data;
    if (ev.type === "error") throw new Error(ev.detail || "Pipeline error");
  }

  return result;
}
