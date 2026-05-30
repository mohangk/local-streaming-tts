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
      generation: { id: 7 },
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

  it("returns null when generation detail does not match the active generation", () => {
    expect(
      playbackTelemetryContext(
        generationState({ currentGenerationId: 8, currentDetail: { generation: { id: 7 }, audio_segments: [] } }),
        audio(),
      ),
    ).toBeNull();
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

  it("serializes overlapping flushes without duplicating queued events", async () => {
    let resolveFetch;
    const firstResponse = new Promise((resolve) => {
      resolveFetch = () => resolve({ ok: true });
    });
    const fetchImpl = vi.fn(() => firstResponse);
    const telemetry = createPlaybackTelemetry({ fetchImpl, sessionId: "session-1710000000000-abc123" });

    telemetry.record(generationState(), audio(), "audio_ended");
    const firstFlush = telemetry.flush();
    telemetry.record(generationState(), audio(), "playback_ended_action", { type: "complete" });
    const secondFlush = telemetry.flush();

    resolveFetch();
    await firstFlush;
    await secondFlush;

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body).events.map((event) => event.event_name)).toEqual([
      "audio_ended",
    ]);
    expect(JSON.parse(fetchImpl.mock.calls[1][1].body).events.map((event) => event.event_name)).toEqual([
      "playback_ended_action",
    ]);
  });

  it("drops invalid client batches so later telemetry can flush", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 422 }));
    const telemetry = createPlaybackTelemetry({ fetchImpl, sessionId: "session-1710000000000-abc123" });

    telemetry.record(generationState(), audio(), "audio_play");
    await expect(telemetry.flush()).resolves.toBe(false);
    fetchImpl.mockResolvedValueOnce({ ok: true });
    telemetry.record(generationState(), audio(), "audio_pause");
    await expect(telemetry.flush()).resolves.toBe(true);

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(JSON.parse(fetchImpl.mock.calls[1][1].body).events.map((event) => event.event_name)).toEqual([
      "audio_pause",
    ]);
  });

  it("continues draining events queued behind a dropped invalid batch", async () => {
    const fetchImpl = vi.fn(async (url) => ({
      ok: !url.includes("/7/"),
      status: url.includes("/7/") ? 422 : 200,
    }));
    const telemetry = createPlaybackTelemetry({ fetchImpl, sessionId: "session-1710000000000-abc123" });

    telemetry.record(generationState(), audio(), "audio_play");
    telemetry.record(
      generationState({ currentGenerationId: 8, currentDetail: { generation: { id: 8 }, audio_segments: [] } }),
      audio(),
      "audio_pause",
    );
    await expect(telemetry.flush()).resolves.toBe(false);

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/generations/7/playback-telemetry");
    expect(fetchImpl.mock.calls[1][0]).toBe("/api/generations/8/playback-telemetry");
  });
});
