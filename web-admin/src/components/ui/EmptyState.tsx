export default function EmptyState({ message = "暂无数据" }: { message?: string }) {
  return <div className="px-4 py-12 text-center text-sm text-slate-400">{message}</div>;
}
