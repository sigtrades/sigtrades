import { useCallback, useEffect, useState } from "react";
import { agentReleasesApi } from "@/api";
import { canWriteAdmin } from "@/lib/adminPermissions";
import PageHeader from "@/components/ui/PageHeader";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import { AdminToast } from "@/components/ui/AdminToast";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuthStore } from "@/store/auth";

function normVer(v: string): string {
  return (v || "").trim().replace(/^v/i, "");
}

type PlatformRelease = {
  latest_version: string;
  min_version: string;
  download_url: string;
  sha256: string;
  release_notes: string;
};

type HistoryEntry = {
  id: string;
  platform: "macos" | "windows";
  version: string;
  min_version?: string;
  download_url?: string;
  filename?: string;
  sha256?: string;
  release_notes?: string;
  published_at_et?: string;
  published_by?: string;
};

function packageNameFromUrl(url: string): string {
  const raw = (url || "").trim();
  if (!raw) return "";
  try {
    const path = new URL(raw, "http://local").pathname;
    return decodeURIComponent(path.split("/").filter(Boolean).pop() || "");
  } catch {
    return raw.split("/").filter(Boolean).pop() || "";
  }
}

const emptyRelease = (): PlatformRelease => ({
  latest_version: "",
  min_version: "",
  download_url: "",
  sha256: "",
  release_notes: "",
});

type Tab = "publish" | "history";
type HistoryFilter = "" | "macos" | "windows";

function PlatformCard({
  title,
  subtitle,
  value,
  onChange,
  onPublish,
  onSaveDraft,
  disabled,
  publishing,
}: {
  title: string;
  subtitle: string;
  value: PlatformRelease;
  onChange: (v: PlatformRelease) => void;
  onPublish: () => void;
  onSaveDraft: () => void;
  disabled?: boolean;
  publishing?: boolean;
}) {
  return (
    <div className="card space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        <p className="text-xs text-slate-500">{subtitle}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="版本号" value={value.latest_version} onChange={(v) => onChange({ ...value, latest_version: v })} disabled={disabled} placeholder="0.1.0" />
        <Field label="最低版本" value={value.min_version} onChange={(v) => onChange({ ...value, min_version: v })} disabled={disabled} placeholder="留空则同版本号" />
      </div>
      <div>
        <Field label="下载地址" value={value.download_url} onChange={(v) => onChange({ ...value, download_url: v })} disabled={disabled} mono placeholder="https://.../sigtrades-agent-macos-v0.1.2.dmg" />
        {packageNameFromUrl(value.download_url) ? (
          <p className="mt-1 text-xs text-slate-500">
            包名：<span className="font-mono text-slate-700">{packageNameFromUrl(value.download_url)}</span>
          </p>
        ) : null}
      </div>
      <Field label="SHA256" value={value.sha256} onChange={(v) => onChange({ ...value, sha256: v })} disabled={disabled} mono placeholder="自动更新校验（可选）" />
      <div>
        <label className="mb-1 block text-xs text-slate-500">更新说明</label>
        <textarea className="textarea w-full text-sm" rows={3} value={value.release_notes} onChange={(e) => onChange({ ...value, release_notes: e.target.value })} disabled={disabled} />
      </div>
      {!disabled && (
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
          <button type="button" className="btn-secondary" onClick={onSaveDraft}>保存草稿</button>
          <button
            type="button"
            className="btn-primary"
            disabled={publishing || !value.latest_version.trim()}
            onClick={onPublish}
          >
            {publishing ? "发布中…" : "发布此版本"}
          </button>
        </div>
      )}
    </div>
  );
}

function applyLocalPackage(
  current: PlatformRelease,
  pkg: {
    exists?: boolean;
    download_url?: string;
    sha256?: string;
    version_hint?: string;
  } | undefined,
  opts?: { fallbackVersion?: string },
): PlatformRelease {
  // 版本优先用打包清单里的 version_hint（make build-agent 已自动 +patch）
  const ver = (pkg?.version_hint || opts?.fallbackVersion || current.latest_version || "").trim();
  return {
    ...current,
    latest_version: ver || current.latest_version,
    min_version:
      !current.min_version || current.min_version === current.latest_version
        ? ver || current.min_version
        : current.min_version,
    download_url: pkg?.exists ? pkg.download_url || current.download_url : current.download_url,
    sha256: pkg?.exists ? pkg.sha256 || current.sha256 : current.sha256,
  };
}

function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return fallback;
}

export default function AgentRelease() {
  const [tab, setTab] = useState<Tab>("publish");
  const [macos, setMacos] = useState<PlatformRelease>(emptyRelease());
  const [windows, setWindows] = useState<PlatformRelease>(emptyRelease());
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>("");
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<"macos" | "windows" | "restore" | "delete" | "load" | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  /** 线上当前已发布版本（用于同包二次确认） */
  const [liveVersions, setLiveVersions] = useState<{ macos: string; windows: string }>({ macos: "", windows: "" });
  const [confirmPublish, setConfirmPublish] = useState<{
    platform: "macos" | "windows";
    release: PlatformRelease;
  } | null>(null);
  const role = useAuthStore((s) => s.role);
  const canWrite = canWriteAdmin(role);

  const syncLiveVersions = (platforms: { macos?: PlatformRelease; windows?: PlatformRelease }) => {
    setLiveVersions({
      macos: platforms.macos?.download_url?.trim() ? normVer(platforms.macos.latest_version || "") : "",
      windows: platforms.windows?.download_url?.trim() ? normVer(platforms.windows.latest_version || "") : "",
    });
  };

  const loadCurrent = useCallback(async () => {
    const data = await agentReleasesApi.get();
    const nextMacos = { ...emptyRelease(), ...(data.platforms?.macos || {}) };
    const nextWindows = { ...emptyRelease(), ...(data.platforms?.windows || {}) };
    setMacos(nextMacos);
    setWindows(nextWindows);
    syncLiveVersions({ macos: nextMacos, windows: nextWindows });
  }, []);

  const loadHistory = useCallback(async () => {
    const data = await agentReleasesApi.history(historyFilter || undefined, 100);
    setHistory(data.items || []);
  }, [historyFilter]);

  useEffect(() => {
    Promise.all([loadCurrent(), loadHistory()])
      .catch(() => setToast({ message: "加载失败", type: "error" }))
      .finally(() => setLoading(false));
  }, [loadCurrent, loadHistory]);

  useEffect(() => {
    if (!loading) loadHistory().catch(() => setHistory([]));
  }, [historyFilter, loading, loadHistory]);

  const saveDraft = async (platform: "macos" | "windows", release: PlatformRelease) => {
    setActing(platform);
    try {
      await agentReleasesApi.save(platform === "macos" ? { macos: release, windows } : { macos, windows: release });
      setToast({ message: "草稿已保存（未写入历史）", type: "success" });
    } catch {
      setToast({ message: "保存失败", type: "error" });
    } finally {
      setActing(null);
    }
  };

  const doPublish = async (platform: "macos" | "windows", release: PlatformRelease) => {
    setActing(platform);
    try {
      const data = await agentReleasesApi.publish(platform, release);
      if (data.platforms?.macos) setMacos({ ...emptyRelease(), ...data.platforms.macos });
      if (data.platforms?.windows) setWindows({ ...emptyRelease(), ...data.platforms.windows });
      if (data.platforms) syncLiveVersions(data.platforms);
      await loadHistory();
      setToast({ message: `${platform === "macos" ? "macOS" : "Windows"} v${release.latest_version} 已发布`, type: "success" });
    } catch (err) {
      setToast({ message: apiErrorMessage(err, "发布失败"), type: "error" });
    } finally {
      setActing(null);
      setConfirmPublish(null);
    }
  };

  const requestPublish = (platform: "macos" | "windows", release: PlatformRelease) => {
    if (!release.latest_version.trim()) return;
    const url = (release.download_url || "").trim();
    if (!url) {
      setToast({ message: "请先填写下载地址（或点「加载本地包」）", type: "error" });
      return;
    }
    if (url.includes("localhost") || url.includes("127.0.0.1")) {
      setToast({
        message: "下载地址仍是 localhost，请改为 https://stapi.sigtrades.com/releases/... 后再发布",
        type: "error",
      });
      return;
    }
    const ver = normVer(release.latest_version);
    if (ver && liveVersions[platform] && ver === liveVersions[platform]) {
      setConfirmPublish({ platform, release });
      return;
    }
    void doPublish(platform, release);
  };

  const restore = async (entry: HistoryEntry) => {
    if (!confirm(`将 ${entry.platform} v${entry.version} 恢复为当前线上版本？`)) return;
    setActing("restore");
    try {
      const data = await agentReleasesApi.restore(entry.id);
      if (data.platforms?.macos) setMacos({ ...emptyRelease(), ...data.platforms.macos });
      if (data.platforms?.windows) setWindows({ ...emptyRelease(), ...data.platforms.windows });
      await loadHistory();
      setToast({ message: "已恢复并重新发布", type: "success" });
    } catch (err) {
      setToast({ message: apiErrorMessage(err, "恢复失败"), type: "error" });
    } finally {
      setActing(null);
    }
  };

  const removeHistory = async (entry: HistoryEntry) => {
    if (!confirm(`删除 ${entry.platform === "macos" ? "macOS" : "Windows"} v${entry.version} 的发布记录？`)) return;
    setActing("delete");
    try {
      await agentReleasesApi.deleteHistory(entry.id);
      await loadHistory();
      setToast({ message: "已删除历史版本", type: "success" });
    } catch (err) {
      setToast({ message: apiErrorMessage(err, "删除失败"), type: "error" });
    } finally {
      setActing(null);
    }
  };

  /** 同时加载 macOS + Windows 本地包；版本直接用打包清单（打包时已自动 +patch） */
  const loadLocalPackages = async () => {
    setActing("load");
    try {
      const data = await agentReleasesApi.localPackages();
      const plats = data.platforms || {};
      const manifestVer = String((data as { manifest?: { version?: string } }).manifest?.version || "").trim();
      const fallback =
        manifestVer ||
        plats.macos?.version_hint ||
        plats.windows?.version_hint ||
        macos.latest_version ||
        windows.latest_version ||
        "";
      setMacos(applyLocalPackage(macos, plats.macos, { fallbackVersion: fallback }));
      setWindows(applyLocalPackage(windows, plats.windows, { fallbackVersion: fallback }));
      const found = [plats.macos?.exists && "macOS", plats.windows?.exists && "Windows"].filter(Boolean);
      const missing = [!plats.macos?.exists && "macOS", !plats.windows?.exists && "Windows"].filter(Boolean);
      const verLabel =
        plats.macos?.version_hint ||
        plats.windows?.version_hint ||
        manifestVer ||
        fallback ||
        "?";
      if (found.length === 0) {
        setToast({ message: "未找到本地包，请先在本机执行 make build-agent（Mac/Windows 各打一次）", type: "error" });
      } else if (missing.length) {
        setToast({
          message: `已加载 ${found.join(" / ")}（打包版本 v${verLabel}）；缺少 ${missing.join(" / ")}，请在对应系统执行 make build-agent`,
          type: "success",
        });
      } else {
        setToast({ message: `已加载 macOS / Windows（打包版本 v${verLabel}）`, type: "success" });
      }
    } catch {
      setToast({ message: "读取本地包失败", type: "error" });
    } finally {
      setActing(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Agent 发布" subtitle="按平台管理版本与发布历史" />
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card h-64 animate-pulse bg-slate-100" />
          <div className="card h-64 animate-pulse bg-slate-100" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Agent 发布" subtitle="macOS / Windows 独立版本 · 发布写入历史记录" />

      <div className="flex gap-2 border-b border-slate-200 pb-2">
        <button type="button" className={tab === "publish" ? "border-b-2 border-brand-600 pb-2 text-sm font-medium text-brand-700" : "pb-2 text-sm text-slate-600"} onClick={() => setTab("publish")}>
          发布管理
        </button>
        <button type="button" className={tab === "history" ? "border-b-2 border-brand-600 pb-2 text-sm font-medium text-brand-700" : "pb-2 text-sm text-slate-600"} onClick={() => setTab("history")}>
          版本历史
        </button>
      </div>

      {tab === "publish" ? (
        <>
          <p className="text-xs text-slate-500">
            本机打包：Mac / Windows 上各执行一次{" "}
            <code className="rounded bg-slate-100 px-1">make build-agent</code>
            （会自动版本 +patch，产物在 <code className="rounded bg-slate-100 px-1">data/agent-releases/</code>）。
            下方按钮加载下载地址、SHA256 与打包版本号；再分别「发布此版本」。同一版本打另一平台时用{" "}
            <code className="rounded bg-slate-100 px-1">AGENT_PACKAGE_VERSION=x.y.z make build-agent</code>。
          </p>
          {canWrite && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-secondary"
                disabled={acting !== null}
                onClick={() => loadLocalPackages()}
              >
                {acting === "load" ? "处理中…" : "加载本地包"}
              </button>
            </div>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <PlatformCard
              title="macOS"
              subtitle="AGENT_LATEST_VERSION / AGENT_DOWNLOAD_URL"
              value={macos}
              onChange={setMacos}
              onSaveDraft={() => saveDraft("macos", macos)}
              onPublish={() => requestPublish("macos", macos)}
              disabled={!canWrite}
              publishing={acting === "macos"}
            />
            <PlatformCard
              title="Windows"
              subtitle="AGENT_WINDOWS_* 环境变量"
              value={windows}
              onChange={setWindows}
              onSaveDraft={() => saveDraft("windows", windows)}
              onPublish={() => requestPublish("windows", windows)}
              disabled={!canWrite}
              publishing={acting === "windows"}
            />
          </div>
        </>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {([
              { id: "" as const, label: "全部" },
              { id: "macos" as const, label: "macOS" },
              { id: "windows" as const, label: "Windows" },
            ]).map((f) => (
              <button key={f.id || "all"} type="button" className={historyFilter === f.id ? "btn-primary py-1.5" : "btn-secondary py-1.5"} onClick={() => setHistoryFilter(f.id)}>
                {f.label}
              </button>
            ))}
          </div>

          <div className="card overflow-hidden p-0">
            <table className="min-w-full text-sm">
              <thead className="border-b bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-4 py-3">平台</th>
                  <th className="px-4 py-3">版本</th>
                  <th className="px-4 py-3">发布时间</th>
                  <th className="px-4 py-3">发布人</th>
                  <th className="px-4 py-3">包名</th>
                  <th className="px-4 py-3">下载</th>
                  {canWrite && <th className="px-4 py-3">操作</th>}
                </tr>
              </thead>
              <tbody>
                {history.length === 0 ? (
                  <tr><td colSpan={canWrite ? 7 : 6}><EmptyState message="暂无发布历史" /></td></tr>
                ) : (
                  history.map((row) => (
                    <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <StatusBadge value={row.platform === "macos" ? "macOS" : "Windows"} kind={row.platform === "macos" ? "active" : "default"} />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        v{row.version}
                        {row.min_version && row.min_version !== row.version ? (
                          <span className="ml-1 text-slate-400">min {row.min_version}</span>
                        ) : null}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{row.published_at_et || "—"}</td>
                      <td className="px-4 py-3 text-slate-600">{row.published_by || "—"}</td>
                      <td className="max-w-[200px] truncate px-4 py-3 font-mono text-xs text-slate-700" title={row.filename || packageNameFromUrl(row.download_url || "")}>
                        {row.filename || packageNameFromUrl(row.download_url || "") || "—"}
                      </td>
                      <td className="px-4 py-3">
                        {row.download_url ? (
                          <a href={row.download_url} target="_blank" rel="noopener noreferrer" className="text-brand-600 hover:underline">
                            下载
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                      {canWrite && (
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-3">
                            <button type="button" className="text-brand-600 hover:underline disabled:opacity-50" disabled={acting !== null} onClick={() => restore(row)}>
                              恢复为当前
                            </button>
                            <button type="button" className="text-red-600 hover:underline disabled:opacity-50" disabled={acting !== null} onClick={() => removeHistory(row)}>
                              删除
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      <ConfirmDialog
        open={confirmPublish !== null}
        title="确认再次发布同一版本？"
        confirmText="确认发布"
        cancelText="取消"
        loading={acting === confirmPublish?.platform}
        onClose={() => {
          if (acting === confirmPublish?.platform) return;
          setConfirmPublish(null);
        }}
        onConfirm={() => {
          if (!confirmPublish) return;
          void doPublish(confirmPublish.platform, confirmPublish.release);
        }}
      >
        {confirmPublish ? (
          <div className="space-y-2">
            <p>
              线上已是{" "}
              <span className="font-semibold text-slate-800">
                {confirmPublish.platform === "macos" ? "macOS" : "Windows"} v{normVer(confirmPublish.release.latest_version)}
              </span>
              ，再次发布将覆盖当前配置并追加一条历史记录。
            </p>
            {packageNameFromUrl(confirmPublish.release.download_url) ? (
              <p className="rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">
                {packageNameFromUrl(confirmPublish.release.download_url)}
              </p>
            ) : null}
          </div>
        ) : null}
      </ConfirmDialog>

      {toast ? <AdminToast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} /> : null}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  disabled,
  mono,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  mono?: boolean;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-slate-500">{label}</label>
      <input className={`input w-full ${mono ? "font-mono text-xs" : ""}`} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} placeholder={placeholder} />
    </div>
  );
}
