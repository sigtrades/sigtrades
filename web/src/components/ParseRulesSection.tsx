import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";
type Rule = { id?: string; source_id: string; parse_mode: string; priority: number; label: string; config: object };

export default function ParseRulesSection({ sourceId }: { sourceId: string }) {
  const { t } = useTranslation();
  const [rules, setRules] = useState<Rule[]>([]);
  const [mode, setMode] = useState("ai");
  const [pattern, setPattern] = useState("");

  useEffect(() => {
    api.get("/config/parse-rules").then((r) => {
      setRules(r.data.filter((x: Rule) => !sourceId || x.source_id === sourceId));
    });
  }, [sourceId]);

  const save = async () => {
    if (!sourceId) return;
    const config = mode === "regex" ? { pattern, min_confidence: 0.5 } : { min_confidence: 0.5 };
    await api.put("/config/parse-rules", {
      source_id: sourceId,
      parse_mode: mode,
      priority: 10,
      label: "default",
      config,
    });
    const r = await api.get("/config/parse-rules");
    setRules(r.data);
  };

  return (
    <section className="card">
      <h2 className="font-semibold">{t("dashboard.parseRules")}</h2>
      <div className="mt-3 flex flex-col gap-2 text-sm sm:flex-row sm:flex-wrap">
        <select className="select sm:w-auto" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="ai">AI</option>
          <option value="regex">Regex</option>
          <option value="structured">Structured</option>
        </select>
        {mode === "regex" && (
          <input className="input w-full flex-1 font-mono text-xs sm:min-w-[200px]" placeholder="(BUY|SELL)\s+(\w+)" value={pattern} onChange={(e) => setPattern(e.target.value)} />
        )}
        <button onClick={save} className="btn-primary w-full sm:w-auto">{t("dashboard.save")}</button>
      </div>
      {rules.length > 0 && <pre className="code-block mt-3">{JSON.stringify(rules, null, 2)}</pre>}
    </section>
  );
}
