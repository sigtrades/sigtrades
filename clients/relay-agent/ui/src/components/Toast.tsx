import { useEffect } from "react";

type Props = {
  message: string;
  variant?: "success" | "error";
  onClose: () => void;
  durationMs?: number;
};

export default function Toast({ message, variant = "success", onClose, durationMs = 3200 }: Props) {
  useEffect(() => {
    const timer = window.setTimeout(onClose, durationMs);
    return () => window.clearTimeout(timer);
  }, [message, onClose, durationMs]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={`toast toast-${variant}`}
    >
      {message}
    </div>
  );
}
