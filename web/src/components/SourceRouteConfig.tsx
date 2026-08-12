import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
import { brokerDisplayName, envLabel } from "../lib/brokerCredentials";
import { actionLabel } from "../lib/sourcePipeline";
import UiSelect from "./UiSelect";

type RouteRule = {
  id?: string;
  source_id: string;
  action: string;
  order_type_policy: string;
  signal_subtype?: string | null;
  broker?: string | null;
  account_id?: string | null;
  account_label?: string | null;
  default_quantity?: number | null;
};

export type BrokerOption = {
  key: string;
  broker: string;
  account_id: string;
  account_label: string;
  label: string;
};

type Props = {
  sourceId: string;
  routeRuleId?: string;
  /** 父级已有的路由规则，用于编辑时同步回填（避免仅依赖二次请求） */
  initialRule?: RouteRule | null;
  embedWizard?: boolean;
  brokerOptions?: BrokerOption[];
  brokerKey?: string;
  onBrokerKeyChange?: (key: string) => void;
  onGoToBrokers?: () => void;
  onSaved?: () => void;
  onError?: (message: string) => void;
  onCanFinishChange?: (can: boolean) => void;
};

function brokerKeyFromRule(rule: RouteRule, options: BrokerOption[]): string {
  if (!rule.broker) return "";
  const byLabel = rule.account_label ? `${rule.broker}:${rule.account_label}` : "";
  const byAccount = `${rule.broker}:${rule.account_id || ""}`;
  if (byLabel && options.some((o) => o.key === byLabel)) return byLabel;
  if (options.some((o) => o.key === byAccount)) return byAccount;
  const match = options.find(
    (o) =>
      o.broker === rule.broker &&
      ((rule.account_label && o.account_label === rule.account_label) ||
        (rule.account_id && o.account_id === rule.account_id)),
  );
  return match?.key || byLabel || byAccount;
}

function applyRuleToForm(
  rule: RouteRule,
  setLoadedRuleId: (id: string) => void,
  setAction: (v: string) => void,
  setPolicy: (v: string) => void,
  setQuantity: (v: string) => void,
  onBrokerKeyChange?: (key: string) => void,
  brokerOptions: BrokerOption[] = [],
) {
  setLoadedRuleId(rule.id || "");
  setAction(rule.action || "confirm_trade");
  setPolicy(rule.order_type_policy || "MKT_only");
  setQuantity(rule.default_quantity ? String(rule.default_quantity) : "");
  if (rule.broker && onBrokerKeyChange) {
    onBrokerKeyChange(brokerKeyFromRule(rule, brokerOptions));
  }
}

export type SourceRouteHandle = {
  save: () => Promise<boolean>;
  canFinish: () => boolean;
};

const SourceRouteConfig = forwardRef<SourceRouteHandle, Props>(function SourceRouteConfig(
  {
    sourceId,
    routeRuleId,
    initialRule = null,
    embedWizard,
    brokerOptions = [],
    brokerKey = "",
    onBrokerKeyChange,
    onGoToBrokers,
    onSaved,
    onError,
    onCanFinishChange,
  },
  ref,
) {
  const { t } = useTranslation();
  const [action, setAction] = useState(() => initialRule?.action || "confirm_trade");
  const [policy, setPolicy] = useState(() => initialRule?.order_type_policy || "MKT_only");
  const [quantity, setQuantity] = useState(() =>
    initialRule?.default_quantity ? String(initialRule.default_quantity) : "",
  );
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [canAutoTrade, setCanAutoTrade] = useState(false);
  const [loadedRuleId, setLoadedRuleId] = useState(() => initialRule?.id || "");
  const loadedBrokerRef = useRef<Pick<RouteRule, "broker" | "account_id" | "account_label"> | null>(
    initialRule?.broker
      ? {
          broker: initialRule.broker,
          account_id: initialRule.account_id,
          account_label: initialRule.account_label,
        }
      : null,
  );
  /** 每个规则只强制回填券商一次，避免覆盖用户之后的手动改选 */
  const brokerAppliedTokenRef = useRef("");

  useEffect(() => {
    api
      .get("/config/entitlements")
      .then((r) => setCanAutoTrade(Boolean(r.data?.features?.auto_trade)))
      .catch(() => setCanAutoTrade(false));
  }, []);

  useEffect(() => {
    if (!canAutoTrade && (action === "auto_trade" || action === "both")) {
      setAction("confirm_trade");
    }
  }, [canAutoTrade, action]);

  const actionOptions = useMemo(() => {
    const base = [
      { value: "notify_only", label: t("pipeline.actionNotify") },
      { value: "confirm_trade", label: t("pipeline.actionConfirm") },
    ];
    if (!canAutoTrade) return base;
    return [
      ...base,
      { value: "auto_trade", label: t("pipeline.actionAuto") },
      { value: "both", label: t("pipeline.actionBoth") },
    ];
  }, [t, canAutoTrade]);

  const policyOptions = useMemo(
    () => [
      { value: "MKT_only", label: t("pipeline.policyMkt") },
      { value: "LMT_then_MKT", label: t("pipeline.policyLmt") },
    ],
    [t],
  );

  const brokerSelectOptions = useMemo(
    () => brokerOptions.map((o) => ({ value: o.key, label: o.label })),
    [brokerOptions],
  );

  const selectedBroker = brokerOptions.find((o) => o.key === brokerKey);

  const hydrateFromRule = useCallback(
    (rule: RouteRule) => {
      const token = `${rule.id || ""}|${rule.broker || ""}|${rule.account_label || ""}|${rule.account_id || ""}`;
      if (brokerAppliedTokenRef.current !== token) {
        brokerAppliedTokenRef.current = "";
      }
      loadedBrokerRef.current = {
        broker: rule.broker,
        account_id: rule.account_id,
        account_label: rule.account_label,
      };
      applyRuleToForm(
        rule,
        setLoadedRuleId,
        setAction,
        setPolicy,
        setQuantity,
        onBrokerKeyChange,
        brokerOptions,
      );
    },
    [brokerOptions, onBrokerKeyChange],
  );

  // 编辑时先用父级规则回填，再拉最新规则校正
  useEffect(() => {
    brokerAppliedTokenRef.current = "";
    if (initialRule && (initialRule.id === routeRuleId || initialRule.source_id === sourceId)) {
      hydrateFromRule(initialRule);
    }
    let cancelled = false;
    api
      .get("/config/route-rules")
      .then((r) => {
        if (cancelled) return;
        const rules = r.data as RouteRule[];
        const rule = routeRuleId
          ? rules.find((x) => x.id === routeRuleId)
          : rules.find((x) => x.source_id === sourceId);
        if (rule) hydrateFromRule(rule);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅在切换流水线时回填
  }, [sourceId, routeRuleId, initialRule?.id]);

  // 券商选项就绪后，按规则强制对齐一次（修复默认选中列表第一项的竞态）
  useEffect(() => {
    if (!brokerOptions.length || !onBrokerKeyChange || !loadedBrokerRef.current?.broker) return;
    const meta = loadedBrokerRef.current;
    const token = `${loadedRuleId}|${meta.broker || ""}|${meta.account_label || ""}|${meta.account_id || ""}`;
    if (brokerAppliedTokenRef.current === token) return;
    const desired = brokerKeyFromRule(
      {
        source_id: sourceId,
        action: "confirm_trade",
        order_type_policy: "MKT_only",
        ...meta,
      },
      brokerOptions,
    );
    if (!desired) return;
    onBrokerKeyChange(desired);
    brokerAppliedTokenRef.current = token;
  }, [brokerOptions, onBrokerKeyChange, loadedRuleId, sourceId]);

  const parsedQuantity = useMemo(() => {
    const n = parseInt(quantity.trim(), 10);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [quantity]);

  const canFinish = useCallback(() => {
    if (embedWizard) return Boolean(selectedBroker);
    return true;
  }, [embedWizard, selectedBroker]);

  const save = useCallback(async (): Promise<boolean> => {
    if (embedWizard && !selectedBroker) {
      const msg = t("execPipeline.brokerRequired");
      setError(msg);
      onError?.(msg);
      return false;
    }
    setBusy(true);
    setError("");
    onError?.("");
    setSaved(false);
    try {
      const res = await api.put("/config/route-rules", {
        ...(loadedRuleId ? { id: loadedRuleId } : {}),
        source_id: sourceId,
        action,
        order_type_policy: policy,
        default_quantity: parsedQuantity,
        ...(embedWizard && selectedBroker
          ? {
              broker: selectedBroker.broker,
              account_id: selectedBroker.account_id,
              account_label: selectedBroker.account_label,
            }
          : {}),
      });
      const savedId = (res.data as { id?: string })?.id;
      if (savedId) setLoadedRuleId(savedId);
      setSaved(true);
      onSaved?.();
      return true;
    } catch {
      const msg = t("pipeline.saveFailed");
      setError(msg);
      onError?.(msg);
      return false;
    } finally {
      setBusy(false);
    }
  }, [
    loadedRuleId,
    sourceId,
    action,
    policy,
    parsedQuantity,
    embedWizard,
    selectedBroker,
    onSaved,
    onError,
    t,
  ]);

  useImperativeHandle(ref, () => ({ save, canFinish }), [save, canFinish]);

  useEffect(() => {
    onCanFinishChange?.(canFinish());
  }, [canFinish, onCanFinishChange]);

  const actionHint =
    action === "notify_only"
      ? t("pipeline.execModeNotifyHint")
      : action === "confirm_trade"
        ? t("pipeline.execModeConfirmHint")
        : action === "auto_trade"
          ? t("pipeline.execModeAutoHint")
          : t("pipeline.execModeBothHint");

  const quantityField = (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-slate-500">{t("pipeline.orderQuantity")}</label>
      <input
        type="number"
        min={1}
        className="input w-full text-sm"
        placeholder={t("pipeline.orderQuantityPlaceholder")}
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
      />
      <p className="text-xs text-slate-500">{t("pipeline.orderQuantityHint")}</p>
    </div>
  );

  if (embedWizard) {
    return (
      <div className="space-y-5">
        <div className="space-y-2">
          <p className="text-sm text-slate-600">{t("execPipeline.stepExecuteHint")}</p>
          <p className="rounded-lg border border-brand-100 bg-brand-50/60 px-3 py-2 text-xs text-brand-800">
            {t("execPipeline.saveOnFinish")}
          </p>
        </div>
        <div className="space-y-5 rounded-xl border border-brand-100 bg-brand-50/40 p-4 lg:p-5">
          <div className="grid gap-4 lg:grid-cols-2 lg:gap-6">
            <div className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white">
                1
              </span>
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="text-sm font-medium text-slate-800">{t("pipeline.execMode")}</p>
                <p className="text-sm leading-relaxed text-slate-600">{t("execPipeline.actionStepGuideA")}</p>
              </div>
            </div>
            <div className="space-y-3">
              <UiSelect value={action} onChange={setAction} options={actionOptions} />
              <p className="text-xs text-slate-500">{actionHint}</p>
              {!canAutoTrade ? (
                <p className="text-xs text-brand-700">{t("dashboard.upgradeForTrade")}</p>
              ) : null}
            </div>
          </div>

          <div className="grid gap-4 border-t border-brand-100 pt-5 lg:grid-cols-2 lg:gap-6">
            <div className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white">
                2
              </span>
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="text-sm font-medium text-slate-800">{t("pipeline.orderPolicy")}</p>
                <p className="text-sm leading-relaxed text-slate-600">{t("execPipeline.actionStepPolicyHint")}</p>
              </div>
            </div>
            <UiSelect value={policy} onChange={setPolicy} options={policyOptions} />
          </div>

          <div className="grid gap-4 border-t border-brand-100 pt-5 lg:grid-cols-2 lg:gap-6">
            <div className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white">
                3
              </span>
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="text-sm font-medium text-slate-800">{t("pipeline.orderQuantity")}</p>
                <p className="text-sm leading-relaxed text-slate-600">{t("execPipeline.quantityStepHint")}</p>
              </div>
            </div>
            {quantityField}
          </div>

          <div className="grid gap-4 border-t border-brand-100 pt-5 lg:grid-cols-2 lg:gap-6">
            <div className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500 text-xs font-bold text-white">
                4
              </span>
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="text-sm font-medium text-slate-800">{t("execPipeline.step.broker")}</p>
                <p className="text-sm leading-relaxed text-slate-600">{t("execPipeline.stepBrokerHint")}</p>
              </div>
            </div>
            <div className="space-y-2">
              {brokerOptions.length === 0 ? (
                <div className="space-y-2">
                  <p className="text-sm text-slate-500">{t("execPipeline.noBrokerYet")}</p>
                  {onGoToBrokers ? (
                    <button type="button" className="btn-secondary text-sm" onClick={onGoToBrokers}>
                      {t("execPipeline.goBrokers")}
                    </button>
                  ) : null}
                </div>
              ) : (
                <UiSelect
                  value={brokerKey}
                  onChange={(v) => onBrokerKeyChange?.(v)}
                  options={brokerSelectOptions}
                  placeholder={t("execPipeline.pickBroker")}
                />
              )}
              {selectedBroker ? (
                <p className="text-xs text-slate-500">
                  {t("execPipeline.selectedBroker", { broker: selectedBroker.label })}
                </p>
              ) : null}
              {error ? <p className="text-xs text-loss">{error}</p> : null}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-500">{t("pipeline.execMode")}</label>
          <UiSelect value={action} onChange={setAction} options={actionOptions} />
          <p className="text-xs text-slate-500">{actionHint}</p>
          {!canAutoTrade ? (
            <p className="text-xs text-brand-700">{t("dashboard.upgradeForTrade")}</p>
          ) : null}
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-500">{t("pipeline.orderPolicy")}</label>
          <UiSelect value={policy} onChange={setPolicy} options={policyOptions} />
        </div>
      </div>
      {quantityField}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary text-sm" disabled={busy} onClick={() => void save()}>
          {t("pipeline.saveAction")}
        </button>
        <span className="text-xs text-slate-500">
          {t("pipeline.currentAction", { action: actionLabel(action, t) })}
        </span>
        {saved ? <span className="text-xs text-profit">{t("pipeline.saved")}</span> : null}
        {error ? <span className="text-xs text-loss">{error}</span> : null}
      </div>
    </div>
  );
});

const AGENT_BROKERS = new Set(["ibkr", "futu"]);

export async function loadBrokerOptions(t: (key: string) => string): Promise<BrokerOption[]> {
  const [bindingsRes, credsRes] = await Promise.all([
    api.get("/broker-bindings"),
    api.get("/broker-credentials").catch(() => ({ data: [] })),
  ]);
  const options: BrokerOption[] = [];
  for (const c of credsRes.data as {
    broker: string;
    account_id: string;
    label?: string;
    env?: string;
  }[]) {
    const accountLabel = (c.label || c.account_id || "").trim();
    if (!accountLabel) continue;
    const name = brokerDisplayName(c.broker, t);
    const env = c.env ? envLabel(c.broker, c.env, t, c.account_id) : "";
    options.push({
      key: `${c.broker}:${accountLabel}`,
      broker: c.broker,
      account_id: c.account_id,
      account_label: accountLabel,
      label: env ? `${name} · ${accountLabel} (${env})` : `${name} · ${accountLabel}`,
    });
  }
  for (const b of bindingsRes.data as {
    broker: string;
    account_id: string;
    label?: string;
    enabled?: boolean;
  }[]) {
    if (!AGENT_BROKERS.has((b.broker || "").toLowerCase())) continue;
    const accountLabel = (b.label || b.account_id || "").trim();
    if (!accountLabel) continue;
    const key = `${b.broker}:${accountLabel}`;
    if (!options.some((o) => o.key === key)) {
      options.push({
        key,
        broker: b.broker,
        account_id: b.account_id || "",
        account_label: accountLabel,
        label: `${brokerDisplayName(b.broker, t)} · ${accountLabel}`,
      });
    }
  }
  return options;
}

export default SourceRouteConfig;
