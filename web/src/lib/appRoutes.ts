import type { NavId } from "../components/AppLayout";

export const APP_BASE = "/app";

const NAV_IDS: NavId[] = [
  "overview",
  "pipelines",
  "sources",
  "brokers",
  "risk",
  "executions",
  "account",
  "membership",
  "settings",
];

export const NAV_PATHS: Record<NavId, string> = {
  overview: `${APP_BASE}/overview`,
  pipelines: `${APP_BASE}/pipelines`,
  sources: `${APP_BASE}/sources`,
  brokers: `${APP_BASE}/brokers`,
  risk: `${APP_BASE}/risk`,
  executions: `${APP_BASE}/executions`,
  account: `${APP_BASE}/account`,
  membership: `${APP_BASE}/membership`,
  settings: `${APP_BASE}/settings`,
};

export const DEFAULT_APP_PATH = NAV_PATHS.overview;

export function navPath(id: NavId): string {
  return NAV_PATHS[id];
}

export function navIdFromPath(pathname: string): NavId {
  const segment = pathname.replace(new RegExp(`^${APP_BASE}/?`), "").split("/")[0];
  if (segment && NAV_IDS.includes(segment as NavId)) {
    return segment as NavId;
  }
  return "overview";
}

export function isValidAppSection(section: string | undefined): section is NavId {
  return Boolean(section && NAV_IDS.includes(section as NavId));
}
