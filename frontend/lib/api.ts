import type { PredictionsResponse, Sport } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json();
}

export function fetchPredictions(
  date: string,
  sport?: Sport
): Promise<PredictionsResponse> {
  const params = new URLSearchParams({ date });
  if (sport) params.set("sport", sport);
  return request(`/api/predictions?${params}`);
}

export function refreshPredictions(
  date: string,
  sport?: Sport
): Promise<PredictionsResponse> {
  return request("/api/predictions/refresh", {
    method: "POST",
    body: JSON.stringify({ date, sport: sport ?? null }),
  });
}

export function refreshResults(
  date: string,
  sport?: Sport
): Promise<PredictionsResponse> {
  return request("/api/results/refresh", {
    method: "POST",
    body: JSON.stringify({ date, sport: sport ?? null }),
  });
}
