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
  if (state.currentDetail?.generation?.id !== state.currentGenerationId) {
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
  let flushPromise = null;

  function dequeueBatch() {
    const first = queue[0];
    if (!first) {
      return null;
    }
    const generationId = first.generationId;
    const events = queue.filter((item) => item.generationId === generationId).slice(0, 50);
    const eventSet = new Set(events);
    for (let index = queue.length - 1; index >= 0; index -= 1) {
      if (eventSet.has(queue[index])) {
        queue.splice(index, 1);
      }
    }
    return { generationId, events };
  }

  function requeueBatch(events) {
    queue.unshift(...events);
    if (queue.length > MAX_QUEUE_LENGTH) {
      queue.splice(MAX_QUEUE_LENGTH);
    }
  }

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

  async function flushQueue() {
    let allDelivered = true;
    let batch = dequeueBatch();
    while (batch) {
      const { generationId, events } = batch;
      let response;
      try {
        response = await fetchImpl(`/api/generations/${generationId}/playback-telemetry`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: telemetrySessionId,
            events: events.map((item) => item.event),
          }),
        });
      } catch {
        requeueBatch(events);
        return false;
      }
      if (!response.ok) {
        if (!response.status || response.status >= 500) {
          requeueBatch(events);
          return false;
        }
        allDelivered = false;
      }
      batch = dequeueBatch();
    }
    return allDelivered;
  }

  async function flush() {
    if (flushPromise) {
      return flushPromise;
    }
    flushPromise = flushQueue();
    try {
      return await flushPromise;
    } finally {
      flushPromise = null;
    }
  }

  return {
    record,
    flush,
    sessionId: telemetrySessionId,
  };
}
