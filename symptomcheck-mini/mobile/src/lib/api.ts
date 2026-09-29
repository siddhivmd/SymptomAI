import type { Arm, ChatMessage, ChatResponse, HealthResponse, ResultsResponse } from "./types";

// Set EXPO_PUBLIC_BACKEND_URL in mobile/.env (or eas.json) to point at another backend.
// Phones can't reach 127.0.0.1 on your computer, so the default is the deployed Render backend.
const DEFAULT_BACKEND_URL = "https://symptomai-4wvn.onrender.com";

export const API_BASE = (process.env.EXPO_PUBLIC_BACKEND_URL || DEFAULT_BACKEND_URL)
  .trim()
  .replace(/\/+$/, "")
  .replace(/\/(chat|health)$/, "");

const CHAT_TIMEOUT_MS = 90_000; // free-tier backends can take ~60s to wake up
const HEALTH_TIMEOUT_MS = 70_000;

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new ApiError("The backend took too long to respond. It may be waking up — please try again.");
    }
    throw new ApiError("Couldn't reach the backend. Check your internet connection.");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 429) {
    throw new ApiError("Too many messages (limit is 10 per minute). Wait a moment and try again.", 429);
  }
  if (!res.ok) throw new ApiError(`The backend returned an error (HTTP ${res.status}).`, res.status);
  return (await res.json()) as T;
}

export function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health", {}, HEALTH_TIMEOUT_MS);
}

export function sendChat(arm: Arm, messages: ChatMessage[]): Promise<ChatResponse> {
  return request<ChatResponse>(
    "/chat",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arm, messages }),
    },
    CHAT_TIMEOUT_MS,
  );
}

export function getResults(): Promise<ResultsResponse> {
  return request<ResultsResponse>("/api/results", {}, HEALTH_TIMEOUT_MS);
}
