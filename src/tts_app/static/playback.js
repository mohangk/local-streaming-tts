export function chooseResumeSegmentIndex({ lastSegmentIndex, totalSegments }) {
  const total = Number(totalSegments || 0);
  if (!Number.isFinite(total) || total <= 0) {
    return 0;
  }

  const saved = Number(lastSegmentIndex || 0);
  if (!Number.isFinite(saved)) {
    return 0;
  }

  return Math.min(Math.max(saved, 0), total - 1);
}

export function buildProgressPayload(segmentIndex, options = {}) {
  return {
    segment_index: segmentIndex,
    completed: Boolean(options.completed),
  };
}

export function continuousAudioUrl(generationId, segmentIndex) {
  return `/api/generations/${generationId}/continuous-audio?start_segment=${segmentIndex}`;
}

export function endedPlaybackAction({
  samplePlayback,
  continuousPlayback,
  generationStatus,
  currentSegmentIndex,
  totalSegments,
}) {
  if (samplePlayback) {
    return { type: "clear-sample" };
  }

  if (continuousPlayback && totalSegments > 0 && generationStatus === "completed") {
    return { type: "complete", segmentIndex: totalSegments - 1 };
  }

  if (totalSegments > 0 && currentSegmentIndex >= totalSegments - 1) {
    return { type: "complete", segmentIndex: currentSegmentIndex };
  }

  return { type: "stop" };
}
