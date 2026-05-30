import { describe, expect, it } from "vitest";
import {
  buildProgressPayload,
  chooseResumeSegmentIndex,
  continuousAudioUrl,
  endedPlaybackAction,
} from "../../src/tts_app/static/playback.js";

describe("chooseResumeSegmentIndex", () => {
  it("clamps saved progress into the available text segment range", () => {
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: 2, totalSegments: 5 })).toBe(2);
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: 99, totalSegments: 5 })).toBe(4);
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: -4, totalSegments: 5 })).toBe(0);
  });

  it("resumes at zero for missing, invalid, or empty generation progress", () => {
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: undefined, totalSegments: 5 })).toBe(0);
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: Number.NaN, totalSegments: 5 })).toBe(0);
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: 2, totalSegments: 0 })).toBe(0);
  });
});

describe("buildProgressPayload", () => {
  it("includes segment index and defaults completed to false", () => {
    expect(buildProgressPayload(3)).toEqual({ segment_index: 3, completed: false });
  });

  it("sets completed only when requested", () => {
    expect(buildProgressPayload(3, { completed: true })).toEqual({ segment_index: 3, completed: true });
  });
});

describe("continuousAudioUrl", () => {
  it("builds a stable continuous playback URL from a generation and segment", () => {
    expect(continuousAudioUrl(36, 25)).toBe("/api/generations/36/continuous-audio?start_segment=25");
  });
});

describe("endedPlaybackAction", () => {
  it("clears sample playback without saving generation progress", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: true,
        continuousPlayback: true,
        currentSegmentIndex: 0,
        totalSegments: 3,
      }),
    ).toEqual({ type: "clear-sample" });
  });

  it("marks generation progress complete when a continuous stream ends", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: false,
        continuousPlayback: true,
        generationStatus: "completed",
        currentSegmentIndex: 0,
        totalSegments: 3,
      }),
    ).toEqual({ type: "complete", segmentIndex: 2 });
  });

  it("does not mark progress complete when a failed continuous stream ends", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: false,
        continuousPlayback: true,
        generationStatus: "failed",
        currentSegmentIndex: 0,
        totalSegments: 3,
      }),
    ).toEqual({ type: "stop" });
  });

  it("marks progress completed only at the final generation segment", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: false,
        continuousPlayback: false,
        currentSegmentIndex: 2,
        totalSegments: 3,
      }),
    ).toEqual({ type: "complete", segmentIndex: 2 });
  });

  it("stops without completion for intermediate non-continuous segments", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: false,
        continuousPlayback: false,
        currentSegmentIndex: 1,
        totalSegments: 3,
      }),
    ).toEqual({ type: "stop" });
  });
});
