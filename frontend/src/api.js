// In production default to the deployed backend so the app works even if
// VITE_API_URL isn't set at build time; locally fall back to the dev server.
const BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? "https://aihq-api.onrender.com" : "http://localhost:8000");

export function getToken() {
  return localStorage.getItem("hq_token") || "";
}
export function setToken(t) {
  if (t) localStorage.setItem("hq_token", t);
  else localStorage.removeItem("hq_token");
}

export async function api(path, opts = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Token ${getToken()}` } : {}),
      ...(opts.headers || {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    // Only a request that carried a token represents an expired session;
    // a 401 from logging in just means the credentials were wrong.
    if (getToken()) setToken("");
    throw new Error(data.error || "Session expired — log in again.");
  }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
