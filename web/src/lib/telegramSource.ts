import api from "./api";

export type TelegramSource = {
  source_id: string;
  name: string;
  chat_ids: string[];
  chat_labels?: Record<string, string>;
  is_active?: boolean;
  kind?: "telegram";
};

export async function createTelegramSource(payload: {
  label: string;
  chat_ids: string[];
  chat_labels?: Record<string, string>;
}): Promise<TelegramSource> {
  const { data } = await api.post("/config/telegram-source", {
    label: payload.label.trim() || "My Telegram",
    chat_ids: payload.chat_ids,
    chat_labels: payload.chat_labels || {},
  });
  return {
    source_id: data.source_id,
    name: payload.label.trim() || "My Telegram",
    chat_ids: data.chat_ids || payload.chat_ids,
    chat_labels: payload.chat_labels || {},
    is_active: true,
    kind: "telegram",
  };
}

export async function renameTelegramSource(sourceId: string, label: string): Promise<void> {
  const trimmed = label.trim();
  if (!trimmed) return;
  await api.patch(`/config/telegram-source/${sourceId}`, { label: trimmed });
}

/** 解析逗号/空白分隔的 chat id 列表（群组一般为负数）。 */
export function parseTelegramChatIds(raw: string): string[] {
  return raw
    .split(/[\s,，]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}
