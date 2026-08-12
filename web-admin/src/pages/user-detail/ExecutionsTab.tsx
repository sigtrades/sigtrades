import { Link } from "react-router-dom";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";

type ExecRow = {
  id: string;
  source_id: string;
  signal_id: string;
  broker: string;
  status: string;
  account_label?: string;
  created_at: string;
};

export default function ExecutionsTab({ items }: { items: ExecRow[] | null }) {
  if (!items) return <p className="text-sm text-slate-500">加载中…</p>;
  if (items.length === 0) return <EmptyState message="暂无执行记录" />;

  return (
    <div className="card overflow-hidden p-0">
      <table className="min-w-full text-sm">
        <thead className="border-b bg-slate-50 text-left text-xs text-slate-500">
          <tr>
            <th className="px-4 py-3">信号</th>
            <th className="px-4 py-3">券商</th>
            <th className="px-4 py-3">状态</th>
            <th className="px-4 py-3">时间</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.id} className="border-b border-slate-100">
              <td className="px-4 py-3">
                {e.source_id} / {e.signal_id}
              </td>
              <td className="px-4 py-3">{e.broker} · {e.account_label || "—"}</td>
              <td className="px-4 py-3">
                <StatusBadge value={e.status} />
              </td>
              <td className="px-4 py-3 text-slate-600">{e.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t px-4 py-2 text-xs text-slate-500">
        查看全局筛选请前往 <Link to="/executions" className="text-brand-600 hover:underline">执行记录</Link>
      </p>
    </div>
  );
}
