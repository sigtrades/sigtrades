import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { analyticsApi } from "@/api";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import EmptyState from "@/components/ui/EmptyState";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const DAY_OPTIONS = [
  { value: 7, label: "7 天" },
  { value: 30, label: "30 天" },
  { value: 90, label: "90 天" },
];

export default function UsersAnalytics() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<{
    from_date?: string;
    to_date?: string;
    registrations_by_day: { date: string; count: number }[];
    dau_by_day: { date: string; count: number }[];
    cumulative_users_by_day: { date: string; count: number }[];
  } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await analyticsApi.userTrends(days);
      setData(res);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const tableRows = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, { date: string; reg: number; dau: number; cum: number }>();
    for (const r of data.registrations_by_day || []) map.set(r.date, { date: r.date, reg: r.count, dau: 0, cum: 0 });
    for (const r of data.dau_by_day || []) {
      const row = map.get(r.date) || { date: r.date, reg: 0, dau: 0, cum: 0 };
      row.dau = r.count;
      map.set(r.date, row);
    }
    for (const r of data.cumulative_users_by_day || []) {
      const row = map.get(r.date) || { date: r.date, reg: 0, dau: 0, cum: 0 };
      row.cum = r.count;
      map.set(r.date, row);
    }
    return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [data]);

  const chartData = tableRows.map((r) => ({
    date: r.date.slice(5),
    新增注册: r.reg,
    登录DAU: r.dau,
    累计用户: r.cum,
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader title="用户数据" subtitle="注册与登录趋势（美东日界）" />
        <div className="flex gap-2">
          {DAY_OPTIONS.map((opt) => (
            <button key={opt.value} type="button" className={days === opt.value ? "btn-primary py-1.5" : "btn-secondary py-1.5"} onClick={() => setDays(opt.value)}>
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {data?.from_date && data.to_date ? (
        <p className="text-xs text-slate-500">统计区间 {data.from_date} — {data.to_date} ET</p>
      ) : null}

      {loading ? (
        <div className="card h-64 animate-pulse bg-slate-100" />
      ) : !data ? (
        <div className="card text-red-600">加载失败</div>
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="card">
              <h3 className="mb-3 font-semibold">新增注册</h3>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Bar dataKey="新增注册" fill="#4f46e5" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="card">
              <h3 className="mb-3 font-semibold">登录 DAU</h3>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="登录DAU" stroke="#16a34a" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="card overflow-hidden p-0">
            <div className="border-b px-4 py-3 text-sm font-semibold">每日明细</div>
            <table className="min-w-full text-sm">
              <thead className="border-b bg-slate-50 text-left text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">日期</th>
                  <th className="px-4 py-3 text-right">新增</th>
                  <th className="px-4 py-3 text-right">DAU</th>
                  <th className="px-4 py-3 text-right">累计用户</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.length === 0 ? (
                  <tr><td colSpan={4}><EmptyState /></td></tr>
                ) : (
                  tableRows.map((r) => (
                    <tr key={r.date} className="border-b border-slate-100">
                      <td className="px-4 py-3">{r.date}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.reg}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.dau}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{r.cum}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-slate-500">
            地区分布见 <Link to="/users" className="text-brand-600 hover:underline">用户管理 → 地区分布</Link>
          </p>
        </>
      )}
    </div>
  );
}
