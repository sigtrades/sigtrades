import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { agentsApi } from "@/api";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import StatCard from "@/components/ui/StatCard";
import { formatBrokers } from "@/lib/formatDisplay";

type AgentRow = {
  user_id: string;
  email?: string | null;
  online: boolean;
  brokers?: unknown;
  updated_at?: string;
  agent_token_count?: number;
};

export default function Agents() {
  const [items, setItems] = useState<AgentRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    agentsApi
      .list()
      .then((data) => setItems(Array.isArray(data) ? data : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const onlineCount = items.filter((i) => i.online).length;

  return (
    <div className="space-y-6">
      <PageHeader title="Agent 连接" subtitle="Relay Agent 在线状态与 token 数量" />
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Presence 记录" value={items.length} />
        <StatCard label="当前在线" value={onlineCount} tone="green" />
        <StatCard label="离线" value={items.length - onlineCount} tone="default" />
      </div>
      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">用户</th>
              <th className="px-4 py-3">在线</th>
              <th className="px-4 py-3">Token 数</th>
              <th className="px-4 py-3">券商能力</th>
              <th className="px-4 py-3">最后更新</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-slate-400">
                  加载中…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <EmptyState message="暂无 Agent 连接记录" />
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.user_id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link to={`/users/${row.user_id}`} className="text-brand-600 hover:underline">
                      {row.email || `${row.user_id.slice(0, 8)}…`}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={row.online ? "在线" : "离线"} kind={row.online ? "online" : "offline"} />
                  </td>
                  <td className="px-4 py-3 tabular-nums">{row.agent_token_count ?? 0}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{formatBrokers(row.brokers)}</td>
                  <td className="px-4 py-3 text-slate-600">{row.updated_at || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
