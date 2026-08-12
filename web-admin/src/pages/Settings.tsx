import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { settingsApi } from "@/api";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import { formatKvValue } from "@/lib/formatDisplay";

type SettingsData = {
  email?: { configured: boolean; from_email?: string; from_name?: string };
  stripe?: { secret_key_configured: boolean; webhook_configured: boolean };
  frontend_url?: string;
  redis_url_configured?: boolean;
  admin_username?: string;
  operations_username?: string;
};

export default function Settings() {
  const [data, setData] = useState<SettingsData | null>(null);
  const [kv, setKv] = useState<{ key: string; value: unknown }[]>([]);
  const [discordAudit, setDiscordAudit] = useState<{ checklist?: string[]; invite_template?: string } | null>(null);

  useEffect(() => {
    settingsApi.get().then((r) => setData(r.data || r)).catch(() => setData(null));
    api.get("/settings/kv").then((r) => setKv((r.data.data || []).filter((row: { key: string }) => !row.key.startsWith("agent_release")))).catch(() => setKv([]));
    api.get("/discord/bot-audit").then((r) => setDiscordAudit(r.data?.data || r.data)).catch(() => setDiscordAudit(null));
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader title="系统设置" subtitle="邮件、Stripe 与 Discord 合规" />

      {data && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Resend 邮件" value={data.email?.configured ? "已配置" : "未配置"} tone={data.email?.configured ? "green" : "amber"} hint={data.email?.from_email} />
          <StatCard label="Stripe Secret" value={data.stripe?.secret_key_configured ? "已配置" : "未配置"} tone={data.stripe?.secret_key_configured ? "green" : "amber"} />
          <StatCard label="Stripe Webhook" value={data.stripe?.webhook_configured ? "已配置" : "未配置"} tone={data.stripe?.webhook_configured ? "green" : "amber"} />
          <StatCard label="Redis" value={data.redis_url_configured ? "已连接" : "未配置"} tone={data.redis_url_configured ? "green" : "amber"} />
        </div>
      )}

      <div className="card space-y-3 text-sm">
        <h2 className="font-semibold">运行信息</h2>
        <Row label="前端 URL" value={data?.frontend_url || "—"} />
        <Row label="Admin 账号" value={data?.admin_username || "—"} />
        <Row label="运营账号" value={data?.operations_username || "—"} />
        <Row label="发件人" value={data?.email?.from_name ? `${data.email.from_name} <${data.email.from_email}>` : "—"} />
        <p className="border-t border-slate-100 pt-3 text-xs text-slate-500">
          Agent 版本发布已移至 <Link to="/agents/release" className="text-brand-600 hover:underline">Agent 与执行 → Agent 发布</Link>
        </p>
      </div>

      {kv.length > 0 && (
        <div className="card overflow-hidden p-0">
          <div className="border-b px-4 py-3 text-sm font-semibold">KV 配置</div>
          <table className="min-w-full text-sm">
            <tbody>
              {kv.map((row) => (
                <tr key={row.key} className="border-b border-slate-100">
                  <td className="px-4 py-3 font-mono text-xs">{row.key}</td>
                  <td className="px-4 py-3 text-slate-600">{formatKvValue(row.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h2 className="mb-3 font-semibold">Discord Bot 审核清单</h2>
        {discordAudit?.checklist ? (
          <ul className="space-y-2">
            {discordAudit.checklist.map((item) => (
              <li key={item} className="flex gap-2 text-sm text-slate-700">
                <StatusBadge value="✓" kind="active" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState message="无法加载 Discord 清单" />
        )}
        {discordAudit?.invite_template ? (
          <p className="mt-4 break-all font-mono text-xs text-slate-500">{discordAudit.invite_template}</p>
        ) : null}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-100 py-2 last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-900">{value}</span>
    </div>
  );
}
