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

export function createQueuedProgressSaver(persistProgress) {
  let queue = Promise.resolve();
  return function saveProgress(snapshot) {
    queue = queue.catch(() => {}).then(() => persistProgress(snapshot));
    return queue;
  };
}

export function continuousAudioUrl(generationId, segmentIndex) {
  return `/api/generations/${generationId}/continuous-audio?start_segment=${segmentIndex}`;
}

function clampSegmentIndex(segmentIndex, totalSegments) {
  const total = Number(totalSegments || 0);
  if (!Number.isFinite(total) || total <= 0) {
    return 0;
  }

  const index = Number(segmentIndex || 0);
  if (!Number.isFinite(index)) {
    return 0;
  }

  return Math.min(Math.max(Math.trunc(index), 0), total - 1);
}

export function estimateContinuousSegmentIndex({
  currentTime,
  duration,
  startSegmentIndex,
  totalSegments,
  audioSegments,
}) {
  const startIndex = clampSegmentIndex(startSegmentIndex, totalSegments);
  const elapsed = Number(currentTime);
  const totalDuration = Number(duration);

  if (!Number.isFinite(elapsed)) {
    return startIndex;
  }

  const segments = Array.isArray(audioSegments)
    ? audioSegments
        .map((segment) => ({
          segmentIndex: Number(segment.segment_index),
          durationMs: Number(segment.duration_ms),
          byteSize: Number(segment.byte_size),
        }))
        .filter(
          (segment) =>
            Number.isFinite(segment.segmentIndex) &&
            segment.segmentIndex >= startIndex &&
            ((Number.isFinite(segment.durationMs) && segment.durationMs > 0) ||
              (Number.isFinite(segment.byteSize) && segment.byteSize > 0)),
        )
        .sort((left, right) => left.segmentIndex - right.segmentIndex)
    : [];

  const durationSegments = segments.filter((segment) => Number.isFinite(segment.durationMs) && segment.durationMs > 0);
  const totalDurationMs = durationSegments.reduce((sum, segment) => sum + segment.durationMs, 0);
  if (durationSegments.length === segments.length && totalDurationMs > 0) {
    const elapsedMs = Math.min(Math.max(elapsed * 1000, 0), totalDurationMs);
    let cumulativeMs = 0;
    for (const segment of durationSegments) {
      cumulativeMs += segment.durationMs;
      if (elapsedMs < cumulativeMs) {
        return clampSegmentIndex(segment.segmentIndex, totalSegments);
      }
    }
    return clampSegmentIndex(durationSegments[durationSegments.length - 1].segmentIndex, totalSegments);
  }

  const byteSegments = segments.filter((segment) => Number.isFinite(segment.byteSize) && segment.byteSize > 0);
  const totalBytes = byteSegments.reduce((sum, segment) => sum + segment.byteSize, 0);
  if (byteSegments.length === 0 || totalBytes <= 0) {
    return startIndex;
  }

  if (!Number.isFinite(totalDuration) || totalDuration <= 0) {
    return startIndex;
  }

  const playbackRatio = Math.min(Math.max(elapsed / totalDuration, 0), 1);
  const elapsedBytes = playbackRatio * totalBytes;
  let cumulativeBytes = 0;
  for (const segment of byteSegments) {
    cumulativeBytes += segment.byteSize;
    if (elapsedBytes < cumulativeBytes) {
      return clampSegmentIndex(segment.segmentIndex, totalSegments);
    }
  }

  return clampSegmentIndex(byteSegments[byteSegments.length - 1].segmentIndex, totalSegments);
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
