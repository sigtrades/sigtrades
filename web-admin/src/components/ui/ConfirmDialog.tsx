import { XMarkIcon } from "@heroicons/react/24/outline";

export function ConfirmDialog({
  open,
  title,
  children,
  confirmText = "确定",
  cancelText = "取消",
  danger,
  loading,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  children?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()} role="dialog">
        <div className="mb-3 flex items-start justify-between gap-2">
          <h2 className="pr-2 text-lg font-semibold text-slate-900">{title}</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:text-slate-600">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>
        {children ? <div className="mb-5 text-sm leading-relaxed text-slate-600">{children}</div> : null}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={loading} className="btn-secondary">
            {cancelText}
          </button>
          <button type="button" onClick={onConfirm} disabled={loading} className={danger ? "btn-danger" : "btn-primary"}>
            {loading ? "请稍候…" : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
