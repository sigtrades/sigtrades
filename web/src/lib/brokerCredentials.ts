import { futuPresetById } from "./futuPresets";
import { ibkrPresetById } from "./ibkrPresets";

export type CredentialLastProbe = {
  ok: boolean;
  tested_at?: string | null;
  account_summary?: {
    account_id?: string | null;
    net_liquidation?: number | null;
    available_cash?: number | null;
    currency?: string | null;
    is_paper?: boolean | null;
  } | null;
  error?: string | null;
};

export type SavedCredential = {
  id: string;
  broker: string;
  account_id: string;
  label: string;
  env: string;
  license?: string;
  tiger_id?: string;
  has_private_key: boolean;
  has_secrets: boolean;
  key_hint: string;
  /** Tiger TBHK user token（脱敏） */
  token_hint?: string;
  app_key_hint?: string;
  app_secret_hint?: string;
  access_token_hint?: string;
  client_id_hint?: string;
  client_secret_hint?: string;
  refresh_token_hint?: string;
  account_hash_hint?: string;
  oauth_status?: "pending" | "authorized" | string;
  oauth_redirect_uri?: string | null;
  api_key_hint?: string;
  api_secret_hint?: string;
  consumer_key_hint?: string;
  channel?: string;
  area_code?: string;
  /** 盈立站点：hk=香港，sg=新加坡 */
  region?: "hk" | "sg" | string;
  phone_number_hint?: string;
  public_key_hint?: string;
  private_key_hint?: string;
  /** 上次「测试账户」持久化结果 */
  last_probe?: CredentialLastProbe | null;
};

export type UsmartRegion = "hk" | "sg";

export const USMART_APPLY_URLS: Record<UsmartRegion, string> = {
  hk: "https://www.usmart.hk/zh-cn/open-api",
  sg: "https://www.usmart.sg/open-api",
};

export const USMART_DEFAULT_AREA_CODE: Record<UsmartRegion, string> = {
  hk: "852",
  sg: "65",
};

export function normalizeUsmartRegion(region?: string | null): UsmartRegion {
  const key = (region || "").trim().toLowerCase();
  if (key === "hk" || key === "hongkong" || key === "hong kong" || key === "香港") return "hk";
  return "sg";
}

export function usmartRegionLabel(region: string | undefined, t: (key: string) => string): string {
  return normalizeUsmartRegion(region) === "hk"
    ? t("dashboard.regionHongKong")
    : t("dashboard.regionSingapore");
}

/** 老虎模拟盘资金账号一般为 ≥17 位纯数字 */
export function isTigerPaperAccount(accountId?: string | null): boolean {
  const a = String(accountId || "").trim();
  return /^\d{17,}$/.test(a);
}

/** 标识文案：优先按资金账号区分模拟/正式，其次看 env 字段 */
export function tigerEnvLabel(
  env: string,
  t: (key: string) => string,
  accountId?: string | null,
): string {
  if (accountId != null && String(accountId).trim() !== "") {
    return isTigerPaperAccount(accountId)
      ? t("dashboard.envTest")
      : t("dashboard.envProduction");
  }
  const key = (env || "").toLowerCase();
  if (key === "production" || key === "prod" || key === "live") {
    return t("dashboard.envProduction");
  }
  return t("dashboard.envTest");
}

export function longbridgeEnvLabel(env: string, t: (key: string) => string): string {
  const key = (env || "sandbox").toLowerCase();
  return key === "live" || key === "production" || key === "prod" || key === "online"
    ? t("dashboard.envLive")
    : t("dashboard.envSandbox");
}

export function alpacaEnvLabel(env: string, t: (key: string) => string): string {
  return (env || "paper").toLowerCase() === "live"
    ? t("dashboard.envLive")
    : t("dashboard.envPaper");
}

export function usmartEnvLabel(env: string, t: (key: string) => string): string {
  return (env || "live").toLowerCase() === "uat"
    ? t("dashboard.envUat")
    : t("dashboard.envLive");
}

export function envLabel(
  broker: string,
  env: string,
  t: (key: string) => string,
  accountId?: string | null,
): string {
  const key = broker.toLowerCase();
  if (key === "alpaca" || key === "ibkr_web") return alpacaEnvLabel(env, t);
  if (key === "longbridge") return longbridgeEnvLabel(env, t);
  if (key === "usmart") return usmartEnvLabel(env, t);
  return tigerEnvLabel(env, t, accountId);
}

export type BrokerKey =
  | "tiger"
  | "longbridge"
  | "schwab"
  | "alpaca"
  | "usmart"
  | "ibkr"
  | "ibkr_web"
  | "futu";

/** 正式/模拟：绿=正式，黄=模拟（与券商配置页角标一致） */
export function isBrokerPaperMode(
  broker: string,
  env?: string | null,
  accountId?: string | null,
): boolean | null {
  const key = (broker || "").toLowerCase();
  if (!key) return null;

  if (key === "ibkr") {
    const preset = ibkrPresetById(accountId);
    return preset ? preset.paper : null;
  }
  if (key === "ibkr_web") {
    const e = (env || "").toLowerCase();
    if (!e) return null;
    return !["production", "prod", "live", "online"].includes(e);
  }
  if (key === "futu") {
    const preset = futuPresetById(accountId);
    return preset ? preset.paper : null;
  }
  if (key === "tiger") {
    if (accountId != null && String(accountId).trim() !== "") {
      return isTigerPaperAccount(accountId);
    }
    const e = (env || "").toLowerCase();
    if (!e) return null;
    return !["production", "prod", "live", "online"].includes(e);
  }
  if (key === "schwab") return false;
  if (key === "usmart") return (env || "live").toLowerCase() === "uat";

  const e = (env || "").toLowerCase();
  if (!e) return null;
  return !["production", "prod", "live", "online"].includes(e);
}

export function brokerDisplayName(broker: string, t: (key: string) => string): string {
  const key = broker.toLowerCase();
  if (key === "tiger") return t("dashboard.brokerTiger");
  if (key === "longbridge") return t("dashboard.brokerLongbridge");
  if (key === "schwab") return t("dashboard.brokerSchwab");
  if (key === "alpaca") return "Alpaca";
  if (key === "usmart") return t("dashboard.brokerUsmart");
  if (key === "ibkr") return t("dashboard.brokerIbkr");
  if (key === "ibkr_web") return t("dashboard.brokerIbkrWeb");
  if (key === "futu") return t("dashboard.brokerFutu");
  return broker.toUpperCase();
}

/** 盈立展示名：带香港/新加坡站点后缀 */
export function usmartDisplayName(
  region: string | undefined,
  t: (key: string) => string,
): string {
  return normalizeUsmartRegion(region) === "hk"
    ? t("dashboard.brokerUsmartHk")
    : t("dashboard.brokerUsmartSg");
}

const KNOWN_BROKERS = new Set([
  "tiger",
  "longbridge",
  "schwab",
  "alpaca",
  "usmart",
  "ibkr",
  "ibkr_web",
  "futu",
]);

export function normalizeBrokerKey(broker: string): BrokerKey | null {
  const key = broker.toLowerCase();
  return KNOWN_BROKERS.has(key) ? (key as BrokerKey) : null;
}
