import { useCallback, useEffect, useState } from "react";
import {
  AgentConfig,
  AgentStatus,
  BrokerProfile,
  api,
  mergeProfiles,
} from "./api";
import Toast from "./components/Toast";
import BrandMark from "./components/BrandMark";
import UserMenu from "./components/UserMenu";
import HomePage from "./pages/HomePage";
import SettingsPage from "./pages/SettingsPage";

const WEB_CONSOLE = import.meta.env.VITE_WEB_URL || "https://sigtrades.com";

const MESSAGES = {
  zh: {
    loginSuccess: "登录成功，Agent 已连接。",
    loginTitle: "登录 sigtrades Agent",
    loginHint: "登录后 Agent 才能连接云端 relay 并执行本地订单。",
    browserLogin: "浏览器登录",
    loggingIn: "登录中…",
    loggedIn: "已登录",
    logout: "退出登录",
    quitApp: "退出 Agent",
    openConsole: "打开控制台",
    online: "在线",
    offline: "离线",
    testConnection: "测试连接",
    saveConfig: "保存配置",
    saved: "已保存，配置已立即生效。",
    languageSaved: "语言已保存",
    gatewayOk: "网关可达",
    gatewayFail: "网关不可达",
    reconnect: "重连",
    reconnecting: "重连中…",
    reconnectOk: "重连成功",
    reconnectFail: "重连失败",
    stop: "停止",
    stopping: "停止中…",
    relayReconnectOk: "已重连服务端",
    relayReconnectFail: "重连服务端失败",
    relayStopped: "已停止服务端连接",
    relayOnline: "已连接服务端",
    relayOffline: "服务端未连接",
    language: "语言",
    autostart: "开机自启（后台运行，无窗口）",
    versionHint: "关窗口会进托盘；退出用本菜单 / 托盘 / ⌘Q",
    loading: "加载中…",
    overview: "概览",
    relay: "连接状态",
    device: "设备 ID",
    sessionSignals: "本次收到",
    totalProcessed: "累计处理",
    filled: "已成交",
    failed: "失败",
    brokerGateways: "券商网关",
    gatewayOnline: "网关在线",
    gatewayOffline: "网关离线",
    notEnabled: "未启用",
    noBrokers: "尚未启用本地券商，请前往设置配置。",
    openSettings: "设置",
    settings: "设置",
    brokers: "本地券商网关",
    brokersHint: "凭证仅保存在本机，不会上传云端。",
    back: "返回",
  },
  en: {
    loginSuccess: "Login successful. Agent connected.",
    loginTitle: "Sign in to sigtrades Agent",
    loginHint: "Sign in so Agent can connect to the cloud relay and execute local orders.",
    browserLogin: "Sign in via browser",
    loggingIn: "Signing in…",
    loggedIn: "Signed in",
    logout: "Sign out",
    quitApp: "Quit Agent",
    openConsole: "Open console",
    online: "Online",
    offline: "Offline",
    testConnection: "Test connection",
    saveConfig: "Save settings",
    saved: "Saved. Broker settings applied immediately.",
    languageSaved: "Language saved",
    gatewayOk: "gateway reachable",
    gatewayFail: "gateway unreachable",
    reconnect: "Reconnect",
    reconnecting: "Reconnecting…",
    reconnectOk: "Reconnected",
    reconnectFail: "Reconnect failed",
    stop: "Stop",
    stopping: "Stopping…",
    relayReconnectOk: "Reconnected to server",
    relayReconnectFail: "Failed to reconnect to server",
    relayStopped: "Disconnected from server",
    relayOnline: "Connected to server",
    relayOffline: "Server disconnected",
    language: "Language",
    autostart: "Launch at login (background, no window)",
    versionHint: "Close hides to tray; quit via this menu / tray / Cmd+Q",
    loading: "Loading…",
    overview: "Overview",
    relay: "Connection",
    device: "Device ID",
    sessionSignals: "This session",
    totalProcessed: "Total processed",
    filled: "Filled",
    failed: "Failed",
    brokerGateways: "Broker gateways",
    gatewayOnline: "Gateway online",
    gatewayOffline: "Gateway offline",
    notEnabled: "Disabled",
    noBrokers: "No local brokers enabled yet. Open Settings to configure.",
    openSettings: "Settings",
    settings: "Settings",
    brokers: "Local broker gateways",
    brokersHint: "Credentials stay on this device only.",
    back: "Back",
  },
} as const;

const LANGUAGE_OPTIONS = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
];

type Page = "home" | "settings";
type ToastState = { message: string; variant: "success" | "error" } | null;

function pickLang(language?: string) {
  return (language || "zh").toLowerCase().startsWith("en") ? "en" : "zh";
}

function msg(language: string | undefined, key: keyof typeof MESSAGES.zh) {
  return MESSAGES[pickLang(language)][key];
}

function probeAllDoneMsg(language: string | undefined, online: number, total: number) {
  return pickLang(language) === "en"
    ? `Checked connections: ${online}/${total} online`
    : `连接检测完成：${online}/${total} 在线`;
}

function LoginScreen({
  language,
  busy,
  onLogin,
}: {
  language?: string;
  busy: boolean;
  onLogin: () => void;
}) {
  const t = (key: keyof typeof MESSAGES.zh) => msg(language, key);
  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-logo">
          <BrandMark />
        </div>
        <h1 className="login-title">{t("loginTitle")}</h1>
        <p className="hint login-hint">{t("loginHint")}</p>
        <button
          type="button"
          className="btn btn-primary login-btn"
          disabled={busy}
          onClick={onLogin}
        >
          {busy ? t("loggingIn") : t("browserLogin")}
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("home");
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [profiles, setProfiles] = useState<BrokerProfile[]>([]);
  const [autostart, setAutostart] = useState(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState<ToastState>(null);
  const [probeKey, setProbeKey] = useState("");
  const [reconnectKey, setReconnectKey] = useState("");
  const [relayBusy, setRelayBusy] = useState<"" | "reconnect" | "stop">("");

  const lang = config?.language;
  const t = (key: keyof typeof MESSAGES.zh) => msg(lang, key);

  const showToast = useCallback((message: string, variant: "success" | "error" = "success") => {
    setToast({ message, variant });
  }, []);

  const refresh = useCallback(async () => {
    const [st, cfg, auto] = await Promise.all([api.status(), api.config(), api.autostart()]);
    setStatus(st);
    setConfig(cfg);
    setProfiles(mergeProfiles(cfg.broker_profiles));
    setAutostart(auto.enabled);
    setReady(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
        if (cancelled) return;
        // 进入软件后自动检测全部已启用连接，更新首页状态
        await api.probeAll();
        if (!cancelled) await refresh();
      } catch (e) {
        if (!cancelled) {
          setReady(true);
          showToast(String(e), "error");
        }
      }
    })();
    const id = window.setInterval(() => {
      api.status().then(setStatus).catch(() => {});
    }, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [refresh, showToast]);

  const onLogin = async () => {
    setBusy("login");
    try {
      // 后端 login 内已重试离线券商；再 probe/refresh 刷新首页角标
      await api.login();
      const probe = await api.probeAll();
      await refresh();
      showToast(
        `${t("loginSuccess")} ${probeAllDoneMsg(lang, probe.online, probe.total)}`,
      );
    } catch (e) {
      showToast(String(e), "error");
    } finally {
      setBusy("");
    }
  };

  const onLogout = async () => {
    setBusy("logout");
    try {
      await api.logout();
      setPage("home");
      await refresh();
    } catch (e) {
      showToast(String(e), "error");
    } finally {
      setBusy("");
    }
  };

  const onQuitApp = async () => {
    setBusy("quit");
    try {
      await api.quit();
    } catch (e) {
      showToast(String(e), "error");
      setBusy("");
    }
  };

  const onSave = async () => {
    setBusy("save");
    try {
      // 持久化全部 profile（含未启用），避免取消勾选后重启又被默认补回
      await api.saveConfig({
        language: config?.language || "zh",
        relay_url: config?.relay_url,
        broker_profiles: profiles,
      });
      // 保存后再次探测全部连接，并把状态刷到首页
      const res = await api.probeAll();
      await refresh();
      setPage("home");
      showToast(`${t("saved")} ${probeAllDoneMsg(lang, res.online, res.total)}`);
    } catch (e) {
      showToast(String(e), "error");
    } finally {
      setBusy("");
    }
  };

  const onLanguageChange = async (value: string) => {
    setConfig((c) => (c ? { ...c, language: value } : c));
    try {
      await api.saveConfig({
        language: value,
        relay_url: config?.relay_url,
        broker_profiles: profiles,
      });
      showToast(msg(value, "languageSaved"));
    } catch (e) {
      showToast(String(e), "error");
    }
  };

  const onAutostartChange = (enabled: boolean) => {
    api
      .setAutostart(enabled)
      .then((r) => setAutostart(r.enabled))
      .catch((err) => showToast(String(err), "error"));
  };

  const onProbe = async (profile: BrokerProfile) => {
    const key = `${profile.broker}:${profile.account_id || profile.name}`;
    setProbeKey(key);
    try {
      const res = await api.probe(profile.broker, profile.config);
      const label = profile.name || profile.broker;
      showToast(
        res.ok ? `${label} ${t("gatewayOk")}` : `${label} ${t("gatewayFail")}`,
        res.ok ? "success" : "error",
      );
    } catch (e) {
      showToast(String(e), "error");
    } finally {
      setProbeKey("");
    }
  };

  const onReconnect = async (gw: { broker: string; account_id: string; name: string }) => {
    const key = `${gw.broker}:${gw.account_id || gw.name}`;
    setReconnectKey(key);
    try {
      const res = await api.reconnect(gw.broker, gw.account_id);
      await refresh();
      const label = res.name || gw.name || gw.broker;
      showToast(
        res.ok
          ? `${label} ${t("reconnectOk")}`
          : res.error || `${label} ${t("reconnectFail")}`,
        res.ok ? "success" : "error",
      );
    } catch (e) {
      showToast(String(e), "error");
    } finally {
      setReconnectKey("");
    }
  };

  const onRelayReconnect = async () => {
    setRelayBusy("reconnect");
    try {
      const res = await api.relayReconnect();
      await refresh();
      showToast(res.ok ? t("relayReconnectOk") : t("relayReconnectFail"), res.ok ? "success" : "error");
    } catch (e) {
      showToast(String(e), "error");
    } finally {
      setRelayBusy("");
    }
  };

  const onRelayStop = async () => {
    setRelayBusy("stop");
    try {
      await api.relayStop();
      await refresh();
      showToast(t("relayStopped"));
    } catch (e) {
      showToast(String(e), "error");
    } finally {
      setRelayBusy("");
    }
  };

  if (!ready) {
    return (
      <div className="login-screen">
        <p className="hint">{msg(lang, "loading")}</p>
      </div>
    );
  }

  if (!status?.logged_in) {
    return (
      <>
        <LoginScreen language={lang} busy={busy === "login"} onLogin={() => void onLogin()} />
        {toast ? (
          <Toast message={toast.message} variant={toast.variant} onClose={() => setToast(null)} />
        ) : null}
      </>
    );
  }

  const displayEmail = status.email || "…";
  const homeLabels = {
    relay: t("relay"),
    device: t("device"),
    sessionSignals: t("sessionSignals"),
    totalProcessed: t("totalProcessed"),
    filled: t("filled"),
    failed: t("failed"),
    brokerGateways: t("brokerGateways"),
    gatewayOnline: t("gatewayOnline"),
    gatewayOffline: t("gatewayOffline"),
    notEnabled: t("notEnabled"),
    noBrokers: t("noBrokers"),
    openSettings: t("openSettings"),
    online: t("online"),
    offline: t("offline"),
    reconnect: t("reconnect"),
    reconnecting: t("reconnecting"),
    stop: t("stop"),
    stopping: t("stopping"),
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <BrandMark compact />
          <span
            className={`badge ${status.online ? "badge-online" : "badge-offline"}`}
            title={status.online ? t("relayOnline") : t("relayOffline")}
          >
            <span className="dot" />
            {status.online ? t("online") : t("offline")}
          </span>
        </div>
        <div className="header-actions">
          <UserMenu
            email={displayEmail}
            language={config?.language || "zh"}
            autostart={autostart}
            version={status.version || "0.1.0"}
            consoleUrl={WEB_CONSOLE}
            languageOptions={LANGUAGE_OPTIONS}
            busy={!!busy}
            labels={{
              language: t("language"),
              autostart: t("autostart"),
              openConsole: t("openConsole"),
              logout: t("logout"),
              quitApp: t("quitApp"),
              versionHint: t("versionHint"),
            }}
            onLanguageChange={(value) => void onLanguageChange(value)}
            onAutostartChange={onAutostartChange}
            onLogout={() => void onLogout()}
            onQuitApp={() => void onQuitApp()}
          />
        </div>
      </header>

      {page === "home" ? (
        <HomePage
          status={status}
          language={lang}
          reconnectKey={reconnectKey}
          relayBusy={relayBusy}
          onOpenSettings={() => setPage("settings")}
          onReconnect={(gw) => void onReconnect(gw)}
          onRelayReconnect={() => void onRelayReconnect()}
          onRelayStop={() => void onRelayStop()}
          labels={homeLabels}
        />
      ) : (
        <SettingsPage
          profiles={profiles}
          language={lang}
          busy={busy === "save"}
          probeKey={probeKey}
          labels={{
            settings: t("settings"),
            brokers: t("brokers"),
            brokersHint: t("brokersHint"),
            saveConfig: t("saveConfig"),
            back: t("back"),
          }}
          onBack={() => setPage("home")}
          onChangeProfile={(next) =>
            setProfiles((prev) =>
              prev.map((x) =>
                x.broker === next.broker &&
                (x.account_id || x.name) === (next.account_id || next.name)
                  ? next
                  : x,
              ),
            )
          }
          onChangeProfiles={(updater) => setProfiles(updater)}
          onProbe={(profile) => void onProbe(profile)}
          onSave={() => void onSave()}
        />
      )}

      {toast ? (
        <Toast message={toast.message} variant={toast.variant} onClose={() => setToast(null)} />
      ) : null}
    </div>
  );
}
