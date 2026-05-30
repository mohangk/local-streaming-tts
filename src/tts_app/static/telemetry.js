const MAX_QUEUE_LENGTH = 100;

function sessionId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function audioSegmentForState(state) {
  return state.currentDetail?.audio_segments.find((segment) => segment.segment_index === state.currentSegmentIndex) || null;
}

export function playbackTelemetryContext(state, audioPlayer) {
  if (!state.currentGenerationId || state.samplePlayback) {
    return null;
  }
  const audioSegment = audioSegmentForState(state);
  return {
    generationId: state.currentGenerationId,
    segmentIndex: state.currentSegmentIndex,
    audioSegmentId: audioSegment?.id ?? null,
    payload: {
      audio_current_time: Number.isFinite(audioPlayer.currentTime) ? audioPlayer.currentTime : null,
      audio_duration: Number.isFinite(audioPlayer.duration) ? audioPlayer.duration : null,
      audio_ended: Boolean(audioPlayer.ended),
      audio_network_state: audioPlayer.networkState,
      audio_paused: Boolean(audioPlayer.paused),
      audio_ready_state: audioPlayer.readyState,
      autoplay: Boolean(state.autoplay),
      continuous_playback: Boolean(state.continuousPlayback),
      event_source_ready_state: state.eventSource?.readyState ?? null,
      wake_lock_active: Boolean(state.wakeLock),
    },
  };
}

export function createPlaybackTelemetry(options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const telemetrySessionId = options.sessionId || sessionId();
  const queue = [];

  function record(state, audioPlayer, eventName, payload = {}) {
    const context = playbackTelemetryContext(state, audioPlayer);
    if (!context) {
      return false;
    }
    queue.push({
      generationId: context.generationId,
      event: {
        event_name: eventName,
        segment_index: context.segmentIndex,
        audio_segment_id: context.audioSegmentId,
        payload: { ...context.payload, ...payload },
      },
    });
    if (queue.length > MAX_QUEUE_LENGTH) {
      queue.splice(0, queue.length - MAX_QUEUE_LENGTH);
    }
    return true;
  }

  async function flush() {
    const first = queue[0];
    if (!first) {
      return true;
    }
    const generationId = first.generationId;
    const events = queue.filter((item) => item.generationId === generationId).slice(0, 50);
    try {
      const response = await fetchImpl(`/api/generations/${generationId}/playback-telemetry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: telemetrySessionId,
          events: events.map((item) => item.event),
        }),
      });
      if (!response.ok) {
        return false;
      }
      for (const item of events) {
        const index = queue.indexOf(item);
        if (index >= 0) {
          queue.splice(index, 1);
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  return {
    record,
    flush,
    sessionId: telemetrySessionId,
  };
}
