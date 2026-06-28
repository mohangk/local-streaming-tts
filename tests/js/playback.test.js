import { describe, expect, it } from "vitest";
import {
  buildProgressPayload,
  chooseResumeSegmentIndex,
  continuousAudioUrl,
  createQueuedProgressSaver,
  endedPlaybackAction,
  estimateContinuousSegmentIndex,
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

describe("createQueuedProgressSaver", () => {
  it("serializes saves with the snapshot captured when each save was queued", async () => {
    let releaseFirst;
    const firstBlocked = new Promise((resolve) => {
      releaseFirst = resolve;
    });
    const persisted = [];
    const saveProgress = createQueuedProgressSaver(async (snapshot) => {
      if (snapshot.generationId === 1) {
        await firstBlocked;
      }
      persisted.push(snapshot);
    });
    const firstSave = saveProgress({ generationId: 1, segmentIndex: 4 });
    const secondSave = saveProgress({ generationId: 2, segmentIndex: 0 });

    releaseFirst();
    await Promise.all([firstSave, secondSave]);

    expect(persisted).toEqual([
      { generationId: 1, segmentIndex: 4 },
      { generationId: 2, segmentIndex: 0 },
    ]);
  });
});

describe("continuousAudioUrl", () => {
  it("builds a stable continuous playback URL from a generation and segment", () => {
    expect(continuousAudioUrl(36, 25)).toBe("/api/generations/36/continuous-audio?start_segment=25");
  });
});

describe("estimateContinuousSegmentIndex", () => {
  const audioSegments = [
    { segment_index: 0, byte_size: 100 },
    { segment_index: 1, byte_size: 300 },
    { segment_index: 2, byte_size: 600 },
  ];

  it("maps continuous playback time to a segment by cumulative audio bytes", () => {
    expect(
      estimateContinuousSegmentIndex({
        currentTime: 0,
        duration: 100,
        startSegmentIndex: 0,
        totalSegments: 3,
        audioSegments,
      }),
    ).toBe(0);
    expect(
      estimateContinuousSegmentIndex({
        currentTime: 11,
        duration: 100,
        startSegmentIndex: 0,
        totalSegments: 3,
        audioSegments,
      }),
    ).toBe(1);
    expect(
      estimateContinuousSegmentIndex({
        currentTime: 41,
        duration: 100,
        startSegmentIndex: 0,
        totalSegments: 3,
        audioSegments,
      }),
    ).toBe(2);
  });

  it("prefers segment durations when stream duration is unavailable", () => {
    expect(
      estimateContinuousSegmentIndex({
        currentTime: 3.1,
        duration: Number.NaN,
        startSegmentIndex: 0,
        totalSegments: 3,
        audioSegments: [
          { segment_index: 0, duration_ms: 1000, byte_size: 999 },
          { segment_index: 1, duration_ms: 2000, byte_size: 1 },
          { segment_index: 2, duration_ms: 4000, byte_size: 1 },
        ],
      }),
    ).toBe(2);
  });

  it("does not skip segments when only some durations are available", () => {
    expect(
      estimateContinuousSegmentIndex({
        currentTime: 11,
        duration: 100,
        startSegmentIndex: 0,
        totalSegments: 3,
        audioSegments: [
          { segment_index: 0, duration_ms: 1000, byte_size: 100 },
          { segment_index: 1, duration_ms: null, byte_size: 300 },
          { segment_index: 2, duration_ms: 4000, byte_size: 600 },
        ],
      }),
    ).toBe(1);
  });

  it("uses the selected start segment as the beginning of the continuous stream", () => {
    expect(
      estimateContinuousSegmentIndex({
        currentTime: 20,
        duration: 90,
        startSegmentIndex: 1,
        totalSegments: 3,
        audioSegments,
      }),
    ).toBe(1);
    expect(
      estimateContinuousSegmentIndex({
        currentTime: 31,
        duration: 90,
        startSegmentIndex: 1,
        totalSegments: 3,
        audioSegments,
      }),
    ).toBe(2);
  });

  it("clamps invalid playback metadata to the selected segment", () => {
    expect(
      estimateContinuousSegmentIndex({
        currentTime: Number.NaN,
        duration: 100,
        startSegmentIndex: 2,
        totalSegments: 3,
        audioSegments,
      }),
    ).toBe(2);
    expect(
      estimateContinuousSegmentIndex({
        currentTime: 10,
        duration: 0,
        startSegmentIndex: 99,
        totalSegments: 3,
        audioSegments,
      }),
    ).toBe(2);
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
