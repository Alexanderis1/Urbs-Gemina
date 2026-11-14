import { describe, expect, it } from "vitest";
import { parseAnswerText, parseInline } from "@/lib/answerText";

describe("answer text formatting", () => {
  it("splits bold text and citations out of a line, keeping every character of the figures", () => {
    expect(parseInline("there are **89** constraints [run:75d7c82e7c6a].")).toEqual([
      { type: "text", text: "there are " },
      { type: "bold", text: "89" },
      { type: "text", text: " constraints " },
      { type: "cite", kind: "run", ref: "75d7c82e7c6a" },
      { type: "text", text: "." },
    ]);
  });

  it("recognises source and data citations, and leaves other brackets alone", () => {
    expect(parseInline("see [src:https://example.org/a] and [data:census] and [note]")).toEqual([
      { type: "text", text: "see " },
      { type: "cite", kind: "src", ref: "https://example.org/a" },
      { type: "text", text: " and " },
      { type: "cite", kind: "data", ref: "census" },
      { type: "text", text: " and [note]" },
    ]);
  });

  it("groups lines into paragraphs, headings and bullet lists", () => {
    const blocks = parseAnswerText("Intro line.\n\n**Where the address is**\n- first [run:abc]\n- second\n\n## Summary\nLast.");
    expect(blocks.map((b) => b.type)).toEqual(["p", "heading", "list", "heading", "p"]);
    expect(blocks[2]).toMatchObject({ type: "list", items: [expect.any(Array), expect.any(Array)] });
    expect(blocks[1]).toMatchObject({ type: "heading", text: "Where the address is" });
    expect(blocks[3]).toMatchObject({ type: "heading", text: "Summary" });
  });

  it("keeps unbalanced asterisks as plain text", () => {
    expect(parseInline("5 * 3 ** 2")).toEqual([{ type: "text", text: "5 * 3 ** 2" }]);
  });
});
