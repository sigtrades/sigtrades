import EmptyState from "@/components/ui/EmptyState";
import StatusBadge from "@/components/ui/StatusBadge";

type Item = {
  id: string;
  version?: string;
  agreed_at?: string;
  ip_address?: string | null;
  user_agent?: string | null;
};

type Data = {
  required_version?: string;
  accepted_current?: boolean;
  items?: Item[];
};

export default function RiskDisclosureTab({ data }: { data: Data | null }) {
  if (!data) return <p className="text-sm text-slate-500">加载中…</p>;

  const items = data.items || [];

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-3 text-sm">
        <span className="text-slate-500">当前文档版本</span>
        <span className="font-mono text-slate-800">{data.required_version || "—"}</span>
        <StatusBadge
          value={data.accepted_current ? "已同意当前版本" : "未同意当前版本"}
          kind={data.accepted_current ? "active" : "pending"}
        />
      </div>
      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-4 py-3">版本</th>
              <th className="px-4 py-3">同意时间</th>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">User-Agent</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={4}>
                  <EmptyState message="暂无风险揭示同意记录" />
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 align-top">
                  <td className="px-4 py-3 font-mono text-xs">{row.version || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{row.agreed_at || "—"}</td>
                  <td className="px-4 py-3 font-mono text-xs">{row.ip_address || "—"}</td>
                  <td className="max-w-md px-4 py-3 text-xs text-slate-500 break-all">
                    {row.user_agent || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
