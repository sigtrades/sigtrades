import { useEffect } from "react";
import { createPortal } from "react-dom";

type Props = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: "default" | "danger";
  busy?: boolean;
  alertOnly?: boolean;
  onClose: () => void;
  onConfirm?: () => void;
};

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  variant = "default",
  busy = false,
  alertOnly = false,
  onClose,
  onConfirm,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40"
        aria-label={cancelLabel || confirmLabel}
        disabled={busy}
        onClick={onClose}
      />
      <div
        role={alertOnly ? "alertdialog" : "dialog"}
        aria-modal="true"
        className="relative w-full max-w-md rounded-t-2xl border border-slate-200 bg-white p-5 shadow-xl sm:rounded-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-slate-900">{title}</h3>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{message}</p>
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          {!alertOnly && cancelLabel ? (
            <button type="button" className="btn-secondary w-full text-sm sm:w-auto" disabled={busy} onClick={onClose}>
              {cancelLabel}
            </button>
          ) : null}
          <button
            type="button"
            className={`w-full text-sm sm:w-auto ${variant === "danger" ? "btn-primary border-loss/20 bg-loss text-white hover:bg-loss/90" : "btn-primary"}`}
            disabled={busy}
            onClick={() => (alertOnly ? onClose() : onConfirm?.())}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
