import { useTranslation } from "react-i18next";
import { flagEmoji, GeoCell, GeoSnapshot, regionLabelZh } from "@/lib/geoDisplay";

export type AdminUser = {
  id: string;
  email: string;
  language?: string;
  auth_provider?: string;
  email_verified?: boolean;
  kill_switch?: boolean;
  created_at?: string;
  registration_geo?: GeoSnapshot | null;
  last_login_geo?: GeoSnapshot | null;
};

export type GeoDistribution = {
  total_users: number;
  users_without_registration_event: number;
  users_without_geo: number;
  users_fallback_to_last_login: number;
  by_country: { country_code: string | null; count: number }[];
};

export default function UsersPanel({ users, geoStats }: { users: AdminUser[]; geoStats?: GeoDistribution | null }) {
  const { t } = useTranslation();

  return (
    <div className="space-y-4">
      {geoStats && (
        <section className="card">
          <h3 className="text-sm font-semibold text-slate-900">{t("users.geoTitle")}</h3>
          <p className="mt-1 text-xs text-slate-500">
            {t("users.geoSummary", {
              total: geoStats.total_users,
              unknown: geoStats.users_without_geo,
              fallback: geoStats.users_fallback_to_last_login,
            })}
          </p>
          <ul className="mt-2 list-inside list-disc text-sm text-slate-600">
            {geoStats.by_country.slice(0, 12).map((row) => (
              <li key={String(row.country_code)}>
                {flagEmoji(row.country_code)} {regionLabelZh(row.country_code)} — {row.count}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">{t("users.email")}</th>
              <th className="px-4 py-3">{t("users.regCountry")}</th>
              <th className="px-4 py-3">{t("users.lastLogin")}</th>
              <th className="px-4 py-3">{t("users.provider")}</th>
              <th className="px-4 py-3">{t("users.verified")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-3 align-top">
                  <div className="font-medium text-slate-900">{u.email}</div>
                  <div className="font-mono text-xs text-slate-400">{u.id.slice(0, 8)}…</div>
                </td>
                <td className="px-4 py-3 align-top">
                  <GeoCell geo={u.registration_geo} />
                </td>
                <td className="px-4 py-3 align-top">
                  <GeoCell geo={u.last_login_geo} />
                </td>
                <td className="px-4 py-3 align-top text-slate-600">{u.auth_provider || "email"}</td>
                <td className="px-4 py-3 align-top">
                  {u.email_verified ? (
                    <span className="text-profit">✓</span>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">{t("users.empty")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
