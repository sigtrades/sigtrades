import { useEffect, useState } from "react";
import { GiftIcon } from "@heroicons/react/24/outline";
import { membershipApi, subscriptionsApi } from "@/api";
import { canWriteAdmin } from "@/lib/adminPermissions";
import { useAuthStore } from "@/store/auth";
import UserEmailSearchResults from "@/components/UserEmailSearchResults";
import { useDebouncedUserSearch } from "@/hooks/useDebouncedUserSearch";

type Plan = { code: string; name: string };
type UserHit = { id: string; email: string };

export default function GrantSubscriptionPanel({
  onGranted,
  defaultUser,
  open: controlledOpen,
  onClose,
  hideTrigger = false,
}: {
  onGranted?: () => void;
  defaultUser?: UserHit | null;
  open?: boolean;
  onClose?: () => void;
  hideTrigger?: boolean;
}) {
  const role = useAuthStore((s) => s.role);
  const canWrite = canWriteAdmin(role);
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = (next: boolean) => {
    if (controlledOpen === undefined) setInternalOpen(next);
    if (!next) onClose?.();
  };
  const [plans, setPlans] = useState<Plan[]>([]);
  const [planCode, setPlanCode] = useState("pro");
  const [days, setDays] = useState<number | "">(30);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<UserHit | null>(defaultUser ?? null);
  const userSearch = useDebouncedUserSearch(query, open && !defaultUser && !selected);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    if (defaultUser) setSelected(defaultUser);
  }, [defaultUser]);

  useEffect(() => {
    if (!open) return;
    membershipApi
      .list()
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setPlans(list.map((p: Plan) => ({ code: p.code, name: p.name })));
        if (list.length > 0 && !list.some((p: Plan) => p.code === planCode)) {
          setPlanCode(list[0].code);
        }
      })
      .catch(() => setPlans([]));
  }, [open, planCode]);

  const grant = async () => {
    if (!selected) {
      setErr("请选择用户");
      return;
    }
    setSaving(true);
    setErr("");
    setMsg("");
    try {
      await subscriptionsApi.grant(selected.id, planCode, typeof days === "number" ? days : undefined);
      setMsg(`已为 ${selected.email} 开通 ${planCode}`);
      if (!defaultUser) {
        setSelected(null);
        setQuery("");
      }
      onGranted?.();
      if (controlledOpen === undefined) setOpen(false);
    } catch {
      setErr("开通失败，请确认用户与套餐有效");
    } finally {
      setSaving(false);
    }
  };

  if (!canWrite) return null;

  return (
    <>
      {!hideTrigger && (
        <button type="button" className="btn-secondary" onClick={() => setOpen(true)}>
          <GiftIcon className="h-4 w-4" /> 赠送订阅
        </button>
      )}

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setOpen(false)}>
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold">后台赠送订阅</h2>
            <p className="mt-1 text-xs text-slate-500">为指定用户创建 active 会员记录（不含 Stripe 扣费）</p>

            <div className="mt-4 grid gap-3">
              {!defaultUser ? (
                <div>
                  <label className="mb-1 block text-xs text-slate-500">搜索用户邮箱</label>
                  <input
                    className="input w-full"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="输入邮箱关键词，自动搜索"
                    autoComplete="off"
                    disabled={!!selected}
                  />
                  {!selected ? (
                    <UserEmailSearchResults
                      query={query}
                      hits={userSearch.hits}
                      searching={userSearch.searching}
                      searched={userSearch.searched}
                      error={userSearch.error}
                      canSearch={userSearch.canSearch}
                      minQueryLen={userSearch.minQueryLen}
                      onSelect={(u) => {
                        setSelected({ id: u.id, email: u.email });
                        setQuery("");
                      }}
                    />
                  ) : null}
                  {selected ? (
                    <div className="mt-2 flex items-center justify-between rounded-lg bg-brand-50 px-3 py-2 text-sm">
                      <span>{selected.email}</span>
                      <button type="button" className="text-xs text-brand-600 hover:underline" onClick={() => setSelected(null)}>
                        更换
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                  用户：<span className="font-medium">{defaultUser.email}</span>
                </div>
              )}

              <div>
                <label className="mb-1 block text-xs text-slate-500">有效天数（可选）</label>
                <input type="number" className="input w-full" value={days} onChange={(e) => setDays(e.target.value ? Number(e.target.value) : "")} placeholder="留空表示无到期" />
              </div>

              <div>
                <label className="mb-1 block text-xs text-slate-500">套餐</label>
                <select className="input w-full" value={planCode} onChange={(e) => setPlanCode(e.target.value)}>
                  {plans.map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.name} ({p.code})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {msg ? <p className="mt-3 text-sm text-green-700">{msg}</p> : null}
            {err ? <p className="mt-3 text-sm text-red-600">{err}</p> : null}

            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>
                关闭
              </button>
              <button type="button" className="btn-primary" disabled={saving || !selected} onClick={grant}>
                {saving ? "处理中…" : "确认赠送"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
