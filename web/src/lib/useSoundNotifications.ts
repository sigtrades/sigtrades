import { useEffect, useRef } from "react";
import api from "./api";
import { normalizeExecutionsResponse } from "./executions";

function playNotificationSound() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(660, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.36);
    window.setTimeout(() => void ctx.close(), 500);
  } catch {
    // ignore autoplay / unsupported environments
  }
}

function executionFingerprint(items: { signal_id: string; status: string; created_at?: string }[]) {
  return items.map((e) => `${e.signal_id}|${e.status}|${e.created_at ?? ""}`).join(";");
}

/** Poll recent executions and play a short sound when new activity appears. */
export function useSoundNotifications(enabled: boolean) {
  const lastFingerprint = useRef<string | null>(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (!enabled) {
      initialized.current = false;
      lastFingerprint.current = null;
      return;
    }

    const poll = async () => {
      if (document.hidden) return;
      try {
        const res = await api.get("/config/executions", { params: { limit: 20, offset: 0 } });
        const items = normalizeExecutionsResponse(res.data).items;
        const fingerprint = executionFingerprint(items);

        if (!initialized.current) {
          initialized.current = true;
          lastFingerprint.current = fingerprint;
          return;
        }

        if (fingerprint !== lastFingerprint.current) {
          lastFingerprint.current = fingerprint;
          playNotificationSound();
        }
      } catch {
        // ignore transient poll errors
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), 5000);
    return () => window.clearInterval(timer);
  }, [enabled]);
}
