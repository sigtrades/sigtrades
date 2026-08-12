import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { executionsApi } from "@/api";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import Pagination from "@/components/ui/Pagination";
import EmptyState from "@/components/ui/EmptyState";
import { signalSummaryRows } from "@/lib/formatDisplay";

type ExecRow = {
  id: string;
  user_id: string;
  user_email?: string | null;
  source_id: string;
  signal_id: string;
  broker: string;
  account_id?: string | null;
  account_label?: string;
  is_paper?: boolean | null;
  env_label?: string | null;
  status: string;
  detail?: string;
  channel_id?: string | null;
  signal_subtype?: string | null;
  realized_pnl?: number | null;
  created_at: string;
  signal?: Record<string, unknown>;
};

function EnvBadge({ isPaper, label }: { isPaper?: boolean | null; label?: string | null }) {
  if (isPaper === true) {
    return <StatusBadge value={label || "模拟"} kind="pending" />;
  }
  if (isPaper === false) {
    return <StatusBadge value={label || "实盘"} kind="success" />;
  }
  return <span className="text-slate-400">—</span>;
}

export default function Executions() {
  const [items, setItems] = useState<ExecRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [broker, setBroker] = useState("");
  const [userId, setUserId] = useState("");
  const [selected, setSelected] = useState<ExecRow | null>(null);
  const [showRawSignal, setShowRawSignal] = useState(false);
  const [loading, setLoading] = useState(true);
  const limit = 20;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await executionsApi.list({
        page,
        limit,
        status: status || undefined,
        user_id: userId.trim() || undefined,
        broker: broker.trim() || undefined,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } finally {
      setLoading(false);
    }
  }, [page, status, userId, broker]);

  useEffect(() => {
    load().catch(() => setItems([]));
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / limit));

  const openDetail = async (id: string) => {
    const data = await executionsApi.get(id);
    setShowRawSignal(false);
    setSelected(data as ExecRow);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="执行记录" subtitle="全平台信号执行审计" />
      <div className="card flex flex-wrap gap-3 p-4">
        <input className="input max-w-xs" placeholder="状态" value={status} onChange={(e) => setStatus(e.target.value)} />
        <input className="input max-w-xs" placeholder="券商" value={broker} onChange={(e) => setBroker(e.target.value)} />
        <input className="input max-w-md font-mono text-xs" placeholder="用户 UUID" value={userId} onChange={(e) => setUserId(e.target.value)} />
        <button
          type="button"
          className="btn-secondary"
          onClick={() => {
            setPage(1);
            load();
          }}
        >
          筛选
        </button>
      </div>

      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">用户</th>
              <th className="px-4 py-3">信号</th>
              <th className="px-4 py-3">券商</th>
              <th className="px-4 py-3">环境</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">时间</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-400">
                  加载中…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <EmptyState />
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link to={`/users/${row.user_id}`} className="text-brand-600 hover:underline">
                      {row.user_email || `${row.user_id.slice(0, 8)}…`}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-slate-700">{row.source_id}</span>
                    <span className="text-slate-400"> / </span>
                    <span className="font-mono text-xs">{row.signal_id}</span>
                  </td>
                  <td className="px-4 py-3">
                    {row.broker}
                    {row.account_label ? ` · ${row.account_label}` : ""}
                  </td>
                  <td className="px-4 py-3">
                    <EnvBadge isPaper={row.is_paper} label={row.env_label} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={row.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-600">{row.created_at}</td>
                  <td className="px-4 py-3">
                    <button type="button" className="text-brand-600 hover:underline" onClick={() => openDetail(row.id)}>
                      详情
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <div className="border-t border-slate-200 px-4 py-3">
          <Pagination page={page} totalPages={totalPages} total={total} onPrev={() => setPage((p) => p - 1)} onNext={() => setPage((p) => p + 1)} />
        </div>
      </div>

      {selected !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setSelected(null)}>
          <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-lg font-semibold">执行详情</h2>
              <button type="button" className="text-slate-500 hover:text-slate-900" onClick={() => setSelected(null)}>
                关闭
              </button>
            </div>
            <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <Info label="ID" value={selected.id} mono />
              <Info label="用户" value={selected.user_email || selected.user_id} />
              <Info label="状态" value={selected.status} />
              <Info label="券商" value={`${selected.broker} · ${selected.account_label || "—"}`} />
              <Info label="环境" value={selected.env_label || (selected.is_paper === true ? "模拟" : selected.is_paper === false ? "实盘" : "—")} />
              <Info label="账户 ID" value={selected.account_id || "—"} mono />
              <Info label="时间" value={selected.created_at} />
              <Info label="source" value={selected.source_id} />
              <Info label="signal_id" value={selected.signal_id} mono />
              <Info label="频道" value={selected.channel_id || "—"} mono />
              <Info label="子类型" value={selected.signal_subtype || "—"} />
              <Info
                label="realized_pnl"
                value={selected.realized_pnl == null ? "—" : String(selected.realized_pnl)}
              />
            </div>
            {selected.detail ? (
              <div className="mt-4">
                <p className="mb-1 text-xs font-medium text-slate-500">详情</p>
                <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{selected.detail}</p>
              </div>
            ) : null}
            {selected.signal ? (
              <div className="mt-4">
                <p className="mb-2 text-xs font-medium text-slate-500">信号摘要</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {signalSummaryRows(selected.signal).map((row) => (
                    <div key={row.label} className="rounded-lg bg-slate-50 px-3 py-2">
                      <p className="text-[11px] text-slate-500">{row.label}</p>
                      <p className="font-medium text-slate-900">{row.value}</p>
                    </div>
                  ))}
                </div>
                <button type="button" className="mt-3 text-xs text-brand-600 hover:underline" onClick={() => setShowRawSignal((v) => !v)}>
                  {showRawSignal ? "隐藏原始 JSON" : "查看原始 JSON"}
                </button>
                {showRawSignal ? (
                  <pre className="code-block mt-2 max-h-48 overflow-auto text-xs">{JSON.stringify(selected.signal, null, 2)}</pre>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={mono ? "mt-0.5 font-mono text-xs" : "mt-0.5 font-medium"}>{value}</p>
    </div>
  );
}
