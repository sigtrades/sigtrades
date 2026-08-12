export function AdminToast({
  message,
  type = "success",
  onDismiss,
}: {
  message: string;
  type?: "success" | "error";
  onDismiss: () => void;
}) {
  return (
    <div className="fixed bottom-6 right-6 z-[90] max-w-sm">
      <div
        className={
          type === "error"
            ? "rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 shadow-lg"
            : "rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 shadow-lg"
        }
      >
        <div className="flex items-start justify-between gap-3">
          <span>{message}</span>
          <button type="button" className="text-xs opacity-70 hover:opacity-100" onClick={onDismiss}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
