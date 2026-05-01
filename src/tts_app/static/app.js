const state = {
  inputMode: "text",
  generations: [],
  currentGenerationId: null,
  currentDetail: null,
  currentSegmentIndex: 0,
  eventSource: null,
};

const views = document.querySelectorAll(".view");
const navButtons = document.querySelectorAll(".nav-button");
const textModeButton = document.querySelector("#text-mode");
const urlModeButton = document.querySelector("#url-mode");
const textInput = document.querySelector("#text-input");
const urlInput = document.querySelector("#url-input");
const textLabel = document.querySelector("#text-label");
const urlLabel = document.querySelector("#url-label");
const generateForm = document.querySelector("#generate-form");
const autoplayInput = document.querySelector("#autoplay");
const historySearch = document.querySelector("#history-search");
const historyList = document.querySelector("#history-list");
const backToHistory = document.querySelector("#back-to-history");
const playPauseButton = document.querySelector("#play-pause");
const playerStatus = document.querySelector("#player-status");
const scrollFollow = document.querySelector("#scroll-follow");
const readingPane = document.querySelector("#reading-pane");
const audioPlayer = document.querySelector("#audio-player");

function showView(viewId) {
  views.forEach((view) => {
    view.classList.toggle("active-view", view.id === viewId);
  });
  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewId);
  });
  if (viewId === "history-view") {
    loadHistory();
  }
}

function setInputMode(mode) {
  state.inputMode = mode;
  const isText = mode === "text";
  textModeButton.classList.toggle("active", isText);
  urlModeButton.classList.toggle("active", !isText);
  textInput.classList.toggle("hidden", !isText);
  textLabel.classList.toggle("hidden", !isText);
  urlInput.classList.toggle("hidden", isText);
  urlLabel.classList.toggle("hidden", isText);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function submitGeneration(event) {
  event.preventDefault();
  const isText = state.inputMode === "text";
  const endpoint = isText ? "/api/generations/text" : "/api/generations/url";
  const payload = {
    autoplay: autoplayInput.checked,
  };

  if (isText) {
    payload.text = textInput.value.trim();
    payload.title = "Manual text";
  } else {
    payload.url = urlInput.value.trim();
  }

  if ((isText && !payload.text) || (!isText && !payload.url)) {
    return;
  }

  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    playerStatus.textContent = "Generation failed to start";
    return;
  }

  const result = await response.json();
  await openGeneration(result.generation_id, autoplayInput.checked);
}

async function loadHistory() {
  const response = await fetch("/api/generations");
  if (!response.ok) {
    historyList.innerHTML = '<div class="history-item">Unable to load history</div>';
    return;
  }
  state.generations = await response.json();
  renderHistory();
}

function renderHistory() {
  const query = historySearch.value.trim().toLowerCase();
  const rows = state.generations.filter((item) => {
    const text = `${item.title} ${item.text_preview} ${item.url ?? ""}`.toLowerCase();
    return text.includes(query);
  });

  if (rows.length === 0) {
    historyList.innerHTML = '<div class="history-item">No generations found</div>';
    return;
  }

  historyList.innerHTML = rows
    .map((item) => {
      const created = item.created_at ? new Date(`${item.created_at}Z`).toLocaleString() : "";
      return `
        <button class="history-item" type="button" data-generation-id="${item.id}">
          <div class="history-item-title">${escapeHtml(item.title)}</div>
          <div class="history-item-meta">${escapeHtml(item.status)} ${escapeHtml(created)}</div>
          <div class="history-item-preview">${escapeHtml(item.text_preview)}</div>
        </button>
      `;
    })
    .join("");
}

async function openGeneration(generationId, shouldAutoplay = false) {
  state.currentGenerationId = generationId;
  state.currentSegmentIndex = 0;
  showView("playback-view");
  subscribeToGeneration(generationId);
  await loadGenerationDetail(generationId);
  if (shouldAutoplay) {
    playSegment(0);
  }
}

async function loadGenerationDetail(generationId) {
  const response = await fetch(`/api/generations/${generationId}`);
  if (!response.ok) {
    playerStatus.textContent = "Unable to load generation";
    return;
  }
  state.currentDetail = await response.json();
  renderPlayback();
}

function subscribeToGeneration(generationId) {
  if (state.eventSource) {
    state.eventSource.close();
  }

  state.eventSource = new EventSource(`/api/generations/${generationId}/events`);
  state.eventSource.onmessage = async (message) => {
    const event = JSON.parse(message.data);
    if (event.type === "segment_completed" || event.type === "generation_completed") {
      await loadGenerationDetail(generationId);
      if (
        autoplayInput.checked &&
        audioPlayer.paused &&
        event.type === "segment_completed" &&
        event.segment_index === state.currentSegmentIndex
      ) {
        playSegment(event.segment_index);
      }
    }
    if (event.type === "generation_failed") {
      playerStatus.textContent = event.error || "Generation failed";
    }
  };
}

function renderPlayback() {
  const detail = state.currentDetail;
  if (!detail) {
    return;
  }

  document.querySelector("#playback-title").textContent = detail.generation.title;
  const audioByIndex = new Map(detail.audio_segments.map((segment) => [segment.segment_index, segment]));
  readingPane.innerHTML = detail.text_segments
    .map((segment) => {
      const audio = audioByIndex.get(segment.segment_index);
      const isReady = Boolean(audio);
      const classes = ["text-segment"];
      if (!isReady) {
        classes.push("pending");
      }
      if (segment.segment_index === state.currentSegmentIndex) {
        classes.push("active-segment");
      }
      return `
        <section class="${classes.join(" ")}" data-segment-index="${segment.segment_index}" data-audio-id="${audio ? audio.id : ""}">
          ${escapeHtml(segment.text)}
        </section>
      `;
    })
    .join("");

  updatePlayerStatus();
  scrollActiveSegmentIntoView();
}

function audioSegmentForIndex(segmentIndex) {
  if (!state.currentDetail) {
    return null;
  }
  return state.currentDetail.audio_segments.find((segment) => segment.segment_index === segmentIndex) || null;
}

function playSegment(segmentIndex) {
  const audio = audioSegmentForIndex(segmentIndex);
  state.currentSegmentIndex = segmentIndex;
  updateActiveSegment();
  updatePlayerStatus();

  if (!audio || !state.currentGenerationId) {
    return;
  }

  audioPlayer.src = `/api/audio/${state.currentGenerationId}/${audio.id}`;
  audioPlayer.play().catch(() => {
    playerStatus.textContent = "Tap Play to start audio";
  });
}

function updateActiveSegment() {
  document.querySelectorAll(".text-segment").forEach((segment) => {
    segment.classList.toggle("active-segment", Number(segment.dataset.segmentIndex) === state.currentSegmentIndex);
  });
  scrollActiveSegmentIntoView();
}

function scrollActiveSegmentIntoView() {
  if (!scrollFollow.checked) {
    return;
  }
  document.querySelector(".active-segment")?.scrollIntoView({ block: "center", behavior: "smooth" });
}

function updatePlayerStatus() {
  if (!state.currentDetail) {
    playerStatus.textContent = "No segment selected";
    return;
  }
  const total = state.currentDetail.text_segments.length;
  const audio = audioSegmentForIndex(state.currentSegmentIndex);
  playerStatus.textContent = audio
    ? `Segment ${state.currentSegmentIndex + 1} of ${total}`
    : `Segment ${state.currentSegmentIndex + 1} pending`;
}

navButtons.forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

textModeButton.addEventListener("click", () => setInputMode("text"));
urlModeButton.addEventListener("click", () => setInputMode("url"));
generateForm.addEventListener("submit", submitGeneration);
historySearch.addEventListener("input", renderHistory);
backToHistory.addEventListener("click", () => showView("history-view"));

historyList.addEventListener("click", (event) => {
  const item = event.target.closest("[data-generation-id]");
  if (item) {
    openGeneration(Number(item.dataset.generationId));
  }
});

readingPane.addEventListener("click", (event) => {
  const segment = event.target.closest("[data-segment-index]");
  if (segment) {
    playSegment(Number(segment.dataset.segmentIndex));
  }
});

playPauseButton.addEventListener("click", () => {
  if (audioPlayer.paused) {
    const audio = audioSegmentForIndex(state.currentSegmentIndex);
    if (audioPlayer.src && audio) {
      audioPlayer.play().catch(() => {
        playerStatus.textContent = "Tap Play to start audio";
      });
    } else {
      playSegment(state.currentSegmentIndex);
    }
    return;
  }
  audioPlayer.pause();
});

audioPlayer.addEventListener("play", () => {
  playPauseButton.textContent = "Pause";
});

audioPlayer.addEventListener("pause", () => {
  playPauseButton.textContent = "Play";
});

audioPlayer.addEventListener("ended", () => {
  const nextIndex = state.currentSegmentIndex + 1;
  if (state.currentDetail && nextIndex < state.currentDetail.text_segments.length) {
    playSegment(nextIndex);
  }
});

loadHistory();
