import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { normalizeExecutionsResponse } from "../lib/executions";
import { groupExecutionsBySignal } from "../lib/executionGroups";
import { hasInFlightExecutions } from "../lib/useExecutionPolling";
import SignalExecutionGroup from "./SignalExecutionGroup";
import type { TimelineExecution } from "./SignalTimeline";

type Props = {
  sourceId: string;
  onAction?: () => void;
};

export default function SourceSignalFeed({ sourceId, onAction }: Props) {
  const { t } = useTranslation();
  const [items, setItems] = useState<TimelineExecution[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/config/executions", { params: { source_id: sourceId, limit: 20 } })
      .then((r) => setItems(normalizeExecutionsResponse(r.data).items))
      .catch(() => setItems([]));
  }, [sourceId]);

  const inFlight = useMemo(() => hasInFlightExecutions(items), [items]);

  useEffect(() => {
    load();
    const intervalMs = inFlight ? 2000 : 15000;
    const timer = window.setInterval(load, intervalMs);
    return () => window.clearInterval(timer);
  }, [load, inFlight]);

  const confirm = async (signalId: string, accountLabel?: string | null) => {
    setBusy(true);
    try {
      await api.post(`/config/executions/${encodeURIComponent(signalId)}/confirm`, {
        source_id: sourceId,
        ...(accountLabel ? { account_label: accountLabel } : {}),
      });
      load();
      onAction?.();
    } finally {
      setBusy(false);
    }
  };

  const reject = async (signalId: string, accountLabel?: string | null) => {
    setBusy(true);
    try {
      await api.post(`/config/executions/${encodeURIComponent(signalId)}/reject`, {
        source_id: sourceId,
        ...(accountLabel ? { account_label: accountLabel } : {}),
      });
      load();
      onAction?.();
    } finally {
      setBusy(false);
    }
  };

  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
        {t("pipeline.noSignalsYet")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {groupExecutionsBySignal(items).map((group) => (
        <SignalExecutionGroup
          key={group.signalId}
          group={group}
          confirmBusy={busy}
          onConfirm={confirm}
          onReject={(id, label) => void reject(id, label)}
        />
      ))}
    </div>
  );
}
