import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";

type PipelineData = {
  source_subscriptions?: { source_id: string; enabled: boolean }[];
  route_rules?: Record<string, unknown>[];
  parse_rules?: Record<string, unknown>[];
  webhook_tokens?: { id: string; source_id: string; label?: string; token_hint: string }[];
};

export default function PipelineTab({ data }: { data: PipelineData | null }) {
  if (!data) return <p className="text-sm text-slate-500">加载中…</p>;

  return (
    <div className="space-y-4">
      <Section title="信号源订阅">
        {(data.source_subscriptions || []).length === 0 ? (
          <EmptyState message="未订阅任何信号源" />
        ) : (
          <Table
            headers={["源 ID", "状态"]}
            rows={(data.source_subscriptions || []).map((s) => [s.source_id, s.enabled ? "启用" : "停用"])}
          />
        )}
      </Section>
      <Section title="路由规则">
        {(data.route_rules || []).length === 0 ? (
          <EmptyState message="无路由规则" />
        ) : (
          <div className="space-y-2">
            {(data.route_rules || []).map((r) => (
              <div key={String(r.id)} className="rounded-lg border border-slate-200 p-3 text-sm">
                <div className="flex flex-wrap gap-2">
                  <StatusBadge value={actionLabel(String(r.action || ""))} />
                  <span className="text-slate-500">{String(r.source_id)}</span>
                  <span className="text-slate-500">→ {String(r.broker || "—")}</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  订单策略：{policyLabel(String(r.order_type_policy || ""))} · 账号：
                  {String(r.account_label || r.account_id || "—")}
                </p>
              </div>
            ))}
          </div>
        )}
      </Section>
      <Section title="解析规则">
        {(data.parse_rules || []).length === 0 ? (
          <EmptyState message="无解析规则" />
        ) : (
          <Table
            headers={["源 ID", "模式", "标签"]}
            rows={(data.parse_rules || []).map((p) => [String(p.source_id), String(p.parse_mode), String(p.label || "—")])}
          />
        )}
      </Section>
      <Section title="Webhook">
        {(data.webhook_tokens || []).length === 0 ? (
          <EmptyState message="暂无 Webhook" />
        ) : (
          <Table
            headers={["源 ID", "标签", "Token 提示"]}
            rows={(data.webhook_tokens || []).map((w) => [w.source_id, w.label || "—", w.token_hint])}
          />
        )}
      </Section>
    </div>
  );
}

function actionLabel(action: string): string {
  const map: Record<string, string> = {
    auto_trade: "自动下单",
    confirm_trade: "确认后下单",
    notify_only: "仅通知",
    both: "通知 + 自动下单",
  };
  return map[action] || action || "—";
}

function policyLabel(policy: string): string {
  const map: Record<string, string> = {
    MKT_only: "市价单",
    LMT_then_MKT: "限价优先（LMT → MKT）",
    LMT_only: "限价单",
  };
  return map[policy] || policy || "—";
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">{title}</h3>
      {children}
    </div>
  );
}

function Table({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <table className="min-w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-slate-500">
          {headers.map((h) => (
            <th key={h} className="pb-2 pr-4">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} className="border-t border-slate-100">
            {row.map((cell, j) => (
              <td key={j} className="py-2 pr-4">
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
