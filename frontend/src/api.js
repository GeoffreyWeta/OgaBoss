// In production default to the deployed backend so the app works even if
// VITE_API_URL isn't set at build time; locally fall back to the dev server.
const BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? "https://ogaboss-api.onrender.com" : "http://localhost:8000");

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
  if (res.status === 401) {
    setToken("");
    throw new Error("Session expired — log in again.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
