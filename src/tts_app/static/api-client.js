export async function responseErrorMessage(response, fallback) {
  try {
    const body = await response.json();
    if (typeof body?.detail?.message === "string" && body.detail.message) {
      return body.detail.message;
    }
    if (typeof body?.detail === "string" && body.detail) {
      return body.detail;
    }
    if (Array.isArray(body?.detail)) {
      const messages = body.detail
        .filter((issue) => typeof issue?.msg === "string" && issue.msg)
        .map((issue) => {
          const field = issue.loc?.at(-1);
          return typeof field === "string" ? `${fieldLabel(field)}: ${issue.msg}` : issue.msg;
        });
      if (messages.length) {
        return messages.join("; ");
      }
    }
  } catch {
    // Non-JSON proxy and server errors use the caller's stable fallback.
  }
  return fallback;
}

function fieldLabel(field) {
  const words = field.replaceAll("_", " ");
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
}
