/** 富途连接模式：与 Agent 本地 profile.account_id 对齐。 */
export type FutuPresetId = "futu-simulate" | "futu-real";

export type FutuPreset = {
  id: FutuPresetId;
  trdEnv: "SIMULATE" | "REAL";
  paper: boolean;
  labelZh: string;
  labelEn: string;
};

export const FUTU_PRESETS: FutuPreset[] = [
  {
    id: "futu-simulate",
    trdEnv: "SIMULATE",
    paper: true,
    labelZh: "SIMULATE · 模拟",
    labelEn: "SIMULATE · Paper",
  },
  {
    id: "futu-real",
    trdEnv: "REAL",
    paper: false,
    labelZh: "REAL · 实盘",
    labelEn: "REAL · Live",
  },
];

export function futuPresetById(id: string | undefined | null): FutuPreset | undefined {
  return FUTU_PRESETS.find((p) => p.id === id);
}

export function futuPresetLabel(id: string | undefined | null, lang: string = "zh"): string {
  const preset = futuPresetById(id || "");
  if (!preset) return id || "—";
  return lang.toLowerCase().startsWith("en") ? preset.labelEn : preset.labelZh;
}
