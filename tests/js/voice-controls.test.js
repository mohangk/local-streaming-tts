import { describe, expect, it } from "vitest";
import { applyStoredVoiceSelection, updateStoredVoiceSelection } from "../../src/tts_app/static/voice-controls.js";

const options = {
  default_language: "en",
  default_voices: { en: "Jennifer", zh: "Cherry" },
  default_voice: "Jennifer",
  default_speed: 1.0,
  voices: [
    { value: "Jennifer", label: "Jennifer", language: "en", preferred: false },
    { value: "Aiden", label: "Aiden", language: "en", preferred: false },
    { value: "Cherry", label: "Cherry", language: "zh", preferred: false },
  ],
  speeds: [
    { value: 1.0, label: "1x" },
    { value: 1.25, label: "1.25x" },
  ],
};

describe("applyStoredVoiceSelection", () => {
  it("uses stored language voice and speed when they are valid", () => {
    expect(
      applyStoredVoiceSelection(options, {
        language: "zh",
        speed: 1.25,
        voices: { zh: "Cherry" },
      }),
    ).toEqual({ language: "zh", voice: "Cherry", speed: 1.25 });
  });

  it("falls back to API defaults when stored values are stale", () => {
    expect(
      applyStoredVoiceSelection(options, {
        language: "fr",
        speed: 1.75,
        voices: { en: "Missing", zh: "Missing" },
      }),
    ).toEqual({ language: "en", voice: "Jennifer", speed: 1.0 });
  });

  it("keeps voices scoped by language", () => {
    expect(
      applyStoredVoiceSelection(options, {
        language: "en",
        speed: 1.0,
        voices: { en: "Aiden", zh: "Cherry" },
      }),
    ).toEqual({ language: "en", voice: "Aiden", speed: 1.0 });
  });
});

describe("updateStoredVoiceSelection", () => {
  it("stores the selected voice under the selected language", () => {
    expect(
      updateStoredVoiceSelection(
        { language: "en", speed: 1.0, voices: { en: "Jennifer" } },
        { language: "zh", voice: "Cherry", speed: 1.25 },
      ),
    ).toEqual({
      language: "zh",
      speed: 1.25,
      voices: {
        en: "Jennifer",
        zh: "Cherry",
      },
    });
  });
});
