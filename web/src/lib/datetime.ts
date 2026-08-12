/** 全站展示与「今日」统计统一为美东时间。 */
export const APP_TIMEZONE = "America/New_York";

export function getEtTodayDateString(date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: APP_TIMEZONE }).format(date);
}

/** Compact ET display: MM/DD HH:MM:SS */
export function formatEtDateTimeCompact(value?: string | null): string {
  if (!value) return "";
  const ms = parseEtTimestamp(value);
  if (!ms) return "";
  const d = new Date(ms);

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: APP_TIMEZONE,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(d);

  const pick = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";

  return `${pick("month")}/${pick("day")} ${pick("hour")}:${pick("minute")}:${pick("second")}`;
}

export function formatEtDateTime(value?: string | null): string {
  if (!value) return "—";
  if (/\sET$/.test(value.trim())) return value.trim();

  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: APP_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(d);

  const pick = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";

  return `${pick("year")}-${pick("month")}-${pick("day")} ${pick("hour")}:${pick("minute")}:${pick("second")} ET`;
}

/**
 * 将「YYYY-MM-DD HH:MM:SS ET」墙钟时间转为 UTC 毫秒。
 * 不可写死 GMT-0500：夏令时为 EDT(UTC-4)，否则会偏 1 小时导致耗时恒为 0。
 */
function etWallTimeToUtcMs(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  second: number,
): number {
  const want = Date.UTC(year, month - 1, day, hour, minute, second);
  // 初值：ET 约落后 UTC 4~5 小时
  let utc = want + 4 * 3600_000;
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: APP_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  for (let i = 0; i < 4; i++) {
    const parts = fmt.formatToParts(new Date(utc));
    const pick = (type: Intl.DateTimeFormatPartTypes) =>
      Number(parts.find((p) => p.type === type)?.value ?? "0");
    let h = pick("hour");
    if (h === 24) h = 0; // 部分环境午夜表示为 24
    const got = Date.UTC(pick("year"), pick("month") - 1, pick("day"), h, pick("minute"), pick("second"));
    utc += want - got;
  }
  return utc;
}

export function parseEtTimestamp(value?: string | null): number {
  if (!value) return 0;
  const trimmed = value.trim();
  if (trimmed.endsWith(" ET")) {
    const core = trimmed.slice(0, -3).trim();
    const m = core.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/);
    if (m) {
      return etWallTimeToUtcMs(+m[1], +m[2], +m[3], +m[4], +m[5], +m[6]);
    }
    // 兜底：依次尝试 EDT / EST
    const iso = core.replace(" ", "T");
    for (const offset of ["GMT-0400", "GMT-0500"]) {
      const d = new Date(`${iso} ${offset}`);
      if (!Number.isNaN(d.getTime())) return d.getTime();
    }
  }
  const d = new Date(trimmed);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

export function isEtToday(value?: string | null, today = getEtTodayDateString()): boolean {
  if (!value) return false;
  const trimmed = value.trim();
  if (trimmed.startsWith(today)) return true;

  const d = new Date(trimmed);
  if (Number.isNaN(d.getTime())) return false;
  return getEtTodayDateString(d) === today;
}

export type RelativeAge =
  | { unit: "just_now" }
  | { unit: "minutes"; n: number }
  | { unit: "hours"; n: number }
  | { unit: "days"; n: number };

/** 相对当前时刻的年龄，用于「几分钟前」展示。 */
export function getRelativeAge(valueMs: number, nowMs = Date.now()): RelativeAge | null {
  if (!valueMs || !Number.isFinite(valueMs)) return null;
  const delta = Math.max(0, nowMs - valueMs);
  const sec = Math.floor(delta / 1000);
  if (sec < 60) return { unit: "just_now" };
  const minutes = Math.floor(sec / 60);
  if (minutes < 60) return { unit: "minutes", n: minutes };
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return { unit: "hours", n: hours };
  return { unit: "days", n: Math.floor(hours / 24) };
}
