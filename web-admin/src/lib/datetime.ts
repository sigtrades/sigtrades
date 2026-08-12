export const APP_TIMEZONE = "America/New_York";

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
