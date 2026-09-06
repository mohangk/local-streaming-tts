import { escapeHtml, formatSpeed, withButtonBusy } from "./utils.js?v=playback-progress-1";

export function createHistory({ historyList, historySearch, playerStatus, state, openGeneration, resetPlaybackState }) {
  async function loadHistory() {
    try {
      const response = await fetch("/api/generations");
      if (!response.ok) {
        historyList.innerHTML = '<div class="history-item">Unable to load history</div>';
        return;
      }
      state.generations = await response.json();
      renderHistory();
    } catch {
      historyList.innerHTML = '<div class="history-item">Unable to load history</div>';
    }
  }

  function renderHistory() {
    const query = historySearch.value.trim().toLowerCase();
    const rows = state.generations.filter((item) => {
      const text = `${item.title} ${item.text_preview} ${item.url ?? ""} ${item.voice} ${item.settings?.speed ?? ""}`.toLowerCase();
      return text.includes(query);
    });

    if (rows.length === 0) {
      historyList.innerHTML = '<div class="history-item">No generations found</div>';
      return;
    }

    historyList.innerHTML = rows
      .map((item) => {
        const created = item.created_at ? new Date(`${item.created_at}Z`).toLocaleString() : "";
        const speed = item.settings?.speed ?? 1;
        const progress = Number(item.progress_percent || 0);
        const urlMarkup = item.url
          ? `<div class="history-item-url">${escapeHtml(item.url)}</div>`
          : "";
        return `
          <article class="history-item" data-generation-id="${item.id}">
            <div class="history-item-title">${escapeHtml(item.title)}</div>
            <div class="history-item-meta">${escapeHtml(item.status)} ${escapeHtml(created)}</div>
            ${urlMarkup}
            <div class="history-item-preview">${escapeHtml(item.text_preview)}</div>
            <details class="history-details">
              <summary>Details</summary>
              <dl>
                <div><dt>Voice</dt><dd>${escapeHtml(item.voice)}</dd></div>
                <div><dt>Speed</dt><dd>${escapeHtml(formatSpeed(speed))}</dd></div>
                <div><dt>Provider</dt><dd>${escapeHtml(item.provider)}</dd></div>
                <div><dt>Progress</dt><dd>${escapeHtml(progress)}%</dd></div>
              </dl>
            </details>
            <div class="history-actions">
              <button class="secondary-action compact-action" type="button" data-action="open" data-generation-id="${item.id}">Open</button>
              <button class="danger-action compact-action" type="button" data-action="delete" data-generation-id="${item.id}">Delete</button>
            </div>
          </article>
        `;
      })
      .join("");
  }

  async function deleteGeneration(generationId, button = null) {
    if (!window.confirm("Delete this history entry and cached audio?")) {
      return;
    }
    await withButtonBusy(button, "Deleting...", async () => {
      try {
        const response = await fetch(`/api/generations/${generationId}`, { method: "DELETE" });
        if (!response.ok) {
          playerStatus.textContent = "Unable to delete history entry";
          return;
        }
        if (state.currentGenerationId === generationId) {
          resetPlaybackState("Deleted generation");
        }
        await loadHistory();
      } catch {
        playerStatus.textContent = "Unable to delete history entry";
      }
    });
  }

  function registerEvents() {
    historySearch.addEventListener("input", renderHistory);
    historyList.addEventListener("click", (event) => {
      const action = event.target.closest("[data-action]");
      const historyItem = event.target.closest("[data-generation-id]");
      if (!historyItem) {
        return;
      }
      const generationId = Number(historyItem.dataset.generationId);
      if (action?.dataset.action === "delete") {
        deleteGeneration(Number(action.dataset.generationId), action);
        return;
      }
      if (action?.dataset.action === "open") {
        openGeneration(Number(action.dataset.generationId), { subscribe: false, autoplay: true, button: action });
        return;
      }
      if (!action) {
        if (event.target.closest(".history-details") && !action) {
          return;
        }
        openGeneration(generationId, { subscribe: false, autoplay: true });
      }
    });

  }

  return { loadHistory, renderHistory, deleteGeneration, registerEvents };
}
