import { useCallback, useEffect, useState } from "react";
import { PlusIcon, PencilIcon, TrashIcon } from "@heroicons/react/24/outline";
import { broadcastsApi } from "@/api";
import { canWriteAdmin } from "@/lib/adminPermissions";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { AdminToast } from "@/components/ui/AdminToast";
import { useAuthStore } from "@/store/auth";

type EmailAudience = "none" | "all" | "members";

type Broadcast = {
  id: string;
  title_zh: string;
  title_en: string;
  body_md_zh: string;
  body_md_en: string;
  send_count: number;
  last_sent_at?: string | null;
  revoked_at?: string | null;
  email_audience?: EmailAudience;
  created_at?: string | null;
};

const emptyForm = {
  title_zh: "",
  title_en: "",
  body_md_zh: "",
  body_md_en: "",
  email_audience: "none" as EmailAudience,
};

const AUDIENCE_LABEL: Record<EmailAudience, string> = {
  none: "不发邮件",
  all: "全员邮件",
  members: "仅会员",
};

export default function InAppMessages() {
  const [items, setItems] = useState<Broadcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState<"create" | "edit">("create");
  const [formId, setFormId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [confirm, setConfirm] = useState<{ kind: "send" | "resend" | "revoke" | "delete"; id: string } | null>(null);
  const [acting, setActing] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const role = useAuthStore((s) => s.role);
  const canWrite = canWriteAdmin(role);

  const load = useCallback(() => {
    setLoading(true);
    broadcastsApi
      .list()
      .then((rows) => setItems(rows as Broadcast[]))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setFormMode("create");
    setFormId(null);
    setForm(emptyForm);
    setFormOpen(true);
  };

  const openEdit = (row: Broadcast) => {
    setFormMode("edit");
    setFormId(row.id);
    setForm({
      title_zh: row.title_zh,
      title_en: row.title_en,
      body_md_zh: row.body_md_zh,
      body_md_en: row.body_md_en,
      email_audience: (row.email_audience as EmailAudience) || "none",
    });
    setFormOpen(true);
  };

  const saveForm = async () => {
    try {
      if (formMode === "create") {
        await broadcastsApi.create(form);
        setToast({ message: "草稿已创建", type: "success" });
      } else if (formId) {
        await broadcastsApi.update(formId, form);
        setToast({ message: "已保存", type: "success" });
      }
      setFormOpen(false);
      load();
    } catch {
      setToast({ message: "保存失败（已发送的不可编辑）", type: "error" });
    }
  };

  const runConfirm = async () => {
    if (!confirm) return;
    setActing(true);
    try {
      if (confirm.kind === "send") await broadcastsApi.send(confirm.id);
      else if (confirm.kind === "resend") await broadcastsApi.resend(confirm.id);
      else if (confirm.kind === "revoke") await broadcastsApi.revoke(confirm.id);
      else if (confirm.kind === "delete") await broadcastsApi.remove(confirm.id);
      setToast({ message: "操作成功", type: "success" });
      setConfirm(null);
      load();
    } catch {
      setToast({ message: "操作失败", type: "error" });
    } finally {
      setActing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader title="用户通知" subtitle="全站站内信广播" />
        {canWrite && (
          <button type="button" className="btn-primary" onClick={openCreate}>
            <PlusIcon className="h-4 w-4" /> 新建公告
          </button>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">标题</th>
              <th className="px-4 py-3">发送</th>
              <th className="px-4 py-3">邮件</th>
              <th className="px-4 py-3">状态</th>
              {canWrite && <th className="px-4 py-3">操作</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="py-8 text-center text-slate-400">加载中…</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={5}><EmptyState /></td></tr>
            ) : (
              items.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="font-medium">{row.title_zh || row.title_en}</div>
                    <div className="mt-1 line-clamp-2 text-xs text-slate-500">{row.body_md_zh}</div>
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {row.send_count ?? 0} 次
                    <div className="text-xs text-slate-400">{row.last_sent_at || "—"}</div>
                  </td>
                  <td className="px-4 py-3 text-xs">{AUDIENCE_LABEL[(row.email_audience as EmailAudience) || "none"]}</td>
                  <td className="px-4 py-3">
                    {row.revoked_at ? (
                      <StatusBadge value="已撤回" kind="offline" />
                    ) : row.send_count > 0 ? (
                      <StatusBadge value="已发送" kind="active" />
                    ) : (
                      <StatusBadge value="草稿" kind="pending" />
                    )}
                  </td>
                  {canWrite && (
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2 text-xs">
                        {row.send_count === 0 && !row.revoked_at && (
                          <>
                            <button type="button" className="text-brand-600 hover:underline" onClick={() => openEdit(row)}><PencilIcon className="inline h-3 w-3" /> 编辑</button>
                            <button type="button" className="text-brand-600 hover:underline" onClick={() => setConfirm({ kind: "send", id: row.id })}>发送</button>
                            <button type="button" className="text-red-600 hover:underline" onClick={() => setConfirm({ kind: "delete", id: row.id })}><TrashIcon className="inline h-3 w-3" /></button>
                          </>
                        )}
                        {row.send_count > 0 && !row.revoked_at && (
                          <>
                            <button type="button" className="text-brand-600 hover:underline" onClick={() => setConfirm({ kind: "resend", id: row.id })}>补发</button>
                            <button type="button" className="text-amber-600 hover:underline" onClick={() => setConfirm({ kind: "revoke", id: row.id })}>撤回</button>
                          </>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold">{formMode === "create" ? "新建公告" : "编辑公告"}</h2>
            <div className="mt-4 grid gap-3">
              <input className="input" placeholder="中文标题" value={form.title_zh} onChange={(e) => setForm({ ...form, title_zh: e.target.value })} />
              <input className="input" placeholder="英文标题" value={form.title_en} onChange={(e) => setForm({ ...form, title_en: e.target.value })} />
              <textarea className="textarea" rows={4} placeholder="中文正文 Markdown" value={form.body_md_zh} onChange={(e) => setForm({ ...form, body_md_zh: e.target.value })} />
              <textarea className="textarea" rows={4} placeholder="英文正文 Markdown" value={form.body_md_en} onChange={(e) => setForm({ ...form, body_md_en: e.target.value })} />
              <select className="input" value={form.email_audience} onChange={(e) => setForm({ ...form, email_audience: e.target.value as EmailAudience })}>
                {Object.entries(AUDIENCE_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setFormOpen(false)}>取消</button>
              <button type="button" className="btn-primary" onClick={saveForm}>保存草稿</button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirm !== null}
        title={confirm?.kind === "revoke" ? "撤回公告" : confirm?.kind === "delete" ? "删除草稿" : confirm?.kind === "resend" ? "补发公告" : "首次发送"}
        danger={confirm?.kind === "revoke" || confirm?.kind === "delete"}
        loading={acting}
        onClose={() => setConfirm(null)}
        onConfirm={runConfirm}
      >
        {confirm?.kind === "revoke" ? "撤回后用户端将不再展示该公告。" : confirm?.kind === "resend" ? "将向所有用户再次写入收件箱。" : "确认执行？"}
      </ConfirmDialog>

      {toast ? <AdminToast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} /> : null}
    </div>
  );
}
