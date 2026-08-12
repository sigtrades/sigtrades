import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";

type BrokersData = {
  credentials?: Record<string, unknown>[];
  bindings?: Record<string, unknown>[];
};

export default function BrokersTab({ data }: { data: BrokersData | null }) {
  if (!data) return <p className="text-sm text-slate-500">加载中…</p>;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        券商密钥已加密存储，后台仅展示掩码，不会解密明文。
      </div>
      <div className="card">
        <h3 className="mb-3 text-sm font-semibold">凭证（掩码）</h3>
        {(data.credentials || []).length === 0 ? (
          <EmptyState message="未配置券商凭证" />
        ) : (
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="pb-2">券商</th>
                <th className="pb-2">标签</th>
                <th className="pb-2">环境</th>
                <th className="pb-2">密钥</th>
              </tr>
            </thead>
            <tbody>
              {(data.credentials || []).map((c) => (
                <tr key={String(c.id)} className="border-t border-slate-100">
                  <td className="py-2">{String(c.broker)}</td>
                  <td className="py-2">{String(c.label || "—")}</td>
                  <td className="py-2">{String(c.env || "—")}</td>
                  <td className="py-2 font-mono text-xs">
                    {c.has_private_key ? String(c.key_hint) : c.has_secrets ? "secrets 已配置" : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="card">
        <h3 className="mb-3 text-sm font-semibold">账户绑定</h3>
        {(data.bindings || []).length === 0 ? (
          <EmptyState message="无绑定" />
        ) : (
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="pb-2">券商</th>
                <th className="pb-2">标签</th>
                <th className="pb-2">策略</th>
                <th className="pb-2">状态</th>
              </tr>
            </thead>
            <tbody>
              {(data.bindings || []).map((b) => (
                <tr key={String(b.id)} className="border-t border-slate-100">
                  <td className="py-2">{String(b.broker)}</td>
                  <td className="py-2">{String(b.label || b.account_id || "—")}</td>
                  <td className="py-2">{String(b.order_type_policy || "—")}</td>
                  <td className="py-2">
                    <StatusBadge value={b.enabled ? "启用" : "停用"} kind={b.enabled ? "active" : "offline"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
