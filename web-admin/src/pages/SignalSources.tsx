import { useEffect, useState } from "react";
import { PlusIcon, PencilIcon, TrashIcon } from "@heroicons/react/24/outline";
import { sourcesApi } from "@/api";
import { canWriteAdmin } from "@/lib/adminPermissions";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuthStore } from "@/store/auth";

type Source = {
  source_id: string;
  kind: string;
  ownership: string;
  owner_user_id?: string | null;
  owner_email?: string | null;
  discord_username?: string | null;
  name: string;
  is_active: boolean;
  config: Record<string, unknown>;
};

const KIND_LABELS: Record<string, string> = {
  discord: "Discord",
  webhook: "Webhook",
  telegram: "Telegram",
  email: "邮件",
};

const OWNERSHIP_LABELS: Record<string, string> = {
  platform_shared: "平台共享",
  user_private: "用户私有",
  user_owned: "用户私有",
};

function kindLabel(kind: string): string {
  return KIND_LABELS[kind] || kind;
}

function ownershipLabel(ownership: string): string {
  return OWNERSHIP_LABELS[ownership] || ownership;
}

const emptyForm = (): Source => ({
  source_id: "",
  kind: "discord",
  ownership: "platform_shared",
  name: "",
  is_active: true,
  config: {},
});

export default function SignalSources() {
  const [items, setItems] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<Source>(emptyForm());
  const [configJson, setConfigJson] = useState("{}");
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const role = useAuthStore((s) => s.role);
  const canWrite = canWriteAdmin(role);

  const load = () => {
    setLoading(true);
    sourcesApi
      .list()
      .then((data) => setItems(Array.isArray(data) ? data : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setForm(emptyForm());
    setConfigJson("{}");
    setModal(true);
  };

  const openEdit = (s: Source) => {
    setForm({ ...s });
    setConfigJson(JSON.stringify(s.config || {}, null, 2));
    setModal(true);
  };

  const save = async () => {
    if (!form.source_id.trim()) return;
    let config: Record<string, unknown> = {};
    try {
      config = JSON.parse(configJson || "{}");
    } catch {
      alert("配置 JSON 格式无效");
      return;
    }
    setSaving(true);
    try {
      const body = { ...form, config };
      const exists = items.some((i) => i.source_id === form.source_id);
      if (exists) await sourcesApi.update(form.source_id, body);
      else await sourcesApi.create(body);
      setModal(false);
      load();
    } finally {
      setSaving(false);
    }
  };

  const deactivate = async () => {
    if (!deleteId) return;
    setSaving(true);
    try {
      await sourcesApi.deactivate(deleteId);
      setDeleteId(null);
      load();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader title="信号源" subtitle="平台共享 Discord 等信号源配置" />
        {canWrite && (
          <button type="button" className="btn-primary" onClick={openCreate}>
            <PlusIcon className="h-4 w-4" /> 新建信号源
          </button>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">源 ID</th>
              <th className="px-4 py-3">名称</th>
              <th className="px-4 py-3">类型</th>
              <th className="px-4 py-3">归属</th>
              <th className="px-4 py-3">账户</th>
              <th className="px-4 py-3">状态</th>
              {canWrite && <th className="px-4 py-3">操作</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={canWrite ? 7 : 6} className="py-8 text-center text-slate-400">加载中…</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={canWrite ? 7 : 6}><EmptyState message="暂无信号源" /></td></tr>
            ) : (
              items.map((s) => (
                <tr key={s.source_id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs">{s.source_id}</td>
                  <td className="px-4 py-3">
                    <div>{s.name || "—"}</div>
                    {s.discord_username ? (
                      <div className="mt-0.5 text-xs text-slate-400">Discord @{s.discord_username}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">{kindLabel(s.kind)}</td>
                  <td className="px-4 py-3">{ownershipLabel(s.ownership)}</td>
                  <td className="px-4 py-3 text-xs text-slate-700">{s.owner_email || "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge value={s.is_active ? "启用" : "停用"} kind={s.is_active ? "active" : "offline"} />
                  </td>
                  {canWrite && (
                    <td className="px-4 py-3">
                      <button type="button" className="mr-3 text-brand-600 hover:underline" onClick={() => openEdit(s)}>
                        <PencilIcon className="inline h-4 w-4" /> 编辑
                      </button>
                      {s.is_active && (
                        <button type="button" className="text-red-600 hover:underline" onClick={() => setDeleteId(s.source_id)}>
                          <TrashIcon className="inline h-4 w-4" /> 停用
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
            <h2 className="text-lg font-semibold">{items.some((i) => i.source_id === form.source_id) ? "编辑信号源" : "新建信号源"}</h2>
            <div className="mt-4 grid gap-3">
              <div>
                <label className="mb-1 block text-xs text-slate-500">源 ID</label>
                <input
                  className="input font-mono text-xs"
                  placeholder="例如 platform-discord-demo"
                  value={form.source_id}
                  onChange={(e) => setForm({ ...form, source_id: e.target.value })}
                  disabled={items.some((i) => i.source_id === form.source_id)}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">显示名称</label>
                <input
                  className="input"
                  placeholder="显示名称"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">类型</label>
                <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                  <option value="discord">Discord</option>
                  <option value="webhook">Webhook</option>
                  <option value="telegram">Telegram</option>
                  <option value="email">邮件</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">归属</label>
                <select
                  className="input"
                  value={form.ownership === "user_private" ? "user_owned" : form.ownership}
                  onChange={(e) => setForm({ ...form, ownership: e.target.value })}
                >
                  <option value="platform_shared">平台共享</option>
                  <option value="user_owned">用户私有</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                启用
              </label>
              <div>
                <label className="mb-1 block text-xs text-slate-500">配置（JSON）</label>
                <textarea className="textarea font-mono text-xs" rows={8} value={configJson} onChange={(e) => setConfigJson(e.target.value)} />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setModal(false)}>取消</button>
              <button type="button" className="btn-primary" disabled={saving} onClick={save}>{saving ? "保存中…" : "保存"}</button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog open={deleteId !== null} title="停用信号源" danger loading={saving} onClose={() => setDeleteId(null)} onConfirm={deactivate}>
        停用后用户将无法订阅该信号源，确定继续？
      </ConfirmDialog>
    </div>
  );
}
