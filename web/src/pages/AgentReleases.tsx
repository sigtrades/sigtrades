import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../lib/api";

type HistoryItem = {
  id: string;
  platform: string;
  version: string;
  filename: string;
  download_url: string;
  release_notes?: string;
  published_at_et?: string;
};

type Filter = "" | "macos" | "windows";

export default function AgentReleases() {
  const { t } = useTranslation();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [filter, setFilter] = useState<Filter>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const q = filter ? `?platform=${filter}&limit=100` : "?limit=100";
    api
      .get(`/public/agent-releases/history${q}`)
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [filter]);

  const filters = useMemo(
    () =>
      [
        { id: "" as const, label: t("agentReleases.filterAll") },
        { id: "macos" as const, label: "macOS" },
        { id: "windows" as const, label: "Windows" },
      ] as const,
    [t],
  );

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{t("agentReleases.title")}</h1>
          <p className="mt-1 text-sm text-slate-600">{t("agentReleases.subtitle")}</p>
        </div>
        <Link to="/app/brokers" className="text-sm text-brand-600 hover:underline">
          ← {t("agentReleases.backToAgent")}
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.id || "all"}
            type="button"
            className={filter === f.id ? "btn-primary py-1.5 text-sm" : "btn-secondary py-1.5 text-sm"}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="card overflow-hidden p-0">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">{t("common.loading")}</p>
        ) : items.length === 0 ? (
          <p className="p-6 text-sm text-slate-500">{t("agentReleases.empty")}</p>
        ) : (
          <div className="overflow-x-auto">
          <table className="min-w-[640px] w-full text-sm">
            <thead className="border-b bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-3">{t("agentReleases.colPlatform")}</th>
                <th className="px-4 py-3">{t("agentReleases.colVersion")}</th>
                <th className="px-4 py-3">{t("agentReleases.colFilename")}</th>
                <th className="px-4 py-3">{t("agentReleases.colTime")}</th>
                <th className="px-4 py-3">{t("agentReleases.colDownload")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">{row.platform === "windows" ? "Windows" : "macOS"}</td>
                  <td className="px-4 py-3 font-mono text-xs">v{row.version}</td>
                  <td className="max-w-[220px] truncate px-4 py-3 font-mono text-xs text-slate-700" title={row.filename}>
                    {row.filename || "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{row.published_at_et || "—"}</td>
                  <td className="px-4 py-3">
                    {row.download_url ? (
                      <a
                        href={row.download_url}
                        className="font-medium text-brand-600 hover:underline"
                        download={row.filename || undefined}
                      >
                        {t("agentReleases.download")}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}
