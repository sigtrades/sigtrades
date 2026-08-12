import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { analyticsApi } from "@/api";
import PageHeader from "@/components/ui/PageHeader";
import EmptyState from "@/components/ui/EmptyState";

type ChannelRow = {
  source_id: string;
  source_name: string;
  source_kind: string;
  channel_id?: string | null;
  channel_label: string;
  closed_trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  open_signals: number;
  total_pnl: number;
  win_rate: number | null;
};

type UserRow = {
  user_id: string;
  user_email?: string | null;
  closed_trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  total_pnl: number;
  win_rate: number | null;
};

const DAY_OPTIONS = [
  { value: 30, label: "30 天" },
  { value: 90, label: "90 天" },
  { value: 180, label: "180 天" },
  { value: 365, label: "1 年" },
];

const KIND_OPTIONS = [
  { value: "", label: "全部来源" },
  { value: "discord", label: "Discord" },
  { value: "telegram", label: "Telegram" },
  { value: "webhook", label: "Webhook" },
];

function pct(rate: number | null | undefined): string {
  if (rate == null) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

function pnlText(v: number): string {
  const n = Number(v) || 0;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}`;
}

export default function ChannelStats() {
  const [days, setDays] = useState(90);
  const [kind, setKind] = useState("discord");
  const [items, setItems] = useState<ChannelRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ChannelRow | null>(null);
  const [userRows, setUserRows] = useState<UserRow[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await analyticsApi.channelStats({
        days,
        kind: kind || undefined,
      });
      setItems(res.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [days, kind]);

  useEffect(() => {
    void load();
  }, [load]);

  const openDetail = async (row: ChannelRow) => {
    setSelected(row);
    setDetailLoading(true);
    try {
      const res = await analyticsApi.channelStatsDetail({
        source_id: row.source_id,
        channel_id: row.channel_id ?? "",
        days,
      });
      setUserRows(res.users || []);
    } catch {
      setUserRows([]);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader
          title="频道胜率"
          subtitle="按 Discord / Telegram 频道统计闭环交易胜率（OPEN 无 PnL 不计；同 signal 多券商去重）"
        />
        <div className="flex flex-wrap gap-2">
          {KIND_OPTIONS.map((opt) => (
            <button
              key={opt.value || "all"}
              type="button"
              className={kind === opt.value ? "btn-primary py-1.5" : "btn-secondary py-1.5"}
              onClick={() => setKind(opt.value)}
            >
              {opt.label}
            </button>
          ))}
          {DAY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={days === opt.value ? "btn-primary py-1.5" : "btn-secondary py-1.5"}
              onClick={() => setDays(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-relaxed text-slate-600">
        <p>
          <span className="font-semibold text-slate-800">胜率口径：</span>
          仅统计有 <code className="rounded bg-white px-1">realized_pnl</code> 的成交（多为平仓）；同一{" "}
          <code className="rounded bg-white px-1">signal_id</code> 多券商先合并盈亏再计 1 笔；OPEN
          无盈亏不进分母。PCS / 铁鹰等同理。
        </p>
      </div>

      <div className="card overflow-hidden p-0">
        <table className="min-w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-3">来源</th>
              <th className="px-4 py-3">频道</th>
              <th className="px-4 py-3">闭环笔数</th>
              <th className="px-4 py-3">胜 / 负</th>
              <th className="px-4 py-3">胜率</th>
              <th className="px-4 py-3">总 PnL</th>
              <th className="px-4 py-3">OPEN 信号</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-400">
                  加载中…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <EmptyState message="暂无带盈亏的闭环成交，或所选来源尚无数据" />
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr
                  key={`${row.source_id}:${row.channel_id || ""}`}
                  className="border-b border-slate-100 hover:bg-slate-50"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{row.source_name}</div>
                    <div className="text-[11px] text-slate-400">
                      {row.source_kind || "—"} · {row.source_id}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-slate-800">{row.channel_label}</div>
                    {row.channel_id ? (
                      <div className="font-mono text-[11px] text-slate-400">{row.channel_id}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{row.closed_trades}</td>
                  <td className="px-4 py-3 tabular-nums text-slate-600">
                    {row.wins} / {row.losses}
                    {row.breakeven ? (
                      <span className="ml-1 text-[11px] text-slate-400">平 {row.breakeven}</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 font-semibold tabular-nums text-slate-900">
                    {pct(row.win_rate)}
                  </td>
                  <td
                    className={`px-4 py-3 tabular-nums font-medium ${
                      row.total_pnl > 0
                        ? "text-emerald-600"
                        : row.total_pnl < 0
                          ? "text-rose-600"
                          : "text-slate-600"
                    }`}
                  >
                    {pnlText(row.total_pnl)}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-slate-500">{row.open_signals}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      className="text-brand-600 hover:underline"
                      onClick={() => void openDetail(row)}
                    >
                      按用户
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {selected ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setSelected(null)}
        >
          <div
            className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">按用户拆分</h2>
                <p className="mt-1 text-sm text-slate-500">
                  {selected.source_name} · {selected.channel_label}
                  {selected.channel_id ? (
                    <span className="ml-1 font-mono text-xs">({selected.channel_id})</span>
                  ) : null}
                </p>
              </div>
              <button
                type="button"
                className="text-slate-500 hover:text-slate-900"
                onClick={() => setSelected(null)}
              >
                关闭
              </button>
            </div>

            <div className="mt-4 overflow-hidden rounded-lg border border-slate-200">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-500">
                  <tr>
                    <th className="px-3 py-2">用户</th>
                    <th className="px-3 py-2">闭环</th>
                    <th className="px-3 py-2">胜 / 负</th>
                    <th className="px-3 py-2">胜率</th>
                    <th className="px-3 py-2">总 PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {detailLoading ? (
                    <tr>
                      <td colSpan={5} className="py-6 text-center text-slate-400">
                        加载中…
                      </td>
                    </tr>
                  ) : userRows.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-6 text-center text-slate-400">
                        暂无用户级闭环数据
                      </td>
                    </tr>
                  ) : (
                    userRows.map((u) => (
                      <tr key={u.user_id} className="border-t border-slate-100">
                        <td className="px-3 py-2">
                          <Link
                            to={`/users/${u.user_id}`}
                            className="text-brand-600 hover:underline"
                          >
                            {u.user_email || u.user_id.slice(0, 8)}
                          </Link>
                        </td>
                        <td className="px-3 py-2 tabular-nums">{u.closed_trades}</td>
                        <td className="px-3 py-2 tabular-nums">
                          {u.wins} / {u.losses}
                        </td>
                        <td className="px-3 py-2 font-medium tabular-nums">{pct(u.win_rate)}</td>
                        <td
                          className={`px-3 py-2 tabular-nums ${
                            u.total_pnl > 0
                              ? "text-emerald-600"
                              : u.total_pnl < 0
                                ? "text-rose-600"
                                : ""
                          }`}
                        >
                          {pnlText(u.total_pnl)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
