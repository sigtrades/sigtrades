import { useEffect, useRef } from "react";
import type { TimelineExecution } from "../components/SignalTimeline";
import { shouldStopTrackingExecution } from "./executionFlow";

/** 弹窗打开且执行未结束时定时刷新；关闭、终态或同步超时后自动清除定时器。 */
export function useExecutionPolling(
  active: boolean,
  execution: Pick<TimelineExecution, "signal_id" | "status" | "created_at" | "detail" | "order_id">,
  onPoll: () => void | Promise<void>,
  intervalMs = 2000,
): void {
  const onPollRef = useRef(onPoll);
  onPollRef.current = onPoll;

  useEffect(() => {
    if (!active || !execution.signal_id) return;
    if (shouldStopTrackingExecution(execution as TimelineExecution)) return;

    let cancelled = false;
    const tick = () => {
      if (!cancelled) void onPollRef.current();
    };

    tick();
    const timer = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [active, execution, intervalMs]);
}

export function hasInFlightExecutions(
  items: Pick<TimelineExecution, "status" | "created_at" | "detail" | "order_id">[],
): boolean {
  return items.some((e) => {
    if (e.status.toUpperCase() === "PENDING_CONFIRM") return false;
    return !shouldStopTrackingExecution(e as TimelineExecution);
  });
}
