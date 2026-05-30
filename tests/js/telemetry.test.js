import { describe, expect, it, vi } from "vitest";
import {
  createPlaybackTelemetry,
  playbackTelemetryContext,
} from "../../src/tts_app/static/telemetry.js";

function generationState(overrides = {}) {
  return {
    currentGenerationId: 7,
    currentSegmentIndex: 2,
    currentDetail: {
      audio_segments: [{ id: 42, segment_index: 2 }],
    },
    samplePlayback: false,
    continuousPlayback: true,
    autoplay: true,
    wakeLock: {},
    eventSource: { readyState: 1 },
    ...overrides,
  };
}

function audio(overrides = {}) {
  return {
    paused: false,
    ended: false,
    currentTime: 12.5,
    duration: 30,
    readyState: 4,
    networkState: 1,
    ...overrides,
  };
}

describe("playbackTelemetryContext", () => {
  it("builds content-free playback context for a generation segment", () => {
    expect(playbackTelemetryContext(generationState(), audio())).toEqual({
      generationId: 7,
      segmentIndex: 2,
      audioSegmentId: 42,
      payload: {
        audio_current_time: 12.5,
        audio_duration: 30,
        audio_ended: false,
        audio_network_state: 1,
        audio_paused: false,
        audio_ready_state: 4,
        autoplay: true,
        continuous_playback: true,
        event_source_ready_state: 1,
        wake_lock_active: true,
      },
    });
  });

  it("returns null for voice sample playback", () => {
    expect(playbackTelemetryContext(generationState({ samplePlayback: true }), audio())).toBeNull();
  });
});

describe("createPlaybackTelemetry", () => {
  it("queues and flushes generation events", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true }));
    const telemetry = createPlaybackTelemetry({ fetchImpl, sessionId: "session-1710000000000-abc123" });

    telemetry.record(generationState(), audio(), "audio_play", { visibility_state: "visible" });
    await telemetry.flush();

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, options] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/generations/7/playback-telemetry");
    expect(options.method).toBe("POST");
    expect(options.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(options.body)).toEqual({
      session_id: "session-1710000000000-abc123",
      events: [
        {
          event_name: "audio_play",
          segment_index: 2,
          audio_segment_id: 42,
          payload: expect.objectContaining({ visibility_state: "visible", audio_paused: false }),
        },
      ],
    });
  });

  it("does not throw when telemetry delivery fails", async () => {
    const telemetry = createPlaybackTelemetry({
      fetchImpl: vi.fn(async () => {
        throw new Error("offline");
      }),
      sessionId: "session-1710000000000-abc123",
    });

    telemetry.record(generationState(), audio(), "audio_waiting");
    await expect(telemetry.flush()).resolves.toBe(false);
  });
});
