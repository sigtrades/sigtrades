/** IBKR 连接模式：与 Agent 本地 profile.account_id 对齐（仅 TWS）。 */
export type IbkrPresetId = "tws-paper" | "tws-live";

export type IbkrPreset = {
  id: IbkrPresetId;
  port: number;
  paper: boolean;
  labelZh: string;
  labelEn: string;
};

export const IBKR_PRESETS: IbkrPreset[] = [
  { id: "tws-paper", port: 7497, paper: true, labelZh: "7497 · TWS 模拟", labelEn: "7497 · TWS Paper" },
  { id: "tws-live", port: 7496, paper: false, labelZh: "7496 · TWS 实盘", labelEn: "7496 · TWS Live" },
];

export function ibkrPresetById(id: string | undefined | null): IbkrPreset | undefined {
  return IBKR_PRESETS.find((p) => p.id === id);
}

export function ibkrPresetLabel(id: string | undefined | null, lang: string = "zh"): string {
  const preset = ibkrPresetById(id || "");
  if (!preset) return id || "—";
  return lang.toLowerCase().startsWith("en") ? preset.labelEn : preset.labelZh;
}
