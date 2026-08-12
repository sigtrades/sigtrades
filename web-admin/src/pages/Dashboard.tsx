import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { analyticsApi } from "@/api";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Overview = {
  current_time_et?: string;
  total_users: number;
  banned_users: number;
  kill_switch_users: number;
  active_memberships: number;
  agents_online: number;
  executions_today: number;
  new_users_7d: number;
  new_users_today: number;
  payment_consents: number;
  paid_memberships?: number;
  gift_memberships?: number;
  trial_memberships?: number;
  paid_checkout_count?: number;
  total_paid_amount_usd?: number;
  today_paid_count?: number;
  today_paid_amount_usd?: number;
  payments_by_day?: { date: string; count: number; amount_usd: number }[];
};

function fmtUsd(n: number) {
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function Dashboard() {
  const [data, setData] = useState<Overview | null>(null);
  const [trend, setTrend] = useState<{ date: string; count: number }[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      analyticsApi.overview().then((res) => (res.success === false ? null : res.data || res)),
      analyticsApi.userTrends(14).then((t) => t.registrations_by_day || []),
    ])
      .then(([overview, regTrend]) => {
        if (!overview) setError("加载失败");
        else setData(overview as Overview);
        setTrend(regTrend);
      })
      .catch(() => setError("无法连接 API"))
      .finally(() => setLoading(false));
  }, []);

  const payChart = useMemo(
    () =>
      (data?.payments_by_day || []).map((d) => ({
        date: d.date.slice(5),
        金额: d.amount_usd,
        笔数: d.count,
      })),
    [data],
  );

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-9 w-40 animate-pulse rounded bg-slate-200" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div key={i} className="card h-24 animate-pulse bg-slate-100" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <PageHeader title="仪表盘" subtitle="SigTrades 运营概览" />
        <div className="card border-red-200 bg-red-50 text-sm text-red-700">{error || "无数据"}</div>
      </div>
    );
  }

  const chartData = [
    { name: "用户", value: data.total_users },
    { name: "活跃订阅", value: data.active_memberships },
    { name: "付费会员", value: data.paid_memberships ?? 0 },
    { name: "Agent在线", value: data.agents_online },
  ];

  const regChart = trend.map((d) => ({ date: d.date.slice(5), count: d.count }));

  return (
    <div className="space-y-6">
      <PageHeader title="仪表盘" subtitle={data.current_time_et ? `当前 ${data.current_time_et}` : "SigTrades 运营概览 · ET 时区"} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <LinkCard label="总用户" value={data.total_users} href="/users" tone="blue" />
        <LinkCard label="今日新增" value={data.new_users_today} href="/users/analytics" />
        <LinkCard label="7日新增" value={data.new_users_7d} href="/users/analytics" />
        <LinkCard label="活跃订阅" value={data.active_memberships} href="/payments" tone="green" />
        <LinkCard label="Agent 在线" value={data.agents_online} href="/agents" tone="green" />
        <LinkCard label="今日执行" value={data.executions_today} href="/executions" />
        <StatCard label="急停用户" value={data.kill_switch_users} tone={data.kill_switch_users > 0 ? "amber" : "default"} />
        <StatCard label="封禁用户" value={data.banned_users} tone={data.banned_users > 0 ? "red" : "default"} />
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-800">付费数据</h2>
          <Link to="/payments" className="text-xs font-medium text-brand-600 hover:underline">
            支付管理 →
          </Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Link to="/payments" className="block transition hover:opacity-90">
            <StatCard label="付费会员" value={data.paid_memberships ?? 0} tone="blue" hint="Stripe 有效订阅" />
          </Link>
          <Link to="/payments" className="block transition hover:opacity-90">
            <StatCard label="赠送/试用" value={(data.gift_memberships ?? 0) + (data.trial_memberships ?? 0)} tone="amber" hint="非 Stripe 付费" />
          </Link>
          <Link to="/payments" className="block transition hover:opacity-90">
            <StatCard
              label="今日收入"
              value={fmtUsd(data.today_paid_amount_usd ?? 0)}
              tone="green"
              hint={data.today_paid_count ? `${data.today_paid_count} 笔 · ET` : "ET 日界"}
            />
          </Link>
          <Link to="/payments" className="block transition hover:opacity-90">
            <StatCard
              label="累计收入"
              value={fmtUsd(data.total_paid_amount_usd ?? 0)}
              hint={`已支付 ${data.paid_checkout_count ?? 0} 笔`}
            />
          </Link>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="card">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">近 14 日新增注册</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={regChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="count" name="新增" fill="#4f46e5" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">近 14 日订阅收入</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={payChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  formatter={(v: number, name: string) => (name === "金额" ? fmtUsd(v) : v)}
                />
                <Bar dataKey="金额" fill="#16a34a" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">关键指标对比</h2>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="value" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function LinkCard({
  label,
  value,
  href,
  tone = "default",
}: {
  label: string;
  value: number;
  href: string;
  tone?: "default" | "green" | "blue";
}) {
  return (
    <Link to={href} className="block transition hover:opacity-90">
      <StatCard label={label} value={value} tone={tone} />
    </Link>
  );
}
