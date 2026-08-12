import { useEffect } from "react";

type Props = {
  message: string;
  onClose: () => void;
  durationMs?: number;
  variant?: "success" | "error";
};

export default function Toast({
  message,
  onClose,
  durationMs = 3200,
  variant = "success",
}: Props) {
  useEffect(() => {
    const timer = window.setTimeout(onClose, durationMs);
    return () => window.clearTimeout(timer);
  }, [message, onClose, durationMs]);

  const isError = variant === "error";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`pointer-events-none fixed bottom-6 right-6 z-[100] max-w-sm animate-[fade-in_0.2s_ease-out] rounded-xl border px-4 py-3 text-sm font-medium shadow-lg ${
        isError
          ? "border-loss/30 bg-loss-soft text-loss"
          : "border-profit/30 bg-profit-soft text-profit"
      }`}
    >
      {message}
    </div>
  );
}
