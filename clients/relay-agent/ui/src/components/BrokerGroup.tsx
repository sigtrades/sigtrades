import { BrokerProfile } from "../api";

const MESSAGES = {
  zh: {
    test: "测试",
    host: "Host",
    port: "Port",
    clientId: "Client ID",
    ibkrTitle: "IBKR",
    futuTitle: "富途 OpenD",
    ibkrHint: "端口按模式固定；一般只需改 Host / Client ID。交易账户用 TWS 当前登录账户。",
    futuHint: "OpenD 默认 127.0.0.1:11111；网页绑定选同一模拟/实盘模式即可路由。",
    enabledCount: (n: number, total: number) => `已启用 ${n}/${total}`,
  },
  en: {
    test: "Test",
    host: "Host",
    port: "Port",
    clientId: "Client ID",
    ibkrTitle: "IBKR",
    futuTitle: "Futu OpenD",
    ibkrHint: "Ports are fixed per mode; usually only Host / Client ID need edits.",
    futuHint: "OpenD defaults to 127.0.0.1:11111; match the same mode on the web binding.",
    enabledCount: (n: number, total: number) => `${n}/${total} enabled`,
  },
} as const;

function langOf(language?: string) {
  return (language || "zh").toLowerCase().startsWith("en") ? "en" : "zh";
}

function profileKey(p: BrokerProfile) {
  return `${p.broker}:${p.account_id || p.name || p.config.port}`;
}

type Props = {
  broker: "ibkr" | "futu";
  profiles: BrokerProfile[];
  language?: string;
  probeKey: string;
  onChangeProfile: (profile: BrokerProfile) => void;
  onChangeProfiles: (updater: (prev: BrokerProfile[]) => BrokerProfile[]) => void;
  onProbe: (profile: BrokerProfile) => void;
};

export default function BrokerGroup({
  broker,
  profiles,
  language,
  probeKey,
  onChangeProfile,
  onChangeProfiles,
  onProbe,
}: Props) {
  const lang = langOf(language);
  const m = MESSAGES[lang];
  const isIbkr = broker === "ibkr";
  const title = isIbkr ? m.ibkrTitle : m.futuTitle;
  const enabled = profiles.filter((p) => p.enabled).length;
  const sharedHost = String(profiles[0]?.config.host ?? "127.0.0.1");
  const sharedPort = String(profiles[0]?.config.port ?? (isIbkr ? 7497 : 11111));

  const setSharedHost = (host: string) => {
    onChangeProfiles((prev) =>
      prev.map((p) =>
        p.broker === broker ? { ...p, config: { ...p.config, host } } : p,
      ),
    );
  };

  const setSharedFutuPort = (port: number) => {
    onChangeProfiles((prev) =>
      prev.map((p) =>
        p.broker === broker ? { ...p, config: { ...p.config, port } } : p,
      ),
    );
  };

  return (
    <div className="broker-settings-group">
      <div className="broker-settings-head">
        <div>
          <p className="broker-settings-title">{title}</p>
          <p className="broker-settings-meta">{m.enabledCount(enabled, profiles.length)}</p>
        </div>
      </div>

      <div className="broker-settings-shared">
        <div className="broker-settings-field">
          <label className="label">{m.host}</label>
          <input
            className="input"
            value={sharedHost}
            placeholder="127.0.0.1"
            onChange={(e) => setSharedHost(e.target.value)}
          />
        </div>
        {!isIbkr ? (
          <div className="broker-settings-field">
            <label className="label">{m.port}</label>
            <input
              className="input"
              value={sharedPort}
              placeholder="11111"
              onChange={(e) => setSharedFutuPort(Number(e.target.value) || 0)}
            />
          </div>
        ) : null}
      </div>

      <div className="broker-settings-rows">
        {profiles.map((p) => {
          const key = profileKey(p);
          const probing = probeKey === key;
          const clientId = String(p.config.client_id ?? 1);
          return (
            <div key={key} className={`broker-settings-row ${p.enabled ? "" : "is-disabled"}`}>
              <label className="broker-settings-enable">
                <input
                  type="checkbox"
                  className="ui-checkbox"
                  checked={p.enabled}
                  onChange={(e) => onChangeProfile({ ...p, enabled: e.target.checked })}
                />
                <span className="broker-settings-mode">{p.name || p.account_id || p.broker}</span>
              </label>
              {isIbkr ? (
                <div className="broker-settings-client">
                  <span className="broker-settings-client-label">{m.clientId}</span>
                  <input
                    className="input input-sm"
                    value={clientId}
                    onChange={(e) =>
                      onChangeProfile({
                        ...p,
                        config: { ...p.config, client_id: Number(e.target.value) || 1 },
                      })
                    }
                  />
                </div>
              ) : (
                <span className="broker-settings-env">{String(p.config.trd_env || "")}</span>
              )}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={probing || !p.enabled}
                onClick={() => onProbe(p)}
              >
                {probing ? "…" : m.test}
              </button>
            </div>
          );
        })}
      </div>

      <p className="broker-settings-hint">{isIbkr ? m.ibkrHint : m.futuHint}</p>
    </div>
  );
}
