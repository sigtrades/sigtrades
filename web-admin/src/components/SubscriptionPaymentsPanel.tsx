import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { paymentsApi } from "@/api";
import EmptyState from "@/components/ui/EmptyState";
import Pagination from "@/components/ui/Pagination";

type DisplayStatus = "paid" | "pending_sync" | "abandoned" | "failed" | "superseded";
type PaymentKind = "initial" | "renewal" | "upgrade" | "intent";

type Row = {
  id: string;
  user_id: string;
  user_email: string;
  plan_code: string;
  billing_cycle: string;
  amount: number;
  currency: string;
  checkout_session_id?: string | null;
  payment_kind: PaymentKind;
  display_status: DisplayStatus;
  accepted_at?: string | null;
  membership?: {
    status?: string | null;
    current_period_end?: string | null;
    plan?: { name?: string; code?: string } | null;
  } | null;
};

function kindLabel(kind: PaymentKind) {
  if (kind === "renewal") return "续费";
  if (kind === "upgrade") return "升级";
  if (kind === "initial") return "首开";
  return "未支付意向";
}

function kindBadge(kind: PaymentKind) {
  if (kind === "renewal") return "bg-blue-100 text-blue-800";
  if (kind === "upgrade") return "bg-purple-100 text-purple-800";
  if (kind === "initial") return "bg-slate-100 text-slate-800";
  return "bg-slate-100 text-slate-600";
}

function statusBadge(status: DisplayStatus) {
  if (status === "paid") return "bg-green-100 text-green-800";
  if (status === "pending_sync") return "bg-amber-100 text-amber-900";
  if (status === "failed") return "bg-red-100 text-red-800";
  return "bg-slate-100 text-slate-600";
}

function statusLabel(status: DisplayStatus) {
  if (status === "paid") return "已支付";
  if (status === "pending_sync") return "待同步";
  if (status === "failed") return "续费失败";
  if (status === "superseded") return "已作废";
  return "未支付";
}

function cycleLabel(cycle: string) {
  if (cycle === "yearly") return "年付";
  if (cycle === "monthly") return "月付";
  return cycle || "—";
}

function canResync(row: Row) {
  if (row.display_status === "paid" || row.display_status === "abandoned") return false;
  const sid = row.checkout_session_id || "";
  return sid.startsWith("cs_") || sid.startsWith("invoice:");
}

function fmtMoney(amount: number, currency: string) {
  const cur = (currency || "usd").toUpperCase();
  return `${cur === "USD" ? "$" : `${cur} `}${Number(amount || 0).toFixed(2)}`;
}

export default function SubscriptionPaymentsPanel() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [searchInput, setSearchInput] = useState("");
  const [searchValue, setSearchValue] = useState("");
  const [resyncingId, setResyncingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const pageSize = 20;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await paymentsApi.subscriptionPayments(page, pageSize, searchValue || undefined);
      setRows(res.items || []);
      setTotal(res.total || 0);
    } catch {
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, searchValue]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleResync = async (id: string) => {
    setResyncingId(id);
    try {
      const res = await paymentsApi.resync(id);
      if (res?.data?.synced) {
        setToast({ message: "已同步会员状态", type: "success" });
      } else {
        setToast({ message: `同步未完成：${res?.data?.reason || "未知原因"}`, type: "error" });
      }
      await load();
    } catch (error: unknown) {
      const e = error as { response?: { data?: { detail?: string } } };
      setToast({ message: e?.response?.data?.detail || "同步失败", type: "error" });
    } finally {
      setResyncingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-4">
      {toast ? (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            toast.type === "success"
              ? "border-green-200 bg-green-50 text-green-800"
              : "border-red-200 bg-red-50 text-red-800"
          }`}
        >
          {toast.message}
          <button type="button" className="ml-3 underline" onClick={() => setToast(null)}>
            关闭
          </button>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setSearchValue(searchInput.trim());
              setPage(1);
            }
          }}
          placeholder="搜索邮箱 / 套餐 / Session ID"
          className="w-72 rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="button"
          className="btn-primary py-1.5"
          onClick={() => {
            setSearchValue(searchInput.trim());
            setPage(1);
          }}
        >
          搜索
        </button>
        <button type="button" className="btn-secondary py-1.5" onClick={() => void load()}>
          刷新
        </button>
      </div>

      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="min-w-[1100px] w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3">用户</th>
                <th className="px-4 py-3">类型</th>
                <th className="px-4 py-3">套餐</th>
                <th className="px-4 py-3">周期</th>
                <th className="px-4 py-3">金额</th>
                <th className="px-4 py-3">支付状态</th>
                <th className="px-4 py-3">会员状态</th>
                <th className="px-4 py-3">到期日</th>
                <th className="px-4 py-3">发起时间</th>
                <th className="px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={10} className="px-4 py-8 text-center text-slate-500">
                    加载中...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={10}>
                    <EmptyState />
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <Link to={`/users/${row.user_id}`} className="font-medium text-brand-600 hover:underline">
                        {row.user_email}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${kindBadge(row.payment_kind)}`}>
                        {kindLabel(row.payment_kind)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {row.membership?.plan?.name || row.plan_code}
                      <span className="ml-1 text-slate-400">({row.plan_code})</span>
                    </td>
                    <td className="px-4 py-3">{cycleLabel(row.billing_cycle)}</td>
                    <td className="px-4 py-3 tabular-nums">{fmtMoney(row.amount, row.currency)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge(row.display_status)}`}>
                        {statusLabel(row.display_status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{row.membership?.status || "—"}</td>
                    <td className="px-4 py-3 text-slate-600">
                      {row.membership?.current_period_end
                        ? new Date(row.membership.current_period_end).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {row.accepted_at ? new Date(row.accepted_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {canResync(row) ? (
                        <button
                          type="button"
                          className="text-sm font-medium text-brand-600 hover:underline disabled:opacity-50"
                          disabled={resyncingId === row.id}
                          onClick={() => void handleResync(row.id)}
                        >
                          {resyncingId === row.id ? "同步中..." : "手动同步"}
                        </button>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-slate-200 px-4 py-3">
          <Pagination
            page={page}
            totalPages={totalPages}
            total={total}
            onPrev={() => setPage((p) => Math.max(1, p - 1))}
            onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
          />
        </div>
      </div>
    </div>
  );
}
