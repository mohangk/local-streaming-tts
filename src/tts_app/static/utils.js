export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function setButtonBusy(button, busy, label) {
  if (!button) {
    return;
  }
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    if (label) {
      button.textContent = label;
    }
    button.classList.add("is-busy");
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    return;
  }
  if ("originalLabel" in button.dataset) {
    button.textContent = button.dataset.originalLabel;
    delete button.dataset.originalLabel;
  }
  button.classList.remove("is-busy");
  button.removeAttribute("aria-busy");
  button.disabled = false;
}

export async function withButtonBusy(button, label, operation) {
  setButtonBusy(button, true, label);
  try {
    return await operation();
  } finally {
    setButtonBusy(button, false);
  }
}

export function formatSpeed(value) {
  const speed = Number(value || 1);
  return `${Number.isInteger(speed) ? speed.toFixed(0) : speed}x`;
}
