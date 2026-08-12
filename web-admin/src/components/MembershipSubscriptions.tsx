import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { GiftIcon, MagnifyingGlassIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { membershipApi, subscriptionsApi } from "@/api";
import { canWriteAdmin } from "@/lib/adminPermissions";
import { useAuthStore } from "@/store/auth";
import StatusBadge from "@/components/ui/StatusBadge";
import Pagination from "@/components/ui/Pagination";
import EmptyState from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import UserEmailSearchResults from "@/components/UserEmailSearchResults";
import { useDebouncedUserSearch } from "@/hooks/useDebouncedUserSearch";

type Membership = {
  id: string;
  user_id: string;
  user_email: string;
  plan_code: string;
  plan_name: string;
  status: string;
  stripe_subscription_id?: string;
  period_end?: string;
  created_at?: string;
  source?: string;
  redeem_code?: string | null;
};

type StatusFilter = "" | "active" | "canceled";

const STATUS_TABS: { label: string; value: StatusFilter }[] = [
  { label: "全部", value: "" },
  { label: "活跃", value: "active" },
  { label: "已取消", value: "canceled" },
];

export default function MembershipSubscriptions({ embedded = false }: { embedded?: boolean }) {
  const [items, setItems] = useState<Membership[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<StatusFilter>("");
  const [loading, setLoading] = useState(true);
  const [batchOpen, setBatchOpen] = useState(false);
  const [plans, setPlans] = useState<{ code: string; name: string }[]>([]);
  const [planCode, setPlanCode] = useState("pro");
  const [days, setDays] = useState(30);
  const [query, setQuery] = useState("");
  const [selectedUsers, setSelectedUsers] = useState<{ id: string; email: string }[]>([]);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [confirmKind, setConfirmKind] = useState<"cancel" | "reactivate" | null>(null);
  const [extendId, setExtendId] = useState<string | null>(null);
  const [extendDays, setExtendDays] = useState(30);
  const [acting, setActing] = useState(false);
  const role = useAuthStore((s) => s.role);
  const canWrite = canWriteAdmin(role);
  const limit = 20;
  const selectedIds = useMemo(() => new Set(selectedUsers.map((u) => u.id)), [selectedUsers]);
  const userSearch = useDebouncedUserSearch(query, batchOpen);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await subscriptionsApi.list(page, limit, status || undefined);
      setItems(res.items || []);
      setTotal(res.total || 0);
    } finally {
      setLoading(false);
    }
  }, [page, status]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!batchOpen) return;
    membershipApi
      .list()
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setPlans(list.map((p: { code: string; name: string }) => ({ code: p.code, name: p.name })));
      })
      .catch(() => setPlans([]));
  }, [batchOpen]);

  const totalPages = Math.max(1, Math.ceil(total / limit));

  const runConfirm = async () => {
    if (!confirmId || !confirmKind) return;
    setActing(true);
    try {
      if (confirmKind === "cancel") await subscriptionsApi.cancel(confirmId);
      else await subscriptionsApi.reactivate(confirmId);
      setConfirmId(null);
      setConfirmKind(null);
      await load();
    } finally {
      setActing(false);
    }
  };

  const batchGrant = async () => {
    if (selectedUsers.length === 0) return;
    setActing(true);
    try {
      await subscriptionsApi.batchGrant(
        selectedUsers.map((u) => u.id),
        planCode,
        days,
      );
      setBatchOpen(false);
      setSelectedUsers([]);
      setQuery("");
      await load();
    } finally {
      setActing(false);
    }
  };

  const extendSubscription = async () => {
    if (!extendId) return;
    setActing(true);
    try {
      await subscriptionsApi.extend(extendId, extendDays);
      setExtendId(null);
      await load();
    } finally {
      setActing(false);
    }
  };

  return (
    <div className={embedded ? "space-y-4" : "space-y-6"}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        {!embedded ? (
          <div>
            <h2 className="text-lg font-semibold text-slate-900">会员订阅</h2>
            <p className="text-sm text-slate-500">全平台 UserMembership 记录</p>
          </div>
        ) : (
          <p className="text-sm text-slate-500">全平台会员订阅记录，可批量赠送或延期</p>
        )}
        {canWrite && (
          <button type="button" className="btn-primary" onClick={() => setBatchOpen(true)}>
            <GiftIcon className="h-4 w-4" /> 批量赠送
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            className={status === tab.value ? "btn-primary py-1.5" : "btn-secondary py-1.5"}
            onClick={() => {
              setStatus(tab.value);
              setPage(1);
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">用户</th>
              <th className="px-4 py-3">套餐</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">到期</th>
              <th className="px-4 py-3">来源</th>
              <th className="px-4 py-3">Stripe</th>
              {canWrite && <th className="px-4 py-3">操作</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={canWrite ? 7 : 6} className="py-8 text-center text-slate-400">
                  加载中…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={canWrite ? 7 : 6}>
                  <EmptyState />
                </td>
              </tr>
            ) : (
              items.map((m) => (
                <tr key={m.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link to={`/users/${m.user_id}`} className="font-medium text-brand-600 hover:underline">
                      {m.user_email}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    {m.plan_name} <span className="text-slate-400">({m.plan_code})</span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={m.status} kind={m.status === "active" ? "active" : "default"} />
                  </td>
                  <td className="px-4 py-3 text-slate-600">{m.period_end || "—"}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    <div>{m.source || "—"}</div>
                    {m.redeem_code ? (
                      <div className="mt-0.5 font-mono text-[11px] text-slate-400">{m.redeem_code}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{m.stripe_subscription_id || "—"}</td>
                  {canWrite && (
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        {m.status === "active" || m.status === "trialing" ? (
                          <>
                            <button type="button" className="text-brand-600 hover:underline" onClick={() => { setExtendId(m.id); setExtendDays(30); }}>
                              延期
                            </button>
                            <button type="button" className="text-red-600 hover:underline" onClick={() => { setConfirmId(m.id); setConfirmKind("cancel"); }}>
                              取消
                            </button>
                          </>
                        ) : (
                          <button type="button" className="text-brand-600 hover:underline" onClick={() => { setConfirmId(m.id); setConfirmKind("reactivate"); }}>
                            重新激活
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
        <div className="border-t border-slate-200 px-4 py-3">
          <Pagination page={page} totalPages={totalPages} total={total} onPrev={() => setPage((p) => p - 1)} onNext={() => setPage((p) => p + 1)} />
        </div>
      </div>

      <ConfirmDialog
        open={confirmId !== null}
        title={confirmKind === "cancel" ? "取消订阅" : "重新激活订阅"}
        danger={confirmKind === "cancel"}
        loading={acting}
        onClose={() => { setConfirmId(null); setConfirmKind(null); }}
        onConfirm={runConfirm}
      >
        {confirmKind === "cancel" ? "确定将该会员订阅标记为已取消？" : "确定重新激活该会员订阅？"}
      </ConfirmDialog>

      {extendId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setExtendId(null)}>
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold">延长订阅</h3>
            <p className="mt-1 text-xs text-slate-500">在现有到期日基础上顺延天数</p>
            <div className="mt-4">
              <label className="mb-1 block text-xs text-slate-500">延长天数</label>
              <input type="number" className="input w-full" value={extendDays} min={1} onChange={(e) => setExtendDays(Number(e.target.value))} />
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setExtendId(null)}>取消</button>
              <button type="button" className="btn-primary" disabled={acting || extendDays < 1} onClick={extendSubscription}>
                {acting ? "处理中…" : "确认延期"}
              </button>
            </div>
          </div>
        </div>
      )}

      {batchOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setBatchOpen(false)}>
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold">批量赠送订阅</h3>
            <div className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-xs text-slate-500">搜索用户</label>
                <div className="relative">
                  <MagnifyingGlassIcon className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <input
                    className="input w-full pl-9"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="输入邮箱关键词，自动搜索"
                    autoComplete="off"
                  />
                </div>
                <UserEmailSearchResults
                  query={query}
                  hits={userSearch.hits}
                  searching={userSearch.searching}
                  searched={userSearch.searched}
                  error={userSearch.error}
                  canSearch={userSearch.canSearch}
                  minQueryLen={userSearch.minQueryLen}
                  excludeIds={selectedIds}
                  onSelect={(u) => {
                    setSelectedUsers((p) => [...p, { id: u.id, email: u.email }]);
                    setQuery("");
                  }}
                />
              </div>
              {selectedUsers.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {selectedUsers.map((u) => (
                    <span key={u.id} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs">
                      {u.email}
                      <button type="button" onClick={() => setSelectedUsers((p) => p.filter((x) => x.id !== u.id))}>
                        <XMarkIcon className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs text-slate-500">套餐</label>
                  <select className="input w-full" value={planCode} onChange={(e) => setPlanCode(e.target.value)}>
                    {plans.map((p) => (
                      <option key={p.code} value={p.code}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">天数</label>
                  <input type="number" className="input w-full" value={days} onChange={(e) => setDays(Number(e.target.value))} />
                </div>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setBatchOpen(false)}>取消</button>
              <button type="button" className="btn-primary" disabled={acting || selectedUsers.length === 0} onClick={batchGrant}>
                赠送给 {selectedUsers.length} 人
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
