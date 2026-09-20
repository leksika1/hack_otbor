// Single place where the frontend talks to the backend.
// The base URL comes from the environment: in Docker the nginx container
// proxies /api to the backend service, so no host is ever hardcoded here.
const BASE_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');

async function readError(response) {
  try {
    const body = await response.json();
    if (body && typeof body.detail === 'string') return body.detail;
  } catch {
    /* response was not JSON */
  }
  return `Сервер вернул ошибку ${response.status}`;
}

export async function analyzeSession(file, { signal, explain = true } = {}) {
  const form = new FormData();
  form.append('file', file);

  const response = await fetch(`${BASE_URL}/analyze?explain=${explain}`, {
    method: 'POST',
    body: form,
    signal,
  });

  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchHealth({ signal } = {}) {
  const response = await fetch(`${BASE_URL}/health`, { signal });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}
