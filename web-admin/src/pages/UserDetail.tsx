import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { subscriptionsApi, usersApi } from "@/api";
import { canManageUserStatus } from "@/lib/adminPermissions";
import { useAuthStore } from "@/store/auth";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import PipelineTab from "@/pages/user-detail/PipelineTab";
import BrokersTab from "@/pages/user-detail/BrokersTab";
import AgentsTab from "@/pages/user-detail/AgentsTab";
import ExecutionsTab from "@/pages/user-detail/ExecutionsTab";
import RiskDisclosureTab from "@/pages/user-detail/RiskDisclosureTab";
import GrantSubscriptionPanel from "@/components/GrantSubscriptionPanel";
import { GeoCell, GeoSnapshot, languageDisplay } from "@/lib/geoDisplay";

type Tab = "overview" | "pipeline" | "brokers" | "agents" | "executions" | "risk";

type MembershipRow = {
  id: string;
  plan_code?: string;
  plan_name?: string;
  status: string;
  period_end?: string;
  stripe_subscription_id?: string;
  created_at?: string;
};

export default function UserDetail() {
  const { userId = "" } = useParams();
  const [tab, setTab] = useState<Tab>("overview");
  const [user, setUser] = useState<Record<string, unknown> | null>(null);
  const [pipeline, setPipeline] = useState<Record<string, unknown> | null>(null);
  const [brokers, setBrokers] = useState<Record<string, unknown> | null>(null);
  const [agents, setAgents] = useState<Record<string, unknown> | null>(null);
  const [executions, setExecutions] = useState<Record<string, unknown>[] | null>(null);
  const [riskDisclosures, setRiskDisclosures] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState("");
  const [banNote, setBanNote] = useState("");
  const [extendId, setExtendId] = useState<string | null>(null);
  const [extendDays, setExtendDays] = useState(30);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [confirmKind, setConfirmKind] = useState<"cancel" | "reactivate" | null>(null);
  const [acting, setActing] = useState(false);
  const role = useAuthStore((s) => s.role);
  const canWrite = canManageUserStatus(role);

  const reloadUser = async () => {
    if (!userId) return;
    setUser(await usersApi.get(userId));
  };

  useEffect(() => {
    if (!userId) return;
    usersApi.get(userId).then(setUser).catch(() => setUser(null));
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    if (tab === "pipeline") usersApi.pipeline(userId).then(setPipeline).catch(() => setPipeline(null));
    if (tab === "brokers") usersApi.brokers(userId).then(setBrokers).catch(() => setBrokers(null));
    if (tab === "agents") usersApi.agents(userId).then(setAgents).catch(() => setAgents(null));
    if (tab === "executions")
      usersApi
        .executions(userId)
        .then((r) => setExecutions(Array.isArray(r) ? r : []))
        .catch(() => setExecutions([]));
    if (tab === "risk")
      usersApi.riskDisclosures(userId).then(setRiskDisclosures).catch(() => setRiskDisclosures(null));
  }, [userId, tab]);

  const memberships = (Array.isArray(user?.memberships) ? user.memberships : []) as MembershipRow[];

  const runMembershipAction = async () => {
    if (!confirmId || !confirmKind) return;
    setActing(true);
    try {
      if (confirmKind === "cancel") await subscriptionsApi.cancel(confirmId);
      else await subscriptionsApi.reactivate(confirmId);
      setConfirmId(null);
      setConfirmKind(null);
      setMsg(confirmKind === "cancel" ? "已取消订阅" : "已重新激活订阅");
      await reloadUser();
    } finally {
      setActing(false);
    }
  };

  const extendMembership = async () => {
    if (!extendId) return;
    setActing(true);
    try {
      await subscriptionsApi.extend(extendId, extendDays);
      setExtendId(null);
      setMsg(`已延长 ${extendDays} 天`);
      await reloadUser();
    } finally {
      setActing(false);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "概览" },
    { id: "pipeline", label: "信号源/规则" },
    { id: "brokers", label: "券商" },
    { id: "agents", label: "Agent" },
    { id: "executions", label: "执行" },
    { id: "risk", label: "风险揭示" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/users" className="text-sm text-brand-600 hover:underline">
            ← 返回用户列表
          </Link>
          <PageHeader title={String(user?.email || "用户详情")} subtitle={userId} />
        </div>
        {user && (
          <div className="flex flex-wrap gap-2">
            {user.is_banned ? <StatusBadge value="已封禁" kind="banned" /> : null}
            {user.kill_switch ? <StatusBadge value="急停中" kind="pending" /> : null}
            {user.email_verified ? <StatusBadge value="邮箱已验证" kind="active" /> : null}
          </div>
        )}
      </div>

      {msg ? <div className="rounded-lg bg-green-50 px-4 py-2 text-sm text-green-700">{msg}</div> : null}

      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {tabs.map((t) => (
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

      {tab === "overview" && user && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card grid gap-3 text-sm sm:grid-cols-2">
            <Field label="邮箱" value={String(user.email)} />
            <Field label="显示名" value={String(user.display_name || "—")} />
            <Field
              label="语言"
              value={(() => {
                const lang = languageDisplay(String(user.language || "zh"));
                return `${lang.label} ${lang.flag}`;
              })()}
            />
            <Field label="注册时间" value={String(user.created_at)} />
            <Field label="认证方式" value={String(user.auth_provider || "—")} />
            <div>
              <div className="text-xs text-slate-500">注册地</div>
              <div className="mt-0.5"><GeoCell geo={user.registration_geo as GeoSnapshot | null} /></div>
            </div>
            <div>
              <div className="text-xs text-slate-500">最近登录地</div>
              <div className="mt-0.5"><GeoCell geo={user.last_login_geo as GeoSnapshot | null} /></div>
            </div>
            <Field label="急停" value={user.kill_switch ? "是" : "否"} />
            {Boolean(user.admin_note) ? (
              <div className="sm:col-span-2">
                <Field label="运营备注" value={String(user.admin_note)} />
              </div>
            ) : null}
          </div>
          {canWrite && (
            <div className="card space-y-3">
              <h3 className="text-sm font-semibold">运营操作</h3>
              <textarea className="textarea text-sm" rows={2} placeholder="封禁备注（可选）" value={banNote} onChange={(e) => setBanNote(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn-danger" onClick={() => usersApi.ban(userId, !user.is_banned, banNote || undefined).then(async () => { setMsg("已更新封禁"); await reloadUser(); })}>
                  {user.is_banned ? "解除封禁" : "封禁用户"}
                </button>
                <button type="button" className="btn-secondary" onClick={() => usersApi.killSwitch(userId, !user.kill_switch).then(async () => { setMsg("已更新急停"); await reloadUser(); })}>
                  {user.kill_switch ? "关闭急停" : "开启急停"}
                </button>
                <button type="button" className="btn-secondary" onClick={() => usersApi.revokeTokens(userId).then(() => setMsg("已撤销 tokens"))}>
                  撤销登录/Agent Token
                </button>
                <GrantSubscriptionPanel
                  defaultUser={{ id: userId, email: String(user.email) }}
                  onGranted={async () => {
                    setMsg("已赠送订阅");
                    await reloadUser();
                  }}
                />
              </div>
            </div>
          )}
          <div className="card lg:col-span-2">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">会员订阅</h3>
              {memberships.length > 0 && (
                <span className="text-xs text-slate-500">共 {memberships.length} 条记录</span>
              )}
            </div>
            {memberships.length === 0 ? (
              <p className="text-sm text-slate-500">暂无订阅记录，可通过上方「赠送订阅」开通会员。</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left text-xs text-slate-500">
                    <tr>
                      <th className="pb-2 pr-4">套餐</th>
                      <th className="pb-2 pr-4">状态</th>
                      <th className="pb-2 pr-4">到期</th>
                      <th className="pb-2 pr-4">Stripe</th>
                      {canWrite && <th className="pb-2">操作</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {memberships.map((m) => (
                      <tr key={m.id} className="border-t border-slate-100">
                        <td className="py-2 pr-4">
                          <div className="font-medium">{m.plan_name || m.plan_code || "—"}</div>
                          {m.plan_code ? <div className="font-mono text-xs text-slate-400">{m.plan_code}</div> : null}
                        </td>
                        <td className="py-2 pr-4">
                          <StatusBadge value={m.status} kind={m.status === "active" || m.status === "trialing" ? "active" : "default"} />
                        </td>
                        <td className="py-2 pr-4">{m.period_end || "—"}</td>
                        <td className="py-2 pr-4 font-mono text-xs">{m.stripe_subscription_id || "—"}</td>
                        {canWrite && (
                          <td className="py-2">
                            <div className="flex flex-wrap gap-2">
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
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "pipeline" && <PipelineTab data={pipeline as never} />}
      {tab === "brokers" && <BrokersTab data={brokers as never} />}
      {tab === "agents" && <AgentsTab data={agents as never} />}
      {tab === "executions" && <ExecutionsTab items={executions as never} />}
      {tab === "risk" && <RiskDisclosureTab data={riskDisclosures as never} />}

      <ConfirmDialog
        open={confirmId !== null}
        title={confirmKind === "cancel" ? "取消订阅" : "重新激活订阅"}
        danger={confirmKind === "cancel"}
        loading={acting}
        onClose={() => { setConfirmId(null); setConfirmKind(null); }}
        onConfirm={runMembershipAction}
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
              <button type="button" className="btn-primary" disabled={acting || extendDays < 1} onClick={extendMembership}>
                {acting ? "处理中…" : "确认延期"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-0.5 font-medium text-slate-900">{value}</p>
    </div>
  );
}
