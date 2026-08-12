export type GatewayStatus = {
  broker: string;
  account_id: string;
  name: string;
  online: boolean;
  port?: number | string;
  trd_env?: string;
  /** 如 OpenD 版本过低，仍可连但组合下单会失败 */
  warning?: string | null;
};

export type AgentStatus = {
  online: boolean;
  relay_held?: boolean;
  brokers: Record<string, boolean>;
  gateways?: GatewayStatus[];
  device_id: string;
  relay_url: string;
  logged_in: boolean;
  email: string | null;
  language: string;
  version: string;
  enabled_brokers?: string[];
  stats?: {
    session_received: number;
    session_failed: number;
    total_processed: number;
    filled: number;
    failed: number;
    by_status?: Record<string, number>;
  };
};

export type BrokerProfile = {
  broker: "ibkr" | "futu";
  name: string;
  enabled: boolean;
  account_id: string;
  config: Record<string, string | number>;
};

export type AgentConfig = {
  language: string;
  relay_url: string;
  broker_profiles: BrokerProfile[];
};

const json = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((body as { error?: string }).error || res.statusText);
  }
  return body as T;
};

export const api = {
  status: () => json<AgentStatus>("/api/status"),
  config: () => json<AgentConfig>("/api/config"),
  saveConfig: (payload: Partial<AgentConfig>) =>
    json<{ ok: boolean; restart_required?: boolean }>("/api/config", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  login: () => json<{ ok: boolean; email?: string }>("/api/login", { method: "POST", body: "{}" }),
  logout: () => json<{ ok: boolean }>("/api/logout", { method: "POST", body: "{}" }),
  quit: () => json<{ ok: boolean }>("/api/quit", { method: "POST", body: "{}" }),
  probe: (broker: string, config: Record<string, unknown>) =>
    json<{ ok: boolean }>("/api/probe", {
      method: "POST",
      body: JSON.stringify({ broker, config }),
    }),
  probeAll: () =>
    json<{ ok: boolean; gateways: GatewayStatus[]; online: number; total: number }>(
      "/api/probe-all",
      { method: "POST", body: "{}" },
    ),
  reconnect: (broker: string, accountId: string) =>
    json<{ ok: boolean; online: boolean; name?: string; error?: string }>("/api/reconnect", {
      method: "POST",
      body: JSON.stringify({ broker, account_id: accountId }),
    }),
  relayStop: () =>
    json<{ ok: boolean; online: boolean; relay_held?: boolean }>("/api/relay/stop", {
      method: "POST",
      body: "{}",
    }),
  relayReconnect: () =>
    json<{ ok: boolean; online: boolean; relay_held?: boolean }>("/api/relay/reconnect", {
      method: "POST",
      body: "{}",
    }),
  autostart: () => json<{ enabled: boolean }>("/api/autostart"),
  setAutostart: (enabled: boolean) =>
    json<{ enabled: boolean }>("/api/autostart", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
};

export const IBKR_PRESET_DEFAULTS: BrokerProfile[] = [
  {
    broker: "ibkr",
    name: "7497 · TWS 模拟",
    enabled: true,
    account_id: "tws-paper",
    config: { host: "127.0.0.1", port: 7497, client_id: 1 },
  },
  {
    broker: "ibkr",
    name: "7496 · TWS 实盘",
    enabled: true,
    account_id: "tws-live",
    config: { host: "127.0.0.1", port: 7496, client_id: 2 },
  },
];

export const FUTU_PRESET_DEFAULTS: BrokerProfile[] = [
  {
    broker: "futu",
    name: "SIMULATE · 模拟",
    enabled: true,
    account_id: "futu-simulate",
    config: { host: "127.0.0.1", port: 11111, trd_env: "SIMULATE" },
  },
  {
    broker: "futu",
    name: "REAL · 实盘",
    enabled: true,
    account_id: "futu-real",
    config: { host: "127.0.0.1", port: 11111, trd_env: "REAL" },
  },
];

export function mergeProfiles(profiles: BrokerProfile[]): BrokerProfile[] {
  const ibkrByAccount = new Map(
    profiles.filter((p) => p.broker === "ibkr" && p.account_id).map((p) => [p.account_id, p]),
  );
  const ibkrByPort = new Map(
    profiles
      .filter((p) => p.broker === "ibkr")
      .map((p) => [Number(p.config.port || 0), p] as const)
      .filter(([port]) => port > 0),
  );
  const ibkr = IBKR_PRESET_DEFAULTS.map((def) => {
    const existing = ibkrByAccount.get(def.account_id) || ibkrByPort.get(Number(def.config.port));
    return existing
      ? {
          ...def,
          ...existing,
          account_id: existing.account_id || def.account_id,
          name: existing.name || def.name,
          config: { ...def.config, ...existing.config },
        }
      : def;
  });

  const futuByAccount = new Map(
    profiles.filter((p) => p.broker === "futu" && p.account_id).map((p) => [p.account_id, p]),
  );
  const futuByEnv = new Map(
    profiles
      .filter((p) => p.broker === "futu")
      .map((p) => [String(p.config.trd_env || "").toUpperCase(), p] as const)
      .filter(([env]) => Boolean(env)),
  );
  const futu = FUTU_PRESET_DEFAULTS.map((def) => {
    const existing =
      futuByAccount.get(def.account_id) || futuByEnv.get(String(def.config.trd_env).toUpperCase());
    return existing
      ? {
          ...def,
          ...existing,
          account_id: existing.account_id || def.account_id,
          name: existing.name || def.name,
          config: { ...def.config, ...existing.config },
        }
      : def;
  });
  return [...ibkr, ...futu];
}
