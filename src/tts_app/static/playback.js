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

export function endedPlaybackAction({ samplePlayback, continuousPlayback, currentSegmentIndex, totalSegments }) {
  if (samplePlayback) {
    return { type: "clear-sample" };
  }

  const nextIndex = currentSegmentIndex + 1;
  if (continuousPlayback && nextIndex < totalSegments) {
    return { type: "play-next", segmentIndex: nextIndex };
  }

  if (totalSegments > 0 && currentSegmentIndex >= totalSegments - 1) {
    return { type: "complete", segmentIndex: currentSegmentIndex };
  }

  return { type: "stop" };
}
