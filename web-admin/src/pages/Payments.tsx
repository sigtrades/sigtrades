import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { paymentsApi, subscriptionsApi } from "@/api";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import StatusBadge from "@/components/ui/StatusBadge";
import Pagination from "@/components/ui/Pagination";
import EmptyState from "@/components/ui/EmptyState";
import GrantSubscriptionPanel from "@/components/GrantSubscriptionPanel";
import SubscriptionPaymentsPanel from "@/components/SubscriptionPaymentsPanel";

type Stats = {
  active_memberships: number;
  paid_memberships: number;
  gift_memberships: number;
  trial_memberships: number;
  stripe_subscriptions: number;
  payment_consents: number;
  paid_checkout_count: number;
  pending_sync_count: number;
  unpaid_intent_count: number;
  total_paid_amount_usd: number;
  today_paid_count: number;
  today_paid_amount_usd: number;
  payments_by_day: { date: string; count: number; amount_usd: number }[];
  from_date?: string | null;
  to_date?: string | null;
  stripe_configured: boolean;
  webhook_configured: boolean;
};

type SubRow = {
  id: string;
  user_id: string;
  user_email: string;
  plan_code: string;
  plan_name: string;
  status: string;
  stripe_subscription_id?: string;
  period_end?: string;
  source?: string;
  payment_status?: string;
  payment_status_label?: string;
  payment_amount_usd?: number | null;
  billing_interval?: string | null;
};

type Tab = "members" | "payments" | "stats";

function fmtUsd(n: number) {
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function paymentBadgeClass(status?: string) {
  if (status === "paid") return "bg-green-100 text-green-800";
  if (status === "trial") return "bg-sky-100 text-sky-800";
  if (status === "redeem") return "bg-violet-100 text-violet-800";
  if (status === "gift") return "bg-amber-100 text-amber-900";
  return "bg-slate-100 text-slate-600";
}

function StatsPanel({ stats, loading }: { stats: Stats | null; loading: boolean }) {
  const chartData = useMemo(
    () =>
      (stats?.payments_by_day || []).map((d) => ({
        date: d.date.slice(5),
        笔数: d.count,
        金额: d.amount_usd,
      })),
    [stats],
  );

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="card h-24 animate-pulse bg-slate-100" />
        ))}
      </div>
    );
  }
  if (!stats) return <div className="card text-sm text-slate-500">无法加载统计数据</div>;

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        有效会员含试用/赠送/Stripe。「付费成功」按有 stripe_subscription_id 的有效会员统计；金额趋势来自已标记 paid 的
        Checkout/续费记录。另有{" "}
        <span className="font-medium text-slate-700 tabular-nums">{stats.unpaid_intent_count}</span>{" "}
        条未完成支付意向。
        {stats.from_date && stats.to_date ? (
          <span className="tabular-nums">
            {" "}
            · 趋势 {stats.from_date} — {stats.to_date} ET
          </span>
        ) : null}
      </p>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="有效会员" value={stats.active_memberships} tone="green" hint="含试用/赠送/Stripe" />
        <StatCard label="付费成功" value={stats.paid_memberships} tone="blue" hint="Stripe 有效订阅" />
        <StatCard label="赠送会员" value={stats.gift_memberships} tone="amber" hint="无 Stripe 订阅" />
        <StatCard
          label="今日订阅收入"
          value={fmtUsd(stats.today_paid_amount_usd)}
          tone="green"
          hint={stats.today_paid_count > 0 ? `${stats.today_paid_count} 笔` : "ET 日界"}
        />
        <StatCard label="累计订阅收入" value={fmtUsd(stats.total_paid_amount_usd)} hint="已标记 paid 金额合计" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="试用中" value={stats.trial_memberships} hint="status=trialing" />
        <StatCard label="已支付笔数" value={stats.paid_checkout_count} tone="blue" hint="Consent 标记 paid" />
        <StatCard label="待同步" value={stats.pending_sync_count} tone="amber" hint="有 Session 未回写 paid" />
        <StatCard
          label="配置"
          value={stats.stripe_configured && stats.webhook_configured ? "就绪" : "检查配置"}
          tone={stats.stripe_configured && stats.webhook_configured ? "green" : "amber"}
          hint={`Stripe ${stats.stripe_configured ? "已配置" : "未配置"} · Webhook ${stats.webhook_configured ? "已配置" : "未配置"}`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="card">
          <h3 className="mb-2 text-sm font-semibold text-slate-800">近 30 日订阅付费金额</h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={(v) => `$${v}`} />
                <Tooltip formatter={(v: number, name: string) => (name === "金额" ? fmtUsd(v) : v)} />
                <Bar dataKey="金额" fill="#6366f1" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3 className="mb-2 text-sm font-semibold text-slate-800">近 30 日新增付费笔数</h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis yAxisId="left" allowDecimals={false} tick={{ fontSize: 10 }} width={32} />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 10 }}
                  width={44}
                  tickFormatter={(v) => `$${v}`}
                />
                <Tooltip formatter={(v: number, name: string) => (name === "金额" ? fmtUsd(v) : v)} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar yAxisId="left" dataKey="笔数" fill="#0ea5e9" radius={[3, 3, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="金额" stroke="#6366f1" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Payments() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [subs, setSubs] = useState<SubRow[]>([]);
  const [subPage, setSubPage] = useState(1);
  const [subTotal, setSubTotal] = useState(0);
  const [tab, setTab] = useState<Tab>("members");
  const [statsLoading, setStatsLoading] = useState(true);
  const limit = 20;

  const reloadStats = useCallback(() => {
    setStatsLoading(true);
    paymentsApi
      .stats(30)
      .then((r) => setStats(r.data || r))
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, []);

  useEffect(() => {
    reloadStats();
  }, [reloadStats]);

  const loadSubs = useCallback(async () => {
    const r = await subscriptionsApi.list(subPage, limit);
    setSubs(r.items || []);
    setSubTotal(r.total || 0);
  }, [subPage]);

  useEffect(() => {
    loadSubs().catch(() => setSubs([]));
  }, [loadSubs]);

  const subPages = Math.max(1, Math.ceil(subTotal / limit));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader title="支付管理" subtitle="Stripe 订阅、付费状态与收入统计" />
        <GrantSubscriptionPanel
          onGranted={() => {
            reloadStats();
            loadSubs().catch(() => setSubs([]));
          }}
        />
      </div>

      {tab !== "stats" ? (
        statsLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="card h-24 animate-pulse bg-slate-100" />
            ))}
          </div>
        ) : stats ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard label="有效会员" value={stats.active_memberships} tone="green" hint="含试用/赠送/Stripe" />
            <StatCard label="付费成功" value={stats.paid_memberships} tone="blue" hint="Stripe 有效订阅" />
            <StatCard label="累计收入" value={fmtUsd(stats.total_paid_amount_usd)} hint="已标记 paid 合计" />
            <StatCard label="今日收入" value={fmtUsd(stats.today_paid_amount_usd)} tone="green" hint="ET 日界" />
            <StatCard label="待同步" value={stats.pending_sync_count} tone="amber" hint="Checkout 未回写 paid" />
          </div>
        ) : (
          <div className="card text-sm text-slate-500">无法加载支付统计</div>
        )
      ) : null}

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["members", "订阅列表"],
            ["payments", "订阅付费"],
            ["stats", "统计概览"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tab === id ? "btn-primary py-1.5" : "btn-secondary py-1.5"}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "stats" ? (
        <StatsPanel stats={stats} loading={statsLoading} />
      ) : tab === "payments" ? (
        <SubscriptionPaymentsPanel />
      ) : (
        <div className="card overflow-hidden p-0">
          <table className="min-w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3">用户</th>
                <th className="px-4 py-3">套餐</th>
                <th className="px-4 py-3">支付金额</th>
                <th className="px-4 py-3">付费状态</th>
                <th className="px-4 py-3">会员状态</th>
                <th className="px-4 py-3">来源</th>
                <th className="px-4 py-3">Stripe ID</th>
                <th className="px-4 py-3">到期</th>
              </tr>
            </thead>
            <tbody>
              {subs.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <EmptyState />
                  </td>
                </tr>
              ) : (
                subs.map((s) => (
                  <tr key={s.id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <Link to={`/users/${s.user_id}`} className="font-medium text-brand-600 hover:underline">
                        {s.user_email}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      {s.plan_name} <span className="text-slate-400">({s.plan_code})</span>
                    </td>
                    <td className="px-4 py-3 tabular-nums text-slate-800">
                      {s.payment_amount_usd != null && s.payment_amount_usd > 0 ? (
                        <span>
                          {fmtUsd(s.payment_amount_usd)}
                          {s.billing_interval === "yearly" ? (
                            <span className="ml-1 text-xs text-slate-400">/年</span>
                          ) : s.billing_interval === "monthly" ? (
                            <span className="ml-1 text-xs text-slate-400">/月</span>
                          ) : null}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${paymentBadgeClass(s.payment_status)}`}
                      >
                        {s.payment_status_label || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge value={s.status} kind={s.status === "active" ? "active" : "default"} />
                    </td>
                    <td className="px-4 py-3 text-slate-600">{s.source || "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">{s.stripe_subscription_id || "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{s.period_end || "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          <div className="border-t border-slate-200 px-4 py-3">
            <Pagination
              page={subPage}
              totalPages={subPages}
              total={subTotal}
              onPrev={() => setSubPage((p) => p - 1)}
              onNext={() => setSubPage((p) => p + 1)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
