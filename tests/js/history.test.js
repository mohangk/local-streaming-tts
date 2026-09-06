import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHistory } from "../../src/tts_app/static/history.js";

let history, historyList, historySearch, playerStatus, state, openGeneration, resetPlaybackState;
const row = (overrides = {}) => ({
  id: 7, title: "An article", text_preview: "A preview", url: "https://example.org/article",
  status: "completed", voice: "Jennifer", provider: "fake", settings: { speed: 1.25 },
  progress_percent: 25, ...overrides,
});

beforeEach(() => {
  document.body.innerHTML = '<input id="search"><div id="list"></div><p id="status"></p>';
  historyList = document.querySelector("#list");
  historySearch = document.querySelector("#search");
  playerStatus = document.querySelector("#status");
  state = { generations: [row()], currentGenerationId: 7 };
  openGeneration = vi.fn();
  resetPlaybackState = vi.fn();
  history = createHistory({ historyList, historySearch, playerStatus, state, openGeneration, resetPlaybackState });
  history.registerEvents();
  vi.stubGlobal("confirm", vi.fn(() => true));
});

describe("History behavior", () => {
  it("renders metadata and filters by title, URL, voice and speed", () => {
    history.renderHistory();
    expect(historyList.textContent).toContain("1.25x");
    for (const query of ["ARTICLE", "example.org", "Jennifer", "1.25"]) {
      historySearch.value = query;
      historySearch.dispatchEvent(new window.Event("input"));
      expect(historyList.querySelectorAll("article")).toHaveLength(1);
    }
    historySearch.value = "missing";
    historySearch.dispatchEvent(new window.Event("input"));
    expect(historyList.textContent).toContain("No generations found");
  });

  it("opens from the card and Open button, leaving Details interactive", () => {
    history.renderHistory();
    historyList.querySelector("summary").click();
    expect(openGeneration).not.toHaveBeenCalled();
    historyList.querySelector(".history-item-title").click();
    expect(openGeneration).toHaveBeenCalledWith(7, { subscribe: false, autoplay: true });
    const button = historyList.querySelector('[data-action="open"]');
    button.click();
    expect(openGeneration).toHaveBeenLastCalledWith(7, { subscribe: false, autoplay: true, button });
  });

  it("confirms deletion, resets current playback and refreshes History", async () => {
    const fetch = vi.fn().mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetch);
    await history.deleteGeneration(7);
    expect(window.confirm).toHaveBeenCalled();
    expect(fetch).toHaveBeenNthCalledWith(1, "/api/generations/7", { method: "DELETE" });
    expect(resetPlaybackState).toHaveBeenCalledWith("Deleted generation");
    expect(historyList.textContent).toContain("No generations found");
  });

  it("does nothing when deletion is cancelled", async () => {
    vi.stubGlobal("fetch", vi.fn());
    window.confirm.mockReturnValue(false);
    await history.deleteGeneration(7);
    expect(fetch).not.toHaveBeenCalled();
    expect(resetPlaybackState).not.toHaveBeenCalled();
  });

  it("keeps entries and playback when deletion fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    history.renderHistory();
    const button = historyList.querySelector('[data-action="delete"]');
    await history.deleteGeneration(7, button);
    expect(button.disabled).toBe(false);
    expect(historyList.querySelector("article")).not.toBeNull();
    expect(resetPlaybackState).not.toHaveBeenCalled();
    expect(playerStatus.textContent).toContain("Unable to delete");
  });

  it("reports load failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await history.loadHistory();
    expect(historyList.textContent).toContain("Unable to load history");
  });
});
