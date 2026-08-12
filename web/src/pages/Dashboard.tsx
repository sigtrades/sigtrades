import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import AppLayout, { NavId } from "../components/AppLayout";
import BrokerConfigSection from "../components/BrokerConfigSection";
import RelayAgentSection from "../components/RelayAgentSection";
import SourcesSection from "../components/SourcesSection";
import Toast from "../components/Toast";
import AccountSettingsSection from "../components/AccountSettingsSection";
import AppSettingsSection from "../components/AppSettingsSection";
import MembershipBillingSection from "../components/MembershipBillingSection";
import OverviewMembershipCard from "../components/OverviewMembershipCard";
import OnboardingWizard from "../components/OnboardingWizard";
import RiskSettingsSection from "../components/RiskSettingsSection";
import ExecutionPipelinesSection from "../components/ExecutionPipelinesSection";
import SignalExecutionGroup from "../components/SignalExecutionGroup";
import { createWebhookIngestToken } from "../lib/webhooks";
import api from "../lib/api";
import { isEtToday } from "../lib/datetime";
import {
  buildPipelineStatuses,
  mergePipelineSources,
} from "../lib/sourcePipeline";
import { groupExecutionsBySignal } from "../lib/executionGroups";
import { normalizeExecutionsResponse, type ExecutionRecord } from "../lib/executions";
import { hasInFlightExecutions } from "../lib/useExecutionPolling";
import { useSoundNotifications } from "../lib/useSoundNotifications";
import { useAuth } from "../store/auth";
import { DEFAULT_APP_PATH, isValidAppSection, navIdFromPath, navPath } from "../lib/appRoutes";

type Webhook = { url_path: string; source_id: string; token: string; label?: string };
type RouteRule = {
  source_id: string;
  action: string;
  order_type_policy: string;
  signal_subtype?: string;
  broker?: string | null;
  account_id?: string | null;
};
type ParseRule = { source_id: string; parse_mode: string; label?: string };
type BrokerBinding = { broker: string; account_id: string; label?: string; enabled?: boolean };
type BrokerCredential = { broker: string; account_id: string; label?: string; env?: string };
type Execution = ExecutionRecord;
type TelegramSource = { source_id: string; name: string; chat_ids: string[] };
type DiscordSource = {
  source_id: string;
  name: string;
  channel_ids: string[];
  channel_labels?: Record<string, string>;
  application_id?: string | null;
  has_bot_token: boolean;
  bridge_mode?: string;
  is_active?: boolean;
};

export default function Dashboard() {
  const { t } = useTranslation();
  const { user, fetchMe } = useAuth();
  const { section } = useParams<{ section: string }>();
  const navigate = useNavigate();
  const nav: NavId = navIdFromPath(`/app/${section ?? ""}`);

  useEffect(() => {
    if (section && !isValidAppSection(section)) {
      navigate(DEFAULT_APP_PATH, { replace: true });
    }
  }, [section, navigate]);
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [agentOnline, setAgentOnline] = useState(false);
  const [killSwitch, setKillSwitch] = useState(false);
  const [soundNotifications, setSoundNotifications] = useState(false);
  const [routeRules, setRouteRules] = useState<RouteRule[]>([]);
  const [parseRules, setParseRules] = useState<ParseRule[]>([]);
  const [brokerBindings, setBrokerBindings] = useState<BrokerBinding[]>([]);
  const [brokerCredentials, setBrokerCredentials] = useState<BrokerCredential[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [discordSources, setDiscordSources] = useState<DiscordSource[]>([]);
  const [telegramSources, setTelegramSources] = useState<TelegramSource[]>([]);
  const [dcLabel, setDcLabel] = useState("My Discord");
  const [dcUserToken, setDcUserToken] = useState("");
  const [routeSourceId, setRouteSourceId] = useState("");
  const [routeAction, setRouteAction] = useState("auto_trade");
  const [routePolicy, setRoutePolicy] = useState("MKT_only");
  const [discordCount, setDiscordCount] = useState(0);
  const [telegramCount, setTelegramCount] = useState(0);
  const [brokerCount, setBrokerCount] = useState(0);
  const [brokerCredCount, setBrokerCredCount] = useState(0);
  const [tgChats, setTgChats] = useState("");
  const [tgLabel, setTgLabel] = useState("My Telegram");
  const [onboardingStep, setOnboardingStep] = useState(0);
  const [toast, setToast] = useState("");
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  const EXECUTIONS_PAGE_SIZE = 20;
  const [execPage, setExecPage] = useState(0);
  const [execPageData, setExecPageData] = useState(() =>
    normalizeExecutionsResponse([]),
  );
  const [execPageLoading, setExecPageLoading] = useState(false);

  const loadExecutionsPage = useCallback(async (page: number) => {
    setExecPageLoading(true);
    try {
      const res = await api.get("/config/executions", {
        params: { limit: EXECUTIONS_PAGE_SIZE, offset: page * EXECUTIONS_PAGE_SIZE },
      });
      setExecPageData(normalizeExecutionsResponse(res.data));
      setExecPage(page);
    } finally {
      setExecPageLoading(false);
    }
  }, []);

  const reload = async () => {
    const [
      webhooksRes,
      agentRes,
      meRes,
      routeRes,
      parseRes,
      execRes,
      bindingsRes,
      discordRes,
      telegramRes,
      credsRes,
    ] = await Promise.all([
      api.get("/config/webhooks"),
      api.get("/config/agent-status"),
      api.get("/me"),
      api.get("/config/route-rules"),
      api.get("/config/parse-rules").catch(() => ({ data: [] })),
      api.get("/config/executions", { params: { limit: 50, offset: 0 } }),
      api.get("/broker-bindings").catch(() => ({ data: [] })),
      api.get("/config/discord-sources").catch(() => ({ data: [] })),
      api.get("/config/telegram-sources").catch(() => ({ data: [] })),
      api.get("/broker-credentials").catch(() => ({ data: [] })),
    ]);
    setWebhooks(webhooksRes.data);
    setAgentOnline(agentRes.data.online);
    setKillSwitch(meRes.data.kill_switch);
    setSoundNotifications(Boolean(meRes.data.sound_notifications));
    setRouteRules(routeRes.data);
    setParseRules(parseRes.data);
    setExecutions(normalizeExecutionsResponse(execRes.data).items);
    setBrokerBindings(bindingsRes.data);
    setBrokerCredentials(
      (credsRes.data as BrokerCredential[]).map((c) => ({
        broker: c.broker,
        account_id: c.account_id,
        label: c.label,
        env: c.env,
      })),
    );
    setDiscordSources(discordRes.data);
    setDiscordCount(discordRes.data.length);
    setTelegramSources(telegramRes.data);
    setTelegramCount(telegramRes.data.length);
    setBrokerCount(bindingsRes.data.length);
    setBrokerCredCount(credsRes.data.length);
  };

  useEffect(() => {
    fetchMe();
    reload();
  }, [fetchMe]);

  // Agent 在线状态依赖 relay presence，登录/重连后需轮询刷新（仅靠进页一次会严重滞后）
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await api.get("/config/agent-status");
        if (!cancelled) setAgentOnline(Boolean(res.data?.online));
      } catch {
        /* ignore */
      }
    };
    const timer = window.setInterval(() => void tick(), 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const inFlightExecutions = useMemo(() => hasInFlightExecutions(executions), [executions]);
  const execPageInFlight = useMemo(
    () => hasInFlightExecutions(execPageData.items),
    [execPageData.items],
  );

  useEffect(() => {
    if (!inFlightExecutions) return;
    const timer = window.setInterval(async () => {
      const execRes = await api.get("/config/executions", { params: { limit: 50, offset: 0 } });
      setExecutions(normalizeExecutionsResponse(execRes.data).items);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [inFlightExecutions]);

  useEffect(() => {
    if (nav !== "executions") return;
    void loadExecutionsPage(execPage);
  }, [nav, execPage, loadExecutionsPage]);

  useEffect(() => {
    if (nav !== "executions" || !execPageInFlight) return;
    const timer = window.setInterval(() => void loadExecutionsPage(execPage), 2000);
    return () => window.clearInterval(timer);
  }, [nav, execPageInFlight, execPage, loadExecutionsPage]);

  useSoundNotifications(soundNotifications);

  useEffect(() => {
    if (searchParams.get("upgraded") === "1") {
      navigate("/membership/success", { replace: true });
      return;
    }
    if (searchParams.get("discord") === "connected") {
      setToast(t("dashboard.discordConnected"));
      setSearchParams({}, { replace: true });
      reload();
    }
    if (searchParams.get("schwab") === "connected") {
      setToast(t("dashboard.schwabConnected"));
      setSearchParams({}, { replace: true });
      reload();
    } else if (searchParams.get("schwab") === "error") {
      setToast(
        t("dashboard.schwabConnectFailed", {
          reason: searchParams.get("reason") || "unknown",
        }),
      );
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, navigate, setSearchParams, t, reload]);

  const createWebhook = async (label?: string) => {
    const base = import.meta.env.VITE_INGEST_PUBLIC_URL || "http://localhost:8082";
    const result = await createWebhookIngestToken(label || "Webhook", base);
    await reload();
    return result;
  };

  const ingestBase = import.meta.env.VITE_INGEST_PUBLIC_URL || "http://localhost:8082";

  const createDiscordMonitor = async (payload: {
    label: string;
    user_token?: string;
    channel_ids: string[];
    channel_labels: Record<string, string>;
    guild_id?: string;
  }) => {
    await api.post("/config/discord-bridge-source", {
      ...payload,
      action: "confirm_trade",
      order_type_policy: "MKT_only",
    });
    setToast(t("dashboard.discordSaved"));
    reload();
  };

  const createTelegramSource = async (label: string, chatIds: string[]) => {
    if (!chatIds.length) return;
    await api.post("/config/telegram-source", {
      label,
      chat_ids: chatIds,
      action: routeAction,
      order_type_policy: routePolicy,
    });
    setTgChats("");
    setTgLabel("My Telegram");
    setToast(t("sourcesPage.telegramCreated"));
    reload();
  };

  const pipelineSources = useMemo(
    () => mergePipelineSources(discordSources, routeRules, parseRules, webhooks, telegramSources),
    [discordSources, routeRules, parseRules, webhooks, telegramSources],
  );

  const pipelineStatuses = useMemo(
    () =>
      buildPipelineStatuses(
        pipelineSources,
        parseRules,
        routeRules,
        brokerBindings,
        executions,
        brokerCredentials,
      ),
    [pipelineSources, parseRules, routeRules, brokerBindings, executions, brokerCredentials],
  );

  // 「已关联流水线」= 已有路由规则；券商账号是否仍可用是流水线就绪问题，不抹掉关联标记
  const linkedPipelineSourceIds = useMemo(
    () => new Set(pipelineStatuses.filter((p) => p.hasAction).map((p) => p.sourceId)),
    [pipelineStatuses],
  );

  const tradesToday = useMemo(
    () => executions.filter((e) => isEtToday(e.created_at)).length,
    [executions],
  );

  const totalPnl = useMemo(
    () => executions.reduce((sum, e) => sum + (e.realized_pnl ?? 0), 0),
    [executions],
  );

  const totalBrokers = brokerCount + brokerCredCount;
  const hasOnboardBroker = totalBrokers > 0;
  const hasOnboardSource = pipelineStatuses.some((p) => p.connected);
  const hasOnboardParse = pipelineStatuses.some((p) => p.hasParse);
  const hasOnboardAction = pipelineStatuses.some((p) => p.hasAction);

  const pageTitle = t(`console.nav.${nav}`);
  const pageSubtitle = t(`console.subtitle.${nav}`);

  const confirmExecution = async (
    signalId: string,
    sourceId: string,
    accountLabel?: string | null,
  ) => {
    setConfirmBusy(true);
    try {
      await api.post(`/config/executions/${encodeURIComponent(signalId)}/confirm`, {
        source_id: sourceId,
        ...(accountLabel ? { account_label: accountLabel } : {}),
      });
      await reload();
      if (nav === "executions") await loadExecutionsPage(execPage);
    } finally {
      setConfirmBusy(false);
    }
  };

  const rejectExecution = async (signalId: string, sourceId: string, accountLabel?: string | null) => {
    setConfirmBusy(true);
    try {
      await api.post(`/config/executions/${encodeURIComponent(signalId)}/reject`, {
        source_id: sourceId,
        ...(accountLabel ? { account_label: accountLabel } : {}),
      });
      await reload();
      if (nav === "executions") await loadExecutionsPage(execPage);
    } finally {
      setConfirmBusy(false);
    }
  };

  const renderExecutionsList = (items: Execution[]) => (
    <div className="space-y-3">
      {groupExecutionsBySignal(
        items.map((e) => ({
          signal_id: e.signal_id,
          source_id: e.source_id,
          status: e.status,
          broker: e.broker,
          account_label: e.account_label,
          fill_price: e.fill_price,
          order_id: e.order_id,
          created_at: e.created_at,
          signal: e.signal,
          detail: e.detail,
        })),
      ).map((group) => (
        <SignalExecutionGroup
          key={group.signalId}
          group={group}
          confirmBusy={confirmBusy}
          onConfirm={(id, accountLabel) => {
            const sourceId = group.sourceId || items.find((x) => x.signal_id === id)?.source_id || "";
            void confirmExecution(id, sourceId, accountLabel);
          }}
          onReject={(id, accountLabel) => {
            const sourceId = group.sourceId || items.find((x) => x.signal_id === id)?.source_id || "";
            void rejectExecution(id, sourceId, accountLabel);
          }}
        />
      ))}
      {items.length === 0 && <p className="py-4 text-sm text-slate-500">{t("dashboard.empty")}</p>}
    </div>
  );

  const execTotalPages = Math.max(1, Math.ceil(execPageData.total / EXECUTIONS_PAGE_SIZE));

  return (
    <AppLayout title={pageTitle} subtitle={pageSubtitle}>
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}

      {nav === "overview" && (
        <div className="space-y-6">
          <div className="overflow-hidden rounded-[1.5rem] bg-slate-950 p-6 text-white shadow-pop">
            <div className="grid gap-6 lg:grid-cols-[1.2fr_.8fr] lg:items-center">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wide text-brand-300">{t("console.commandCenter")}</p>
                <h2 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">{t("console.commandTitle")}</h2>
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-300">{t("console.commandHint")}</p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="text-slate-400">{t("console.kpi.pipelines")}</p>
                  <p className="mt-2 text-2xl font-bold">{pipelineStatuses.length}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="text-slate-400">{t("console.kpi.brokers")}</p>
                  <p className="mt-2 text-2xl font-bold">{totalBrokers}</p>
                </div>
              </div>
            </div>
          </div>

          <OverviewMembershipCard />

          {/* 总览引导：先券商，再流水线 */}
          {!hasOnboardBroker ? (
            <section className="overflow-hidden rounded-2xl border border-brand-100 bg-gradient-to-br from-brand-50 to-white p-6 shadow-card">
              <p className="text-sm font-semibold uppercase tracking-wide text-brand-600">
                {t("onboarding.eyebrow")}
              </p>
              <h2 className="mt-1 text-xl font-bold text-slate-950">{t("onboarding.brokerFirstTitle")}</h2>
              <p className="mt-2 max-w-2xl text-sm text-slate-600">{t("onboarding.brokerFirstHint")}</p>
              <ol className="mt-4 flex flex-wrap items-center gap-2 text-xs font-medium text-slate-500">
                <li className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-white px-2.5 py-1 text-brand-700">
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-brand-600 text-[10px] font-bold text-white">
                    1
                  </span>
                  {t("onboarding.brokerTitle")}
                </li>
                <span className="text-slate-300">→</span>
                <li className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/70 px-2.5 py-1">
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-slate-200 text-[10px] font-bold text-slate-600">
                    2
                  </span>
                  {t("onboarding.pipelineTitle")}
                </li>
              </ol>
              <button
                type="button"
                className="btn-primary mt-5"
                onClick={() => navigate(navPath("brokers"))}
              >
                {t("onboarding.brokerFirstCta")}
              </button>
              <p className="mt-3 text-xs text-slate-500">{t("onboarding.agentNote")}</p>
            </section>
          ) : pipelineStatuses.length === 0 ? (
            <ExecutionPipelinesSection
              pipelines={pipelineStatuses}
              discordSources={discordSources}
              webhooks={webhooks}
              telegramSources={telegramSources}
              ingestBase={ingestBase}
              routeRules={routeRules}
              onReload={reload}
              onGoToBrokers={() => navigate(navPath("brokers"))}
              onCreateWebhook={createWebhook}
              onWizardComplete={async () => {
                await reload();
              }}
            />
          ) : (
            <>
              <OnboardingWizard
                step={onboardingStep}
                onStep={(step) => {
                  setOnboardingStep(step);
                  // 0=券商，其后均为流水线相关
                  navigate(navPath(step === 0 ? "brokers" : "pipelines"));
                }}
                hasBroker={hasOnboardBroker}
                hasSource={hasOnboardSource}
                hasParse={hasOnboardParse}
                hasAction={hasOnboardAction}
              />

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="kpi-card">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("console.kpi.agent")}</p>
                    <span className={`h-2.5 w-2.5 rounded-full ${agentOnline ? "bg-profit shadow-[0_0_0_4px_rgb(16_185_129_/_0.12)]" : "bg-slate-300"}`} />
                  </div>
                  <p className={`mt-3 text-2xl font-bold tracking-tight ${agentOnline ? "text-profit" : "text-slate-400"}`}>
                    {agentOnline ? t("dashboard.online") : t("dashboard.offline")}
                  </p>
                </div>
                <div className="kpi-card">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("console.kpi.tradesToday")}</p>
                  <p className="mt-3 text-2xl font-bold tracking-tight text-slate-950">{tradesToday}</p>
                  <p className="mt-1 text-xs text-slate-400">{t("common.timezoneEt")}</p>
                </div>
                <div className="kpi-card">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("console.kpi.realizedPnl")}</p>
                  <p className={`mt-3 text-2xl font-bold tracking-tight ${totalPnl >= 0 ? "text-profit" : "text-loss"}`}>
                    {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(2)}
                  </p>
                </div>
                <div className="kpi-card">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("console.kpi.killSwitch")}</p>
                  <p className={`mt-3 text-2xl font-bold tracking-tight ${killSwitch ? "text-loss" : "text-profit"}`}>
                    {killSwitch ? "ON" : "OFF"}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">{killSwitch ? t("execPipeline.paused") : t("dashboard.online")}</p>
                </div>
              </div>
              <div className="card overflow-hidden p-0">
                <div className="border-b border-slate-100 px-6 py-4">
                  <div>
                    <p className="section-eyebrow">{t("console.nav.executions")}</p>
                    <h2 className="mt-1 font-semibold text-slate-900">{t("dashboard.executions")}</h2>
                  </div>
                </div>
                <div className="px-6 py-4">{renderExecutionsList(executions.slice(0, 10))}</div>
                <div className="flex justify-end border-t border-slate-100 bg-slate-50/60 px-6 py-3">
                  <button type="button" className="btn-ghost" onClick={() => navigate(navPath("executions"))}>
                    {t("dashboard.viewAllExecutions")} →
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {nav === "pipelines" && (
        <ExecutionPipelinesSection
          pipelines={pipelineStatuses}
          discordSources={discordSources}
          webhooks={webhooks}
          telegramSources={telegramSources}
          ingestBase={ingestBase}
          routeRules={routeRules}
          onReload={reload}
          onGoToBrokers={() => navigate(navPath("brokers"))}
          onCreateWebhook={createWebhook}
          onWizardComplete={async () => {
            await reload();
          }}
        />
      )}

      {nav === "sources" && (
        <SourcesSection
          ingestBase={ingestBase}
          webhooks={webhooks}
          discordSources={discordSources}
          telegramSources={telegramSources}
          linkedSourceIds={linkedPipelineSourceIds}
          dcLabel={dcLabel}
          dcUserToken={dcUserToken}
          onDcLabelChange={setDcLabel}
          onDcUserTokenChange={setDcUserToken}
          onCreateWebhook={createWebhook}
          onCreateDiscordBridge={createDiscordMonitor}
          onDiscordSourcesChanged={reload}
          onCreateTelegram={createTelegramSource}
          onGoToPipelines={() => navigate(navPath("pipelines"))}
        />
      )}

      {nav === "brokers" && (
        <div className="space-y-6">
          <BrokerConfigSection onSaved={() => { setBrokerCount((c) => c + 1); reload(); }} />
          <RelayAgentSection agentOnline={agentOnline} />
        </div>
      )}

      {nav === "risk" && <RiskSettingsSection />}

      {nav === "executions" && (
        <div className="card">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold">{t("dashboard.executions")}</h2>
            <p className="text-sm text-slate-500">{t("dashboard.execTotal", { total: execPageData.total })}</p>
          </div>
          <div className="mt-3">
            {execPageLoading ? (
              <p className="py-4 text-sm text-slate-500">{t("common.loading")}</p>
            ) : (
              renderExecutionsList(execPageData.items)
            )}
          </div>
          {execPageData.total > EXECUTIONS_PAGE_SIZE && (
            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4">
              <button
                type="button"
                disabled={execPage === 0 || execPageLoading}
                onClick={() => setExecPage((p) => Math.max(0, p - 1))}
                className="btn-secondary text-sm"
              >
                {t("dashboard.execPrev")}
              </button>
              <span className="text-sm text-slate-500">
                {t("dashboard.execPage", { page: execPage + 1, pages: execTotalPages })}
              </span>
              <button
                type="button"
                disabled={(execPage + 1) * EXECUTIONS_PAGE_SIZE >= execPageData.total || execPageLoading}
                onClick={() => setExecPage((p) => p + 1)}
                className="btn-secondary text-sm"
              >
                {t("dashboard.execNext")}
              </button>
            </div>
          )}
        </div>
      )}

      {nav === "account" && <AccountSettingsSection />}

      {nav === "membership" && <MembershipBillingSection />}

      {nav === "settings" && (
        <AppSettingsSection
          killSwitch={killSwitch}
          soundNotifications={soundNotifications}
          onKillSwitchChanged={setKillSwitch}
          onSoundNotificationsChanged={setSoundNotifications}
        />
      )}
    </AppLayout>
  );
}



