import { useCallback, useEffect, useState } from "react";
import { PlusIcon, PencilIcon, TrashIcon } from "@heroicons/react/24/outline";
import { AdminPromotion, membershipApi, promotionsApi } from "@/api";
import { canWriteAdmin } from "@/lib/adminPermissions";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import Pagination from "@/components/ui/Pagination";
import EmptyState from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { AdminToast } from "@/components/ui/AdminToast";
import { useAuthStore } from "@/store/auth";

type Tab = "promotions" | "redemptions";
type PlanOption = { code: string; name: string };

const kindLabel: Record<string, string> = {
  code_public: "公开兑换码",
  code_private: "定向码",
  code_oneoff: "一次性",
  partner_campaign: "合作活动模板",
  signup_bonus: "新人礼",
  referral: "邀请",
};

const kindOptions = Object.keys(kindLabel);

type FormState = {
  name: string;
  kind: string;
  code: string;
  membership_days: number;
  membership_plan_code: string;
  max_uses: string;
  is_active: boolean;
};

const emptyForm = (): FormState => ({
  name: "",
  kind: "code_public",
  code: "",
  membership_days: 7,
  membership_plan_code: "pro",
  max_uses: "",
  is_active: true,
});

export default function Promotions() {
  const [tab, setTab] = useState<Tab>("promotions");
  const [items, setItems] = useState<AdminPromotion[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [plans, setPlans] = useState<PlanOption[]>([]);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [redemptions, setRedemptions] = useState<Record<string, unknown>[]>([]);
  const [redPage, setRedPage] = useState(1);
  const [redTotal, setRedTotal] = useState(0);
  const role = useAuthStore((s) => s.role);
  const canWrite = canWriteAdmin(role);

  const loadPromos = useCallback(() => {
    setLoading(true);
    promotionsApi
      .list()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const loadRedemptions = useCallback(async () => {
    const res = await promotionsApi.redemptions({ page: redPage, limit: 20 });
    setRedemptions(res.items || []);
    setRedTotal(res.total || 0);
  }, [redPage]);

  useEffect(() => {
    if (tab === "promotions") loadPromos();
    else void loadRedemptions();
  }, [tab, loadPromos, loadRedemptions]);

  useEffect(() => {
    if (!modal) return;
    membershipApi
      .list()
      .then((data) => {
        const list = (Array.isArray(data) ? data : [])
          .map((p: PlanOption) => ({ code: p.code, name: p.name || p.code }))
          // 赠送活动不发 free
          .filter((p: PlanOption) => p.code && p.code !== "free");
        setPlans(list);
        setForm((prev) => {
          if (list.some((p: PlanOption) => p.code === prev.membership_plan_code)) return prev;
          const fallback = list.find((p: PlanOption) => p.code === "pro")?.code || list[0]?.code || "pro";
          return { ...prev, membership_plan_code: fallback };
        });
      })
      .catch(() => setPlans([]));
  }, [modal]);

  const openCreate = () => {
    setEditId(null);
    setForm(emptyForm());
    setModal(true);
  };

  const openEdit = (p: AdminPromotion) => {
    setEditId(p.id);
    setForm({
      name: p.name,
      kind: p.kind,
      code: p.code || "",
      membership_days: p.membership_days ?? 7,
      membership_plan_code: p.membership_plan_code || "pro",
      max_uses: p.max_uses ? String(p.max_uses) : "",
      is_active: p.is_active,
    });
    setModal(true);
  };

  const save = async () => {
    const body = {
      name: form.name,
      kind: form.kind,
      code: form.code || undefined,
      reward_kind: "membership_days",
      membership_days: form.membership_days,
      membership_plan_code: form.membership_plan_code,
      max_uses: form.max_uses ? Number(form.max_uses) : undefined,
      is_active: form.is_active,
      amount_usd: 0,
    };
    try {
      if (editId) await promotionsApi.update(editId, body);
      else await promotionsApi.create(body);
      setModal(false);
      setToast({ message: editId ? "已更新" : "已创建", type: "success" });
      loadPromos();
    } catch {
      setToast({ message: "保存失败", type: "error" });
    }
  };

  const toggleActive = async (p: AdminPromotion) => {
    await promotionsApi.update(p.id, { is_active: !p.is_active });
    loadPromos();
  };

  const remove = async () => {
    if (!deleteId) return;
    try {
      await promotionsApi.remove(deleteId);
      setDeleteId(null);
      setToast({ message: "已删除", type: "success" });
      loadPromos();
    } catch {
      setToast({ message: "删除失败（可能已有核销记录）", type: "error" });
      setDeleteId(null);
    }
  };

  const redPages = Math.max(1, Math.ceil(redTotal / 20));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader title="活动 / 兑换码" subtitle="会员天数兑换与核销审计" />
        {canWrite && tab === "promotions" && (
          <button type="button" className="btn-primary" onClick={openCreate}>
            <PlusIcon className="h-4 w-4" /> 创建活动
          </button>
        )}
      </div>

      <div className="flex gap-2 border-b border-slate-200 pb-2">
        <button type="button" className={tab === "promotions" ? "border-b-2 border-brand-600 pb-2 text-sm font-medium text-brand-700" : "pb-2 text-sm text-slate-600"} onClick={() => setTab("promotions")}>
          活动列表
        </button>
        <button type="button" className={tab === "redemptions" ? "border-b-2 border-brand-600 pb-2 text-sm font-medium text-brand-700" : "pb-2 text-sm text-slate-600"} onClick={() => setTab("redemptions")}>
          核销记录
        </button>
      </div>

      {tab === "promotions" ? (
        <div className="card overflow-hidden p-0">
          <table className="min-w-full text-sm">
            <thead className="border-b bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3">名称</th>
                <th className="px-4 py-3">类型</th>
                <th className="px-4 py-3">兑换码</th>
                <th className="px-4 py-3">奖励</th>
                <th className="px-4 py-3">使用</th>
                <th className="px-4 py-3">状态</th>
                {canWrite && <th className="px-4 py-3">操作</th>}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="py-8 text-center text-slate-400">加载中…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={7}><EmptyState /></td></tr>
              ) : (
                items.map((p) => (
                  <tr key={p.id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium">{p.name}</td>
                    <td className="px-4 py-3"><StatusBadge value={kindLabel[p.kind] || p.kind} /></td>
                    <td className="px-4 py-3 font-mono text-xs">{p.code || "—"}</td>
                    <td className="px-4 py-3">
                      {p.membership_period_end
                        ? `至 ${p.membership_period_end.slice(0, 10)} · ${p.membership_plan_code || "—"}`
                        : `${p.membership_days ?? 0} 天 · ${p.membership_plan_code || "—"}`}
                    </td>
                    <td className="px-4 py-3 tabular-nums">{p.current_uses ?? 0}{p.max_uses ? ` / ${p.max_uses}` : ""}</td>
                    <td className="px-4 py-3">
                      <StatusBadge value={p.is_active ? "启用" : "停用"} kind={p.is_active ? "active" : "offline"} />
                    </td>
                    {canWrite && (
                      <td className="px-4 py-3 whitespace-nowrap">
                        <button type="button" className="mr-2 text-brand-600 hover:underline" onClick={() => openEdit(p)}><PencilIcon className="inline h-4 w-4" /></button>
                        <button type="button" className="mr-2 text-slate-600 hover:underline" onClick={() => toggleActive(p)}>{p.is_active ? "停用" : "启用"}</button>
                        <button type="button" className="text-red-600 hover:underline" onClick={() => setDeleteId(p.id)}><TrashIcon className="inline h-4 w-4" /></button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <div className="card overflow-hidden p-0">
            <table className="min-w-full text-sm">
              <thead className="border-b bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-4 py-3">时间</th>
                  <th className="px-4 py-3">用户</th>
                  <th className="px-4 py-3">活动</th>
                  <th className="px-4 py-3">兑换码</th>
                  <th className="px-4 py-3">权益</th>
                  <th className="px-4 py-3">类型</th>
                </tr>
              </thead>
              <tbody>
                {redemptions.length === 0 ? (
                  <tr><td colSpan={6}><EmptyState message="暂无核销记录" /></td></tr>
                ) : (
                  redemptions.map((r) => (
                    <tr key={String(r.id)} className="border-b border-slate-100">
                      <td className="px-4 py-3 text-slate-600">{String(r.created_at || "—")}</td>
                      <td className="px-4 py-3">{String(r.user_email || "—")}</td>
                      <td className="px-4 py-3">{String(r.promotion_name || "—")}</td>
                      <td className="px-4 py-3 font-mono text-xs">{String(r.promotion_code || "—")}</td>
                      <td className="px-4 py-3 text-slate-600">
                        {String(r.plan_code || "—")} · {String(r.membership_days ?? "—")} 天
                      </td>
                      <td className="px-4 py-3">{kindLabel[String(r.promotion_kind)] || String(r.promotion_kind)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <Pagination page={redPage} totalPages={redPages} total={redTotal} onPrev={() => setRedPage((p) => p - 1)} onNext={() => setRedPage((p) => p + 1)} />
        </>
      )}

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold">{editId ? "编辑活动" : "创建活动"}</h2>
            <div className="mt-4 grid gap-3">
              <input className="input" placeholder="活动名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} disabled={!!editId}>
                {kindOptions.map((k) => (
                  <option key={k} value={k}>{kindLabel[k]}</option>
                ))}
              </select>
              <input
                className="input font-mono"
                placeholder={form.kind === "partner_campaign" ? "campaign_key（如 sunnyquant_pro_gift）" : "兑换码（code 类型必填）"}
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
              />
              <div className="grid grid-cols-2 gap-2">
                <input type="number" className="input" placeholder="会员天数" value={form.membership_days} onChange={(e) => setForm({ ...form, membership_days: Number(e.target.value) })} />
                <select
                  className="input"
                  value={form.membership_plan_code}
                  onChange={(e) => setForm({ ...form, membership_plan_code: e.target.value })}
                >
                  {plans.length === 0 ? (
                    <option value={form.membership_plan_code || "pro"}>{form.membership_plan_code || "pro"}</option>
                  ) : (
                    plans.map((p) => (
                      <option key={p.code} value={p.code}>
                        {p.name} ({p.code})
                      </option>
                    ))
                  )}
                </select>
              </div>
              <input className="input" placeholder="最大使用次数（留空不限）" value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                启用
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setModal(false)}>取消</button>
              <button type="button" className="btn-primary" onClick={save}>保存</button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog open={deleteId !== null} title="删除活动" danger onClose={() => setDeleteId(null)} onConfirm={remove}>
        无核销记录的活动可删除；否则请改用停用。
      </ConfirmDialog>

      {toast ? <AdminToast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} /> : null}
    </div>
  );
}
