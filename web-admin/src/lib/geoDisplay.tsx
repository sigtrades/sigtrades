import type { ReactNode } from "react";

export type GeoSnapshot = {
  ip?: string;
  country_code?: string | null;
  city_name?: string | null;
};

export function flagEmoji(code: string | null | undefined): string {
  if (!code || code.length !== 2) return "";
  const u = code.toUpperCase();
  if (!/^[A-Z]{2}$/.test(u)) return "";
  return [...u].map((c) => String.fromCodePoint(127397 + c.charCodeAt(0))).join("");
}

export function regionLabelZh(code: string | null | undefined): string {
  if (!code) return "未知";
  try {
    return new Intl.DisplayNames(["zh-CN"], { type: "region" }).of(code) || code;
  } catch {
    return code;
  }
}

export function languageDisplay(language: string | null | undefined): { label: string; flag: string } {
  const lang = (language || "zh").toLowerCase();
  if (lang.startsWith("en")) return { label: "EN", flag: "🇺🇸" };
  if (lang === "zh-hk" || lang === "zh-tw") return { label: "繁中", flag: "🇭🇰" };
  return { label: "中文", flag: "🇨🇳" };
}

export function GeoCell({ geo }: { geo?: GeoSnapshot | null }): ReactNode {
  if (!geo || (!geo.ip && !geo.country_code && !geo.city_name)) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  return (
    <div className="text-xs leading-tight">
      <div className="flex items-center gap-1">
        <span className="text-base" title={geo.country_code || ""}>
          {flagEmoji(geo.country_code) || "·"}
        </span>
        <span className="text-slate-800">{regionLabelZh(geo.country_code)}</span>
      </div>
      {geo.city_name ? (
        <div className="mt-0.5 max-w-[140px] truncate text-slate-500" title={geo.city_name}>
          {geo.city_name}
        </div>
      ) : null}
      <div className="mt-0.5 max-w-[128px] truncate font-mono text-slate-400" title={geo.ip || undefined}>
        {geo.ip || "—"}
      </div>
    </div>
  );
}
