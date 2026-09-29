import { useCallback, useEffect, useRef, useState } from "react";

import { checkHealth } from "../lib/api";

export type BackendStatus = "connecting" | "waking" | "online" | "offline";

const RETRY_MS = 5_000;
const MAX_ATTEMPTS = 24; // ~2+ minutes of retries during a cold start

// Free-tier hosts answer with errors while the backend wakes up, so keep retrying
// instead of giving up after the first failure.
export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>("connecting");
  const [mockMode, setMockMode] = useState(false);
  const online = useRef(false);

  const markOnline = useCallback(() => {
    online.current = true;
    setStatus("online");
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const attempt = async (n: number) => {
      if (cancelled || online.current) return;
      try {
        const health = await checkHealth();
        if (cancelled) return;
        setMockMode(health.mock_mode);
        markOnline();
      } catch {
        if (cancelled || online.current) return;
        if (n < MAX_ATTEMPTS) {
          setStatus("waking");
          timer = setTimeout(() => attempt(n + 1), RETRY_MS);
        } else {
          setStatus("offline");
        }
      }
    };
    attempt(1);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [markOnline]);

  return { status, mockMode, markOnline };
}
