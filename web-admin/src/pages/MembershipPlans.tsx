import { useEffect, useState } from "react";
import { PencilIcon, PlusIcon, TrashIcon } from "@heroicons/react/24/outline";
import { membershipApi } from "@/api";
import { canWriteAdmin } from "@/lib/adminPermissions";
import { PLAN_FEATURE_OPTIONS, PLAN_LIMIT_KEYS } from "@/lib/planFeatures";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuthStore } from "@/store/auth";

type Plan = {
  code: string;
  name: string;
  features: Record<string, unknown>;
  stripe_price_id?: string | null;
  stripe_price_id_monthly?: string | null;
  stripe_price_id_yearly?: string | null;
  price_monthly?: number | null;
  price_yearly?: number | null;
  sort_order?: number;
  is_active?: boolean;
};

const emptyForm = (): Plan => ({
  code: "",
  name: "",
  features: { auto_trade: false, webhook: false, ai_parse: true, max_signal_sources: 1, max_brokers: 1, max_discord_channels: 1, discord_multi_channel: false, multi_agent: false },
  stripe_price_id_monthly: "",
  stripe_price_id_yearly: "",
  price_monthly: null,
  price_yearly: null,
  sort_order: 0,
  is_active: true,
});

function formatUsd(amount: number | null | undefined): string {
  if (amount == null || Number.isNaN(amount)) return "—";
  return `$${amount.toFixed(amount % 1 === 0 ? 0 : 2)}`;
}

function formatDisplayPrice(plan: Plan): string {
  const monthly = plan.price_monthly;
  const yearly = plan.price_yearly;
  if ((monthly == null || monthly <= 0) && (yearly == null || yearly <= 0)) return "—";
  const parts: string[] = [];
  if (monthly != null && monthly > 0) parts.push(`${formatUsd(monthly)}/月`);
  if (yearly != null && yearly > 0) parts.push(`${formatUsd(yearly)}/年`);
  return parts.join(" · ");
}

function formatStripePrice(plan: Plan): string {
  const monthly = plan.stripe_price_id_monthly || plan.stripe_price_id;
  const yearly = plan.stripe_price_id_yearly;
  if (!monthly && !yearly) return "—";
  const parts: string[] = [];
  if (monthly) parts.push(`月 ${monthly}`);
  if (yearly) parts.push(`年 ${yearly}`);
  return parts.join(" · ");
}

export default function MembershipPlans() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<Plan>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [deleteCode, setDeleteCode] = useState<string | null>(null);
  const role = useAuthStore((s) => s.role);
  const canWrite = canWriteAdmin(role);

  const load = () => {
    setLoading(true);
    membershipApi
      .list()
      .then((data) => setPlans(Array.isArray(data) ? data : []))
      .catch(() => setPlans([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setForm(emptyForm());
    setModal(true);
  };

  const openEdit = (p: Plan) => {
    setForm({
      ...p,
      stripe_price_id_monthly: p.stripe_price_id_monthly || p.stripe_price_id || "",
      stripe_price_id_yearly: p.stripe_price_id_yearly || "",
      price_monthly: p.price_monthly ?? null,
      price_yearly: p.price_yearly ?? null,
      is_active: p.is_active !== false,
    });
    setModal(true);
  };

  const save = async () => {
    if (!form.code.trim() || !form.name.trim()) return;
    setSaving(true);
    try {
      await membershipApi.upsert(form.code, {
        code: form.code,
        name: form.name,
        features: form.features,
        stripe_price_id_monthly: form.stripe_price_id_monthly || null,
        stripe_price_id_yearly: form.stripe_price_id_yearly || null,
        price_monthly: form.price_monthly != null ? Number(form.price_monthly) : null,
        price_yearly: form.price_yearly != null ? Number(form.price_yearly) : null,
        sort_order: form.sort_order || 0,
        is_active: form.is_active !== false,
      });
      setModal(false);
      load();
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (p: Plan) => {
    if (!canWrite) return;
    const next = p.is_active === false;
    await membershipApi.upsert(p.code, {
      code: p.code,
      name: p.name,
      features: p.features,
      stripe_price_id_monthly: p.stripe_price_id_monthly || p.stripe_price_id || null,
      stripe_price_id_yearly: p.stripe_price_id_yearly || null,
      price_monthly: p.price_monthly ?? null,
      price_yearly: p.price_yearly ?? null,
      sort_order: p.sort_order || 0,
      is_active: next,
    });
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader title="会员套餐" subtitle="配置展示价格、权益、Stripe Price ID、排序与前台展示（停用后定价页不显示）" />
        {canWrite && (
          <button type="button" className="btn-primary" onClick={openCreate}>
            <PlusIcon className="h-4 w-4" /> 新建套餐
          </button>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">Code</th>
              <th className="px-4 py-3">名称</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">展示价格</th>
              <th className="px-4 py-3">权益摘要</th>
              <th className="px-4 py-3">Stripe Price</th>
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
            ) : plans.length === 0 ? (
              <tr>
                <td colSpan={canWrite ? 7 : 6}>
                  <EmptyState />
                </td>
              </tr>
            ) : (
              plans.map((p) => (
                <tr key={p.code} className={`border-b border-slate-100 hover:bg-slate-50 ${p.is_active === false ? "opacity-60" : ""}`}>
                  <td className="px-4 py-3 font-mono text-xs">{p.code}</td>
                  <td className="px-4 py-3 font-medium">{p.name}</td>
                  <td className="px-4 py-3">
                    {p.is_active === false ? (
                      <StatusBadge value="已停用" kind="inactive" />
                    ) : (
                      <StatusBadge value="展示中" kind="active" />
                    )}
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-800">{formatDisplayPrice(p)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {PLAN_FEATURE_OPTIONS.filter((f) => p.features?.[f.key]).map((f) => (
                        <StatusBadge key={f.key} value={f.label} kind="active" />
                      ))}
                      <span className="text-xs text-slate-500">
                        源×{String(p.features?.max_signal_sources ?? "?")} · 券商×{String(p.features?.max_brokers ?? "?")}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{formatStripePrice(p)}</td>
                  {canWrite && (
                    <td className="px-4 py-3">
                      <button type="button" className="mr-3 text-brand-600 hover:underline" onClick={() => openEdit(p)}>
                        <PencilIcon className="inline h-4 w-4" /> 编辑
                      </button>
                      <button
                        type="button"
                        className={`mr-3 hover:underline ${p.is_active === false ? "text-emerald-600" : "text-amber-600"}`}
                        onClick={() => void toggleActive(p)}
                      >
                        {p.is_active === false ? "启用" : "停用"}
                      </button>
                      {p.code !== "free" && (
                        <button type="button" className="text-red-600 hover:underline" onClick={() => setDeleteCode(p.code)}>
                          <TrashIcon className="inline h-4 w-4" /> 删除
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold">{form.code && plans.some((p) => p.code === form.code) ? "编辑套餐" : "新建套餐"}</h2>
            <div className="mt-4 grid gap-3">
              <input className="input" placeholder="code (free/starter/pro)" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} disabled={form.code === "free" && plans.some((p) => p.code === "free")} />
              <input className="input" placeholder="显示名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_active !== false}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                />
                前台展示（取消勾选 = 停用，定价页不显示）
              </label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">展示价格（月 / USD）</label>
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    className="input w-full"
                    placeholder="如 9"
                    value={form.price_monthly ?? ""}
                    onChange={(e) => setForm({ ...form, price_monthly: e.target.value === "" ? null : Number(e.target.value) })}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">展示价格（年 / USD）</label>
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    className="input w-full"
                    placeholder="如 90"
                    value={form.price_yearly ?? ""}
                    onChange={(e) => setForm({ ...form, price_yearly: e.target.value === "" ? null : Number(e.target.value) })}
                  />
                </div>
              </div>
              <p className="text-xs text-slate-400">前台定价页展示用；实际扣款仍以 Stripe Price ID 为准。</p>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Stripe Price ID（月度）</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="price_xxx_monthly"
                  value={form.stripe_price_id_monthly || ""}
                  onChange={(e) => setForm({ ...form, stripe_price_id_monthly: e.target.value })}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Stripe Price ID（年度）</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="price_xxx_yearly"
                  value={form.stripe_price_id_yearly || ""}
                  onChange={(e) => setForm({ ...form, stripe_price_id_yearly: e.target.value })}
                />
              </div>
              <div>
                <p className="mb-2 text-xs font-medium text-slate-500">功能开关</p>
                <div className="flex flex-wrap gap-3">
                  {PLAN_FEATURE_OPTIONS.map((f) => (
                    <label key={f.key} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={Boolean(form.features[f.key])}
                        onChange={(e) => setForm({ ...form, features: { ...form.features, [f.key]: e.target.checked } })}
                      />
                      {f.label}
                    </label>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {PLAN_LIMIT_KEYS.map((f) => (
                  <div key={f.key}>
                    <label className="mb-1 block text-xs text-slate-500">{f.label}</label>
                    <input
                      type="number"
                      className="input w-full"
                      value={Number(form.features[f.key] ?? 0)}
                      onChange={(e) => setForm({ ...form, features: { ...form.features, [f.key]: Number(e.target.value) } })}
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setModal(false)}>
                取消
              </button>
              <button type="button" className="btn-primary" disabled={saving} onClick={save}>
                {saving ? "保存中…" : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleteCode !== null}
        title="删除套餐"
        danger
        onClose={() => setDeleteCode(null)}
        onConfirm={async () => {
          if (!deleteCode) return;
          await membershipApi.remove(deleteCode);
          setDeleteCode(null);
          load();
        }}
      >
        删除后无法恢复，请确认没有用户正在使用该套餐。
      </ConfirmDialog>
    </div>
  );
}
