export default function Pagination({
  page,
  totalPages,
  total,
  onPrev,
  onNext,
}: {
  page: number;
  totalPages: number;
  total?: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500">
        第 {page} / {totalPages} 页{total !== undefined ? ` · 共 ${total} 条` : ""}
      </span>
      <div className="flex gap-2">
        <button type="button" className="btn-secondary py-1.5" disabled={page <= 1} onClick={onPrev}>
          上一页
        </button>
        <button type="button" className="btn-secondary py-1.5" disabled={page >= totalPages} onClick={onNext}>
          下一页
        </button>
      </div>
    </div>
  );
}
