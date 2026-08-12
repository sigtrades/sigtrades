import { BrokerProfile } from "../api";
import BrokerGroup from "../components/BrokerGroup";

type Props = {
  profiles: BrokerProfile[];
  language?: string;
  busy: boolean;
  probeKey: string;
  labels: {
    settings: string;
    brokers: string;
    brokersHint: string;
    saveConfig: string;
    back: string;
  };
  onBack: () => void;
  onChangeProfile: (profile: BrokerProfile) => void;
  onChangeProfiles: (updater: (prev: BrokerProfile[]) => BrokerProfile[]) => void;
  onProbe: (profile: BrokerProfile) => void;
  onSave: () => void;
};

const BROKER_ORDER: Array<"ibkr" | "futu"> = ["ibkr", "futu"];

function sortProfiles(broker: string, items: BrokerProfile[]): BrokerProfile[] {
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

export default function SettingsPage({
  profiles,
  language,
  busy,
  probeKey,
  labels,
  onBack,
  onChangeProfile,
  onChangeProfiles,
  onProbe,
  onSave,
}: Props) {
  const groups = BROKER_ORDER.map((broker) => ({
    broker,
    profiles: sortProfiles(
      broker,
      profiles.filter((p) => p.broker === broker),
    ),
  })).filter((g) => g.profiles.length > 0);

  return (
    <div className="settings-page">
      <div className="settings-scroll">
        <div className="page-head">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onBack}>
            ← {labels.back}
          </button>
          <p className="section-title">{labels.settings}</p>
        </div>

        <p className="section-title">{labels.brokers}</p>
        <p className="hint" style={{ margin: "0 0 10px" }}>
          {labels.brokersHint}
        </p>
        <div className="settings-brokers">
          {groups.map((g) => (
            <BrokerGroup
              key={g.broker}
              broker={g.broker}
              profiles={g.profiles}
              language={language}
              probeKey={probeKey}
              onChangeProfile={onChangeProfile}
              onChangeProfiles={onChangeProfiles}
              onProbe={onProbe}
            />
          ))}
        </div>
      </div>

      <div className="settings-footer">
        <button type="button" className="btn btn-primary settings-save-btn" disabled={busy} onClick={onSave}>
          {labels.saveConfig}
        </button>
      </div>
    </div>
  );
}
