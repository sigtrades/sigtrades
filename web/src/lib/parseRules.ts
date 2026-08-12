import api from "./api";

export type ParseRule = {
  id?: string;
  source_id: string;
  parse_mode: string;
  priority: number;
  label: string;
  config: Record<string, unknown>;
};

export type ParsePreviewResult = {
  signal: Record<string, unknown>;
  confidence: number;
  mode: string;
  error?: string | null;
  matched_label?: string | null;
};

export type ParseRuleInput = {
  source_id: string;
  parse_mode: string;
  priority: number;
  label: string;
  config: Record<string, unknown>;
};

export async function fetchParseRules(): Promise<ParseRule[]> {
  const { data } = await api.get("/config/parse-rules");
  return data;
}

export async function saveParseRule(rule: ParseRuleInput): Promise<void> {
  await api.put("/config/parse-rules", rule);
}

export async function deleteParseRule(sourceId: string, label: string): Promise<void> {
  await api.delete("/config/parse-rules", { params: { source_id: sourceId, label } });
}

/** 将 from 源的全部解析规则复制到 to 源（Discord ↔ Telegram 共用解析引擎）。 */
export async function copyParseRules(fromSourceId: string, toSourceId: string): Promise<number> {
  const { data } = await api.post("/config/parse-rules/copy", {
    from_source_id: fromSourceId,
    to_source_id: toSourceId,
  });
  return Number(data?.copied || 0);
}

export async function fetchParseSourceSettings(sourceId: string): Promise<{ option_default_dte: number }> {
  const { data } = await api.get(`/config/parse-source-settings/${sourceId}`);
  return data;
}

export async function saveParseSourceSettings(
  sourceId: string,
  optionDefaultDte: number,
): Promise<void> {
  await api.put("/config/parse-source-settings", {
    source_id: sourceId,
    option_default_dte: optionDefaultDte,
  });
}

export async function previewParse(payload: {
  sample: string | object;
  source_id?: string;
  rules?: ParseRuleInput[];
  author?: string;
  option_default_dte?: number;
}): Promise<ParsePreviewResult> {
  const { data } = await api.post("/config/parse-preview", payload);
  return data;
}

export type ParseGenerateResult = {
  parse_mode: string;
  config: Record<string, unknown>;
  summary: string;
  preview: ParsePreviewResult;
};

export async function generateParseRule(payload: {
  sample: string;
  expected_output: Record<string, unknown>;
}): Promise<ParseGenerateResult> {
  const { data } = await api.post("/config/parse-generate-rule", payload);
  return data;
}

export type ParseAiBootstrapResult = ParseGenerateResult & {
  ai: ParsePreviewResult;
  expected_output: Record<string, unknown>;
};

export async function bootstrapParseRuleAi(payload: {
  sample: string;
  author?: string;
  prompt?: string;
}): Promise<ParseAiBootstrapResult> {
  const { data } = await api.post("/config/parse-ai-bootstrap", payload);
  return data;
}

export function suggestParseRuleLabel(_mode: string, existing: ParseRule[]): string {
  const base = "example";
  if (!existing.some((r) => r.label === base)) return base;
  let i = 2;
  while (existing.some((r) => r.label === `${base}-${i}`)) i += 1;
  return `${base}-${i}`;
}

export function nextParseRulePriority(existing: ParseRule[]): number {
  if (existing.length === 0) return 10;
  return Math.max(...existing.map((r) => r.priority)) + 10;
}

export function parseModeLabel(mode: string, t: (key: string) => string): string {
  const map: Record<string, string> = {
    example: t("dashboard.parseModeExample"),
    ai: t("dashboard.parseModeAi"),
    regex: t("dashboard.parseModeRegex"),
    structured: t("dashboard.parseModeStructured"),
  };
  return map[mode] || mode;
}

export { DEFAULT_FLOW_SAMPLE, DEFAULT_PARSE_EXPECTED_FORM } from "./parseExpectedFields";
