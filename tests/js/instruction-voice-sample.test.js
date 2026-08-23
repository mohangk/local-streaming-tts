import { afterEach, describe, expect, it, vi } from "vitest";
import { responseErrorMessage } from "../../src/tts_app/static/api-client.js";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

const sampleOptions = {
  default_language: "en",
  default_model: "qwen3-tts-instruct-flash-realtime",
  default_speed: 1,
  default_voice: "Kai",
  languages: [{ value: "en", label: "English" }],
  models: [{ value: "qwen3-tts-instruct-flash-realtime", label: "Qwen Instruct" }],
  voices: [{ value: "Kai", label: "Kai - soothing man" }],
  voices_by_model: {
    "qwen3-tts-instruct-flash-realtime": [{ value: "Kai", label: "Kai - soothing man" }],
  },
  speeds: [{ value: 1, label: "1x" }],
};

function renderInstructionSamplePage() {
  document.body.innerHTML = `
    <form id="instruction-sample-form">
      <select id="instruction-language"></select>
      <select id="instruction-voice"></select>
      <select id="instruction-speed"></select>
      <select id="instruction-model"></select>
      <textarea id="instruction-prompt">Calm narration.</textarea>
      <textarea id="instruction-text">Sample text.</textarea>
      <button id="instruction-sample" type="submit">Sample</button>
      <button id="clear-instruction-samples" type="button">Clear samples</button>
      <div id="instruction-status"></div>
    </form>
    <audio id="instruction-audio"></audio>
  `;
}

describe("responseErrorMessage", () => {
  it("returns a structured API error message", async () => {
    const response = new globalThis.Response(
      JSON.stringify({ detail: { code: "provider_error", message: "Invalid voice specified" } }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );

    await expect(responseErrorMessage(response, "Unable to load voice sample")).resolves.toBe(
      "Invalid voice specified",
    );
  });

  it("uses the fallback when the error response is not JSON", async () => {
    const response = new globalThis.Response("Bad Gateway", { status: 502 });

    await expect(responseErrorMessage(response, "Unable to load voice sample")).resolves.toBe(
      "Unable to load voice sample",
    );
  });

  it("formats FastAPI validation errors without returning submitted input", async () => {
    const response = new globalThis.Response(
      JSON.stringify({
        detail: [
          {
            type: "less_than_equal",
            loc: ["body", "speed"],
            msg: "Input should be less than or equal to 2",
            input: "private submitted value",
          },
        ],
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    );

    const message = await responseErrorMessage(response, "Unable to load voice sample");

    expect(message).toBe("Speed: Input should be less than or equal to 2");
    expect(message).not.toContain("private submitted value");
  });
});

describe("Generate-page voice sampling", () => {
  it("shows the structured provider error returned by Readvox", async () => {
    document.body.innerHTML = `
      <select id="language-select"><option value="en" selected>English</option></select>
      <select id="voice-select"><option value="Jennifer" selected>Jennifer</option></select>
      <select id="speed-select"><option value="1" selected>1x</option></select>
      <div id="player-status"></div>
      <audio id="audio-player"></audio>
    `;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new globalThis.Response(
          JSON.stringify({ detail: { code: "provider_error", message: "Provider rejected the voice" } }),
          { status: 502, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const { playVoiceSample } = await import(
      "../../src/tts_app/static/voice-controls.js?test=structured-sample-error"
    );

    await playVoiceSample();

    expect(document.querySelector("#player-status").textContent).toBe("Provider rejected the voice");
  });
});

describe("Instruction voice sample page", () => {
  it("updates voices when the selected model changes", async () => {
    renderInstructionSamplePage();
    const modelOptions = {
      ...sampleOptions,
      models: [
        { value: "model-one", label: "Model one" },
        { value: "model-two", label: "Model two" },
      ],
      default_model: "model-one",
      default_voice: "First Voice",
      voices: [{ value: "First Voice", label: "First voice" }],
      voices_by_model: {
        "model-one": [{ value: "First Voice", label: "First voice" }],
        "model-two": [{ value: "Second Voice", label: "Second voice" }],
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(globalThis.Response.json(modelOptions)));

    await import("../../src/tts_app/static/instruction-voice-sample.js?test=model-voices");
    await vi.waitFor(() => expect(document.querySelector("#instruction-voice").value).toBe("First Voice"));
    const modelSelect = document.querySelector("#instruction-model");

    modelSelect.value = "model-two";
    modelSelect.dispatchEvent(new globalThis.Event("change", { bubbles: true }));

    expect(document.querySelector("#instruction-voice").value).toBe("Second Voice");
    expect(document.querySelector("#instruction-voice").textContent).toContain("Second voice");
    expect(document.querySelector("#instruction-voice").textContent).not.toContain("First voice");
  });

  it("loads options and restores the sample button after a validation error", async () => {
    renderInstructionSamplePage();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(globalThis.Response.json(sampleOptions))
      .mockResolvedValueOnce(
        globalThis.Response.json(
          {
            detail: [
              {
                loc: ["body", "sample_text"],
                msg: "String should have at most 50000 characters",
                input: "private submitted value",
              },
            ],
          },
          { status: 422 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await import("../../src/tts_app/static/instruction-voice-sample.js?test=validation-state");
    await vi.waitFor(() => expect(document.querySelector("#instruction-voice").value).toBe("Kai"));

    document.querySelector("#instruction-sample-form").dispatchEvent(
      new globalThis.Event("submit", { bubbles: true, cancelable: true }),
    );

    await vi.waitFor(() => {
      expect(document.querySelector("#instruction-status").textContent).toBe(
        "Sample text: String should have at most 50000 characters",
      );
    });
    expect(document.querySelector("#instruction-sample").disabled).toBe(false);
    expect(document.querySelector("#instruction-status").textContent).not.toContain("private submitted value");
  });

  it("replaces the previous object URL and clears playback state", async () => {
    renderInstructionSamplePage();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(globalThis.Response.json(sampleOptions))
      .mockResolvedValueOnce(new globalThis.Response(new globalThis.Blob(["first"]), { status: 200 }))
      .mockResolvedValueOnce(new globalThis.Response(new globalThis.Blob(["second"]), { status: 200 }))
      .mockResolvedValueOnce(new globalThis.Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn().mockReturnValueOnce("blob:first").mockReturnValueOnce("blob:second");
    const revokeObjectURL = vi.fn();
    const NativeURL = globalThis.URL;
    class TestURL extends NativeURL {}
    TestURL.createObjectURL = createObjectURL;
    TestURL.revokeObjectURL = revokeObjectURL;
    vi.stubGlobal("URL", TestURL);
    vi.spyOn(globalThis.HTMLMediaElement.prototype, "play").mockResolvedValue();
    vi.spyOn(globalThis.HTMLMediaElement.prototype, "load").mockImplementation(() => {});

    await import("../../src/tts_app/static/instruction-voice-sample.js?test=playback-state");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const form = document.querySelector("#instruction-sample-form");

    form.dispatchEvent(new globalThis.Event("submit", { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(document.querySelector("#instruction-audio").getAttribute("src")).toBe("blob:first"));
    form.dispatchEvent(new globalThis.Event("submit", { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(document.querySelector("#instruction-audio").getAttribute("src")).toBe("blob:second"));

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:first");
    document.querySelector("#clear-instruction-samples").click();
    await vi.waitFor(() => expect(document.querySelector("#instruction-status").textContent).toBe("Samples cleared"));
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:second");
    expect(document.querySelector("#instruction-audio").hasAttribute("src")).toBe(false);
    expect(document.querySelector("#clear-instruction-samples").disabled).toBe(false);
  });
});
