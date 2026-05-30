import { describe, expect, it } from "vitest";

describe("playback helpers", () => {
  it("runs in jsdom", () => {
    const marker = document.createElement("div");
    marker.textContent = "Readvox";
    document.body.append(marker);

    expect(document.body.textContent).toContain("Readvox");
  });
});
