import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { usersApi } from "@/api";
import { canManageUserStatus, canWriteAdmin } from "@/lib/adminPermissions";
import { useAuthStore } from "@/store/auth";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import Pagination from "@/components/ui/Pagination";
import EmptyState from "@/components/ui/EmptyState";
import MembershipSubscriptions from "@/components/MembershipSubscriptions";
import GrantSubscriptionPanel from "@/components/GrantSubscriptionPanel";
import { Pie, PieChart, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { GeoCell, GeoSnapshot, languageDisplay, regionLabelZh } from "@/lib/geoDisplay";

const COLORS = ["#4f46e5", "#16a34a", "#f59e0b", "#ec4899", "#06b6d4", "#64748b"];

type MembershipSummary = {
  id: string;
  plan_code: string;
  plan_name: string;
  status: string;
  period_end?: string;
};

type UserRow = {
  id: string;
  email: string;
  display_name?: string;
  language?: string | null;
  kill_switch: boolean;
  is_banned?: boolean;
  email_verified: boolean;
  auth_provider?: string;
  created_at: string;
  registration_geo?: GeoSnapshot | null;
  last_login_geo?: GeoSnapshot | null;
  membership?: MembershipSummary;
};

type Tab = "users" | "memberships" | "geo";

function membershipStatusKind(status: string) {
  if (status === "active" || status === "trialing") return "active" as const;
  if (status === "canceled" || status === "expired") return "default" as const;
  return "pending" as const;
}

export default function Users() {
  const [tab, setTab] = useState<Tab>("users");
  const [items, setItems] = useState<UserRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [grantUser, setGrantUser] = useState<{ id: string; email: string } | null>(null);
  const [geo, setGeo] = useState<{ total_users: number; by_country: { country_code: string | null; count: number }[] } | null>(null);
  const role = useAuthStore((s) => s.role);
  const canWrite = canWriteAdmin(role);
  const limit = 20;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await usersApi.list(page, limit, search || undefined);
      setItems(res.items || []);
      setTotal(res.total || 0);
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    if (tab === "users") void load();
  }, [load, tab]);

  useEffect(() => {
    if (tab === "geo") {
      usersApi.geoDistribution().then(setGeo).catch(() => setGeo(null));
    }
  }, [tab]);

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const chartData = (geo?.by_country || []).slice(0, 10).map((row) => ({
    name: row.country_code ? regionLabelZh(row.country_code) : "未知",
    value: row.count,
  }));

  return (
    <div className="space-y-6">
      <PageHeader title="用户管理" subtitle={`共 ${geo?.total_users ?? total} 位用户`} />

      <div className="flex gap-2 border-b border-slate-200 pb-2">
        {[
          { id: "users" as const, label: "用户列表" },
          { id: "memberships" as const, label: "会员订阅" },
          { id: "geo" as const, label: "地区分布" },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={tab === t.id ? "border-b-2 border-brand-600 pb-2 text-sm font-medium text-brand-700" : "pb-2 text-sm text-slate-600 hover:text-slate-900"}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setPage(1);
                setSearch(q.trim());
              }}
            >
              <input className="input max-w-md" placeholder="搜索邮箱" value={q} onChange={(e) => setQ(e.target.value)} />
              <button type="submit" className="btn-secondary">搜索</button>
            </form>
            {canWrite && <GrantSubscriptionPanel onGranted={load} />}
          </div>

          <div className="card overflow-x-auto p-0">
            <table className="min-w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-4 py-3">用户</th>
                  <th className="px-4 py-3">注册地</th>
                  <th className="px-4 py-3">最近登录地</th>
                  <th className="px-4 py-3">会员套餐</th>
                  <th className="px-4 py-3">订阅状态</th>
                  <th className="px-4 py-3">到期</th>
                  <th className="px-4 py-3">注册时间</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9} className="px-4 py-8 text-center text-slate-400">加载中…</td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={9}><EmptyState /></td></tr>
                ) : (
                  items.map((u) => {
                    const lang = languageDisplay(u.language);
                    return (
                    <tr key={u.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3 align-top">
                        <div className="font-medium text-slate-900">{u.email}</div>
                        {u.display_name ? <div className="text-xs text-slate-500">{u.display_name}</div> : null}
                        <div className="mt-1 text-xs text-slate-500">
                          语言：<span className="font-medium text-slate-700">{lang.label}</span>
                          <span className="ml-1">{lang.flag}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <GeoCell geo={u.registration_geo} />
                      </td>
                      <td className="px-4 py-3 align-top">
                        <GeoCell geo={u.last_login_geo} />
                      </td>
                      <td className="px-4 py-3 align-top">
                        {u.membership ? (
                          <div>
                            <div className="font-medium">{u.membership.plan_name}</div>
                            <div className="font-mono text-xs text-slate-400">{u.membership.plan_code}</div>
                          </div>
                        ) : (
                          <span className="text-slate-400">免费</span>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top">
                        {u.membership ? (
                          <StatusBadge value={u.membership.status} kind={membershipStatusKind(u.membership.status)} />
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 align-top text-slate-600">{u.membership?.period_end || "—"}</td>
                      <td className="px-4 py-3 align-top text-slate-600">{u.created_at}</td>
                      <td className="px-4 py-3 align-top">
                        <div className="flex flex-wrap gap-1">
                          {u.is_banned ? <StatusBadge value="封禁" kind="banned" /> : null}
                          {u.kill_switch ? <StatusBadge value="急停" kind="pending" /> : null}
                          {u.email_verified ? <StatusBadge value="已验证" kind="active" /> : null}
                        </div>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <div className="flex flex-wrap items-center gap-2">
                          <Link to={`/users/${u.id}`} className="text-brand-600 hover:underline">详情</Link>
                          {canWrite && (
                            <button type="button" className="text-brand-600 hover:underline" onClick={() => setGrantUser({ id: u.id, email: u.email })}>
                              赠送
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <Pagination page={page} totalPages={totalPages} total={total} onPrev={() => setPage((p) => p - 1)} onNext={() => setPage((p) => p + 1)} />
          {!canManageUserStatus(role) && <p className="text-xs text-slate-400">当前为运营只读账号。</p>}

          {grantUser && (
            <GrantSubscriptionPanel
              hideTrigger
              open
              defaultUser={grantUser}
              onClose={() => setGrantUser(null)}
              onGranted={() => {
                setGrantUser(null);
                void load();
              }}
            />
          )}
        </>
      )}

      {tab === "memberships" && <MembershipSubscriptions embedded />}

      {tab === "geo" && (
        <div className="card">
          <h3 className="mb-4 text-lg font-semibold">注册/登录地区 Top 10</h3>
          <p className="mb-4 text-xs text-slate-500">
            优先按注册时解析的国家统计；注册地未识别时回退到最近登录地。
          </p>
          {!geo ? (
            <p className="text-slate-500">加载中…</p>
          ) : chartData.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label>
                    {chartData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-4 text-xs text-slate-500">
            完整趋势与表格请查看 <Link to="/users/analytics" className="text-brand-600 hover:underline">用户数据</Link>
          </p>
        </div>
      )}
    </div>
  );
}
