// The assistant writes light Markdown (bold, bullets, short headings) with citations like [run:abc123].
// This turns it into blocks for display. It never changes, drops or reorders the words or figures.

export type Inline =
  | { type: "text"; text: string }
  | { type: "bold"; text: string }
  | { type: "cite"; kind: "run" | "src" | "data"; ref: string };

export type Block =
  | { type: "p"; inline: Inline[] }
  | { type: "heading"; text: string }
  | { type: "list"; items: Inline[][] };

const TOKEN = /\*\*([^*\n]+)\*\*|\[(run|src|data):([^\]\s]+)\]/g;

export function parseInline(line: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  const text = (s: string) => {
    if (!s) return;
    const prev = out[out.length - 1];
    if (prev?.type === "text") prev.text += s;
    else out.push({ type: "text", text: s });
  };
  for (const m of line.matchAll(TOKEN)) {
    text(line.slice(last, m.index));
    if (m[1] !== undefined) out.push({ type: "bold", text: m[1] });
    else out.push({ type: "cite", kind: m[2] as "run" | "src" | "data", ref: m[3]! });
    last = m.index + m[0].length;
  }
  text(line.slice(last));
  return out;
}

export function parseAnswerText(raw: string): Block[] {
  const blocks: Block[] = [];
  for (const rawLine of raw.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    if (bullet) {
      const prev = blocks[blocks.length - 1];
      const item = parseInline(bullet[1]!);
      if (prev?.type === "list") prev.items.push(item);
      else blocks.push({ type: "list", items: [item] });
      continue;
    }
    const hashes = /^#{1,4}\s+(.*)$/.exec(line);
    // A line that is only bold text is a section title.
    const boldOnly = /^\*\*([^*]+)\*\*:?$/.exec(line);
    if (hashes || boldOnly) blocks.push({ type: "heading", text: (hashes?.[1] ?? boldOnly![1]!).replace(/\*\*/g, "") });
    else blocks.push({ type: "p", inline: parseInline(line) });
  }
  return blocks;
}
