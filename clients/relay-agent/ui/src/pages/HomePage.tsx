import { GatewayStatus, AgentStatus } from "../api";

type Props = {
  status: AgentStatus;
  language?: string;
  reconnectKey?: string;
  relayBusy?: "" | "reconnect" | "stop";
  onOpenSettings: () => void;
  onReconnect: (gw: GatewayStatus) => void;
  onRelayReconnect: () => void;
  onRelayStop: () => void;
  labels: {
    relay: string;
    device: string;
    sessionSignals: string;
    totalProcessed: string;
    filled: string;
    failed: string;
    brokerGateways: string;
    gatewayOnline: string;
    gatewayOffline: string;
    notEnabled: string;
    noBrokers: string;
    openSettings: string;
    online: string;
    offline: string;
    reconnect: string;
    reconnecting: string;
    stop: string;
    stopping: string;
  };
};

const BROKER_ORDER = ["ibkr", "futu"];
const BROKER_LABELS: Record<string, { zh: string; en: string }> = {
  ibkr: { zh: "IBKR", en: "IBKR" },
  futu: { zh: "富途 OpenD", en: "Futu OpenD" },
};

function brokerLabel(broker: string, language?: string) {
  const lang = (language || "zh").toLowerCase().startsWith("en") ? "en" : "zh";
  return BROKER_LABELS[broker]?.[lang] || broker.toUpperCase();
}

function modeLabel(gw: GatewayStatus): string {
  const name = (gw.name || gw.account_id || "").trim();
  return name || gw.broker.toUpperCase();
}

function gwKey(gw: GatewayStatus) {
  return `${gw.broker}:${gw.account_id || gw.name}`;
}

function sortGateways(broker: string, items: GatewayStatus[]): GatewayStatus[] {
  if (broker === "ibkr") {
    const order = ["tws-paper", "tws-live"];
    return [...items].sort(
      (a, b) => order.indexOf(a.account_id) - order.indexOf(b.account_id),
    );
  }
  if (broker === "futu") {
    const order = ["futu-simulate", "futu-real"];
    return [...items].sort(
      (a, b) => order.indexOf(a.account_id) - order.indexOf(b.account_id),
    );
  }
  return items;
}

function groupGateways(gateways: GatewayStatus[]): { broker: string; items: GatewayStatus[] }[] {
  const map = new Map<string, GatewayStatus[]>();
  for (const gw of gateways) {
    const list = map.get(gw.broker) || [];
    list.push(gw);
    map.set(gw.broker, list);
  }
  const brokers = [
    ...BROKER_ORDER.filter((b) => map.has(b)),
    ...[...map.keys()].filter((b) => !BROKER_ORDER.includes(b)).sort(),
  ];
  return brokers.map((broker) => ({
    broker,
    items: sortGateways(broker, map.get(broker) || []),
  }));
}

export default function HomePage({
  status,
  language,
  reconnectKey = "",
  relayBusy = "",
  onOpenSettings,
  onReconnect,
  onRelayReconnect,
  onRelayStop,
  labels,
}: Props) {
  const stats = status.stats;
  const groups = groupGateways(status.gateways || []);
  const relayHeld = Boolean(status.relay_held);

  return (
    <div className="page">
      <div className="card">
        <div className="card-head">
          <p className="card-title">{labels.brokerGateways}</p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onOpenSettings}>
            {labels.openSettings}
          </button>
        </div>
        {groups.length === 0 ? (
          <p className="hint">{labels.noBrokers}</p>
        ) : (
          <div className="broker-group-list">
            {groups.map(({ broker, items }) => {
              const onlineCount = items.filter((g) => g.online).length;
              // 同一 OpenD 只提示一次，放在券商组标题下方，避免模拟/实盘卡片重复
              const groupWarning =
                items.map((g) => (g.warning || "").trim()).find((w) => w.length > 0) || "";
              return (
                <div key={broker} className="broker-group">
                  <div className="broker-group-head">
                    <span className="broker-group-name">{brokerLabel(broker, language)}</span>
                    <span
                      className={`broker-group-summary ${onlineCount > 0 ? "is-online" : "is-offline"}`}
                    >
                      {onlineCount > 0
                        ? `${onlineCount}/${items.length} ${labels.online}`
                        : labels.offline}
                    </span>
                  </div>
                  {groupWarning ? (
                    <p className="broker-group-warning" title={groupWarning}>
                      {groupWarning}
                    </p>
                  ) : null}
                  <div className={`broker-tag-row ${broker === "ibkr" ? "is-ibkr" : "is-futu"}`}>
                    {items.map((gw) => {
                      const key = gwKey(gw);
                      const busy = reconnectKey === key;
                      return (
                        <div
                          key={key}
                          className={`broker-mode-tag ${gw.online ? "is-online" : "is-offline"}`}
                          title={gw.online ? labels.gatewayOnline : labels.gatewayOffline}
                        >
                          <div className="broker-mode-main">
                            <span className="broker-mode-dot" aria-hidden />
                            <div className="broker-mode-text">
                              <span className="broker-mode-label">{modeLabel(gw)}</span>
                              <span
                                className={`broker-mode-status ${gw.online ? "is-online" : "is-offline"}`}
                              >
                                {gw.online ? labels.online : labels.offline}
                              </span>
                            </div>
                          </div>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm broker-reconnect-btn"
                            disabled={busy}
                            onClick={() => onReconnect(gw)}
                          >
                            {busy ? labels.reconnecting : labels.reconnect}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <p className="stat-label">{labels.sessionSignals}</p>
          <p className="stat-value">{stats?.session_received ?? 0}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">{labels.totalProcessed}</p>
          <p className="stat-value">{stats?.total_processed ?? 0}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">{labels.filled}</p>
          <p className="stat-value stat-value-success">{stats?.filled ?? 0}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">{labels.failed}</p>
          <p className="stat-value stat-value-danger">{stats?.failed ?? 0}</p>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="card-title-with-badge">
            <p className="card-title">{labels.relay}</p>
            <span className={`badge ${status.online ? "badge-online" : "badge-offline"}`}>
              <span className="dot" />
              {status.online ? labels.online : labels.offline}
            </span>
          </div>
          <div className="relay-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!!relayBusy}
              onClick={onRelayReconnect}
            >
              {relayBusy === "reconnect" ? labels.reconnecting : labels.reconnect}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!!relayBusy || relayHeld}
              onClick={onRelayStop}
            >
              {relayBusy === "stop" ? labels.stopping : labels.stop}
            </button>
          </div>
        </div>
        <div className="info-row">
          <span className="info-label">{labels.device}</span>
          <span className="info-value mono">{status.device_id}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Relay</span>
          <span className="info-value mono">{status.relay_url}</span>
        </div>
      </div>
    </div>
  );
}
