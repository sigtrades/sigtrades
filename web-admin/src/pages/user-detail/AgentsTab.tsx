import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import { formatBrokers } from "@/lib/formatDisplay";

type AgentsData = {
  tokens?: { id: string; label?: string; created_at?: string; revoked_at?: string; token_hash_hint: string }[];
  presence?: { online: boolean; brokers?: unknown; updated_at?: string } | null;
};

export default function AgentsTab({ data }: { data: AgentsData | null }) {
  if (!data) return <p className="text-sm text-slate-500">加载中…</p>;

  return (
    <div className="space-y-4">
      <div className="card">
        <h3 className="mb-3 text-sm font-semibold">在线状态</h3>
        {data.presence ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <StatusBadge value={data.presence.online ? "在线" : "离线"} kind={data.presence.online ? "online" : "offline"} />
            <span className="text-slate-500">更新：{data.presence.updated_at || "—"}</span>
            {data.presence.brokers ? (
              <span className="text-xs text-slate-500">券商能力：{formatBrokers(data.presence.brokers)}</span>
            ) : null}
          </div>
        ) : (
          <EmptyState message="无 presence 记录" />
        )}
      </div>
      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-4 py-3">标签</th>
              <th className="px-4 py-3">创建</th>
              <th className="px-4 py-3">Token 摘要</th>
              <th className="px-4 py-3">状态</th>
            </tr>
          </thead>
          <tbody>
            {(data.tokens || []).length === 0 ? (
              <tr>
                <td colSpan={4}>
                  <EmptyState />
                </td>
              </tr>
            ) : (
              (data.tokens || []).map((t) => (
                <tr key={t.id} className="border-b border-slate-100">
                  <td className="px-4 py-3">{t.label || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{t.created_at || "—"}</td>
                  <td className="px-4 py-3 font-mono text-xs">{t.token_hash_hint}</td>
                  <td className="px-4 py-3">
                    <StatusBadge value={t.revoked_at ? "已撤销" : "有效"} kind={t.revoked_at ? "offline" : "active"} />
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
