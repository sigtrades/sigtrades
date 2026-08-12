import { useCallback, useEffect, useState, type FormEvent } from "react";
import clsx from "clsx";
import { MagnifyingGlassIcon, XMarkIcon } from "@heroicons/react/24/outline";
import {
  inboundMailApi,
  type InboundEmailDetail,
  type InboundEmailListItem,
} from "@/api";
import { formatEtDateTime } from "../lib/datetime";

const DEFAULT_FROM = "team@sigtrades.com";

function shortenId(id: string, left = 10) {
  if (!id) return "—";
  if (id.length <= left + 3) return id;
  return `${id.slice(0, left)}…`;
}

function isRowUnread(row: InboundEmailListItem) {
  if (typeof row.is_read === "boolean") return !row.is_read;
  return !row.read_at;
}

export default function InboundMailPanel() {
  const [items, setItems] = useState<InboundEmailListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<InboundEmailDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeFrom, setComposeFrom] = useState(DEFAULT_FROM);
  const [composeTo, setComposeTo] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeText, setComposeText] = useState("");
  const [composeSending, setComposeSending] = useState(false);
  const [toast, setToast] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [emailQuery, setEmailQuery] = useState("");
  const [emailFilter, setEmailFilter] = useState("");

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await inboundMailApi.list({
        page,
        page_size: pageSize,
        email: emailFilter.trim() || undefined,
      });
      setItems(data.items || []);
      setTotal(data.total ?? data.pagination?.total ?? 0);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "加载失败";
      setToast({ type: "err", text: msg });
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, emailFilter]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const openDetail = async (row: InboundEmailListItem) => {
    setDetailOpen(true);
    setDetail(null);
    setReplyText("");
    setDetailLoading(true);
    try {
      const d = (await inboundMailApi.get(row.id)) as InboundEmailDetail;
      setDetail(d);
      setItems((prev) =>
        prev.map((it) => (it.id === row.id ? { ...it, is_read: true, read_at: d.read_at ?? it.read_at } : it)),
      );
      window.dispatchEvent(new CustomEvent("admin:inbound-mail-updated"));
    } catch {
      setToast({ type: "err", text: "加载详情失败" });
      setDetailOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const sendReply = async () => {
    if (!detail) return;
    const text = replyText.trim();
    if (!text) {
      setToast({ type: "err", text: "请填写回复正文" });
      return;
    }
    setSending(true);
    try {
      await inboundMailApi.reply(detail.id, { text });
      setDetailOpen(false);
      setDetail(null);
      setReplyText("");
      setToast({ type: "ok", text: "回复已发送，邮件已从收件地址发出" });
      void loadList();
      window.dispatchEvent(new CustomEvent("admin:inbound-mail-updated"));
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "response" in e
          ? String((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "发送失败")
          : "发送失败";
      setToast({ type: "err", text: msg });
    } finally {
      setSending(false);
    }
  };

  const sendOutboundEmail = async () => {
    const fromEmail = composeFrom.trim() || DEFAULT_FROM;
    const to = composeTo.trim();
    const subject = composeSubject.trim();
    const text = composeText.trim();
    if (!fromEmail) {
      setToast({ type: "err", text: "请填写发件地址" });
      return;
    }
    if (!to) {
      setToast({ type: "err", text: "请填写收件人邮箱" });
      return;
    }
    if (!subject) {
      setToast({ type: "err", text: "请填写邮件主题" });
      return;
    }
    if (!text) {
      setToast({ type: "err", text: "请填写邮件正文" });
      return;
    }
    setComposeSending(true);
    try {
      await inboundMailApi.send({ from_email: fromEmail, to, subject, text });
      setComposeOpen(false);
      setComposeFrom(DEFAULT_FROM);
      setComposeTo("");
      setComposeSubject("");
      setComposeText("");
      setToast({ type: "ok", text: "邮件已发送" });
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "response" in e
          ? String((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "发送失败")
          : "发送失败";
      setToast({ type: "err", text: msg });
    } finally {
      setComposeSending(false);
    }
  };

  const downloadAttachment = (attachmentId: string, filename: string) => {
    if (!detail) return;
    const url = inboundMailApi.attachmentUrl(detail.id, attachmentId);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const handleEmailSearch = (e: FormEvent) => {
    e.preventDefault();
    setPage(1);
    setEmailFilter(emailQuery.trim());
  };

  const clearEmailFilter = () => {
    setEmailQuery("");
    setEmailFilter("");
    setPage(1);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500">
          Resend <code className="rounded bg-slate-100 px-1 text-xs">email.received</code>{" "}
          入站；快捷回复使用原邮件收件地址作为发件人。
        </p>
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <span>共 {total} 封</span>
          <button type="button" onClick={() => setComposeOpen(true)} className="btn-primary px-3 py-1.5 text-sm">
            发送邮件
          </button>
          <button type="button" onClick={() => void loadList()} className="btn-secondary px-3 py-1.5 text-sm">
            刷新
          </button>
        </div>
      </div>

      {toast ? (
        <div
          className={clsx(
            "rounded-lg px-4 py-3 text-sm",
            toast.type === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800",
          )}
        >
          {toast.text}
        </div>
      ) : null}

      <form onSubmit={handleEmailSearch} className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] max-w-xl flex-1">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={emailQuery}
            onChange={(e) => setEmailQuery(e.target.value)}
            placeholder="按邮箱筛选（发件人 / 收件人 / 工单联系邮箱）"
            className="input w-full py-2 pl-10 pr-4 text-sm"
          />
        </div>
        <button type="submit" className="btn-primary px-4 py-2 text-sm">
          搜索
        </button>
        {emailFilter ? (
          <button type="button" onClick={clearEmailFilter} className="btn-secondary px-3 py-2 text-sm">
            清除筛选
          </button>
        ) : null}
        {emailFilter ? (
          <span className="text-sm text-slate-500">
            当前筛选：<code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{emailFilter}</code>
          </span>
        ) : null}
      </form>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">时间</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">发件人</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">主题</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">收件人</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">Resend ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                    加载中…
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                    暂无入站邮件
                  </td>
                </tr>
              ) : (
                items.map((row) => {
                  const unread = isRowUnread(row);
                  return (
                    <tr
                      key={row.id}
                      className={clsx(
                        "cursor-pointer border-l-4",
                        unread
                          ? "border-l-brand-500 bg-brand-50/30 font-semibold text-slate-900 hover:bg-brand-50/50"
                          : "border-l-transparent font-normal text-slate-500 hover:bg-slate-50",
                      )}
                      onClick={() => void openDetail(row)}
                    >
                      <td className="whitespace-nowrap px-4 py-3 text-sm">
                        {row.received_at || row.created_at ? formatEtDateTime(row.received_at || row.created_at) : "—"}
                      </td>
                      <td className="max-w-[200px] truncate px-4 py-3 text-sm" title={row.from_address}>
                        {row.from_address}
                      </td>
                      <td className="max-w-[240px] truncate px-4 py-3 text-sm" title={row.subject || ""}>
                        {row.is_support_ticket ? (
                          <span className="mr-2 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                            工单
                          </span>
                        ) : null}
                        {row.subject || "(无主题)"}
                      </td>
                      <td
                        className="max-w-[200px] truncate px-4 py-3 text-sm"
                        title={(row.to_addresses || []).join(", ")}
                      >
                        {(row.to_addresses || []).join(", ") || "—"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs opacity-90">
                        {shortenId(row.resend_email_id)}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {row.fetch_error ? (
                          <span className="text-amber-700" title={row.fetch_error}>
                            拉取异常
                          </span>
                        ) : (
                          <span className={unread ? "text-brand-700" : "text-slate-400"}>已入库</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {total > pageSize ? (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
            <span>
              第 {page} / {totalPages} 页
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="btn-secondary px-3 py-1 disabled:opacity-40"
              >
                上一页
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="btn-secondary px-3 py-1 disabled:opacity-40"
              >
                下一页
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {detailOpen ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
          <button
            type="button"
            className="absolute inset-0 bg-slate-900/50"
            aria-label="关闭"
            onClick={() => setDetailOpen(false)}
          />
          <div className="relative flex max-h-[92vh] w-full max-w-4xl flex-col rounded-t-2xl bg-white shadow-xl sm:rounded-2xl">
            <div className="flex shrink-0 items-start justify-between border-b border-slate-100 px-5 py-4">
              <div className="min-w-0 pr-4">
                <h2 className="break-words text-lg font-semibold text-slate-900">{detail?.subject || "(无主题)"}</h2>
                <p className="mt-1 break-words text-xs text-slate-500">
                  {detail ? `发件：${detail.from_address}` : "…"}
                </p>
                {detail?.is_support_ticket ? (
                  <p className="mt-1 break-words text-xs text-blue-700">
                    工单回复目标：{detail.reply_to_address || "未解析到客户邮箱"}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                className="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                onClick={() => setDetailOpen(false)}
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
              {detailLoading ? (
                <p className="text-slate-500">加载中…</p>
              ) : detail ? (
                <>
                  <section className="rounded-xl border border-slate-200 bg-slate-50/90 p-4 text-sm" aria-label="邮件元信息">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between lg:gap-8">
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">收件人</div>
                        <div className="break-words leading-relaxed text-slate-900">
                          {(detail.to_addresses || []).join(", ") || "—"}
                        </div>
                      </div>
                      <div className="min-w-0 shrink-0 space-y-1 lg:text-right">
                        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">时间</div>
                        <div className="tabular-nums text-slate-900">
                          {detail.received_at || detail.created_at
                            ? formatEtDateTime(detail.received_at || detail.created_at)
                            : "—"}
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 space-y-1 border-t border-slate-200/80 pt-4">
                      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Resend email_id</div>
                      <code className="block break-all font-mono text-xs leading-relaxed text-slate-800">
                        {detail.resend_email_id}
                      </code>
                    </div>
                    {detail.fetch_error ? (
                      <div className="mt-4 break-words rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
                        拉取正文失败：{detail.fetch_error}
                      </div>
                    ) : null}
                    {detail.is_support_ticket ? (
                      <div className="mt-4 break-words rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-900">
                        已识别为客服工单，快捷回复将发送给客户邮箱：
                        <span className="font-semibold">{detail.reply_to_address || "未解析到客户邮箱"}</span>
                      </div>
                    ) : null}
                  </section>

                  {detail.html ? (
                    <div className="min-h-0 space-y-2">
                      <h3 className="text-sm font-medium text-slate-800">邮件正文（HTML）</h3>
                      <iframe
                        title="html-preview"
                        sandbox=""
                        className="h-[min(52vh,520px)] min-h-[280px] w-full rounded-lg border border-slate-200 bg-white"
                        srcDoc={detail.html}
                      />
                      {detail.text?.trim() ? (
                        <details className="rounded-lg border border-slate-100 bg-white">
                          <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
                            纯文本视图（备用）
                          </summary>
                          <pre className="max-h-56 overflow-auto whitespace-pre-wrap border-t border-slate-100 px-3 py-3 text-sm text-slate-800">
                            {detail.text}
                          </pre>
                        </details>
                      ) : null}
                    </div>
                  ) : (
                    <div>
                      <h3 className="text-sm font-medium text-slate-800">正文（纯文本）</h3>
                      <pre className="mt-2 max-h-[min(40vh,360px)] overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-800">
                        {detail.text?.trim() ? detail.text : "（无正文）"}
                      </pre>
                    </div>
                  )}

                  {(detail.attachments || []).length > 0 ? (
                    <div>
                      <h3 className="text-sm font-medium text-slate-700">附件</h3>
                      <ul className="mt-2 space-y-1">
                        {(detail.attachments || []).map((a, i) => {
                          const id = a.id || String(i);
                          const name = a.filename || a.name || id;
                          return (
                            <li key={id}>
                              <button
                                type="button"
                                className="text-sm text-brand-600 hover:underline"
                                onClick={() => downloadAttachment(id, name)}
                              >
                                {name}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : null}

                  <div className="border-t border-slate-100 pt-4">
                    <h3 className="text-sm font-medium text-slate-900">快捷回复</h3>
                    <p className="mt-1 text-xs text-slate-500">
                      {detail.is_support_ticket
                        ? `将发送至客户邮箱：${detail.reply_to_address || "未解析到客户邮箱"}；发件地址为该邮件的收件地址（首条 to）。`
                        : "将发送至对方邮箱；发件地址为该邮件的收件地址（首条 to）。"}
                    </p>
                    <label className="mt-3 block text-xs font-medium text-slate-600">正文（必填，纯文本）</label>
                    <textarea
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      rows={5}
                      className="textarea mt-1 w-full"
                      placeholder="纯文本回复…"
                    />
                    <button
                      type="button"
                      disabled={sending}
                      onClick={() => void sendReply()}
                      className="btn-primary mt-4 disabled:opacity-50"
                    >
                      {sending ? "发送中…" : "发送回复"}
                    </button>
                  </div>
                </>
              ) : (
                <p className="text-slate-500">无法加载详情</p>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {composeOpen ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
          <button
            type="button"
            className="absolute inset-0 bg-slate-900/50"
            aria-label="关闭"
            onClick={() => setComposeOpen(false)}
          />
          <div className="relative flex max-h-[92vh] w-full max-w-2xl flex-col rounded-t-2xl bg-white shadow-xl sm:rounded-2xl">
            <div className="flex shrink-0 items-start justify-between border-b border-slate-100 px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">发送邮件</h2>
                <p className="mt-1 text-xs text-slate-500">将通过 Resend 发送，默认发件地址为 {DEFAULT_FROM}。</p>
              </div>
              <button
                type="button"
                className="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                onClick={() => setComposeOpen(false)}
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <div>
                <label className="block text-xs font-medium text-slate-600">发件地址</label>
                <input
                  type="email"
                  value={composeFrom}
                  onChange={(e) => setComposeFrom(e.target.value)}
                  placeholder={DEFAULT_FROM}
                  className="input mt-1 w-full"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600">收件人邮箱</label>
                <input
                  type="email"
                  value={composeTo}
                  onChange={(e) => setComposeTo(e.target.value)}
                  placeholder="customer@example.com"
                  className="input mt-1 w-full"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600">主题</label>
                <input
                  type="text"
                  value={composeSubject}
                  onChange={(e) => setComposeSubject(e.target.value)}
                  placeholder="请输入邮件主题"
                  className="input mt-1 w-full"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600">正文（必填，纯文本）</label>
                <textarea
                  value={composeText}
                  onChange={(e) => setComposeText(e.target.value)}
                  rows={8}
                  placeholder="纯文本正文…"
                  className="textarea mt-1 w-full"
                />
              </div>
              <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
                <button
                  type="button"
                  disabled={composeSending}
                  onClick={() => setComposeOpen(false)}
                  className="btn-secondary disabled:opacity-50"
                >
                  取消
                </button>
                <button
                  type="button"
                  disabled={composeSending}
                  onClick={() => void sendOutboundEmail()}
                  className="btn-primary disabled:opacity-50"
                >
                  {composeSending ? "发送中…" : "发送"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
