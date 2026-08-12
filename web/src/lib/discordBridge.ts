import api from "./api";

export type DiscordGuild = { id: string; name: string; icon?: string | null };

const DISCORD_ICON_SIZES = [16, 32, 64, 128, 256, 512, 1024, 2048, 4096] as const;

/** Discord CDN only accepts discrete icon sizes; snap up to the next allowed value. */
export function normalizeDiscordIconSize(size: number): number {
  const clamped = Math.max(16, Math.min(Math.round(size), 4096));
  for (const allowed of DISCORD_ICON_SIZES) {
    if (allowed >= clamped) return allowed;
  }
  return 4096;
}

export function discordGuildIconCdnUrl(guild: DiscordGuild, size = 48): string | null {
  if (!guild.icon) return null;
  const normalized = normalizeDiscordIconSize(size);
  const ext = guild.icon.startsWith("a_") ? "gif" : "png";
  return `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.${ext}?size=${normalized}`;
}

export function discordGuildIconUrl(guild: DiscordGuild, size = 48): string | null {
  if (!guild.icon) return null;
  const params = new URLSearchParams({
    guild_id: guild.id,
    icon: guild.icon,
    size: String(normalizeDiscordIconSize(size)),
  });
  return `/api/config/discord-asset/guild-icon?${params}`;
}

export type DiscordChannel = { id: string; name: string; guild_id: string; type: number };

export type TestMessage = {
  channel_id: string;
  channel_name: string;
  message_id: string;
  author: string;
  content: string;
  ts: number;
};

export type DiscordTokenStatus = {
  saved: boolean;
  hint?: string;
  user?: string;
  source_id?: string;
  is_active?: boolean;
};

const TOKEN_HINT_MASK = "•".repeat(16);

/** Expand legacy `abcd...wxyz` hints for display; pass-through if already masked. */
export function formatTokenHint(hint: string): string {
  const trimmed = hint.trim();
  if (!trimmed || trimmed === "****") return trimmed;
  const legacy = trimmed.match(/^(.{4})\.\.\.(.{4})$/);
  if (legacy) return `${legacy[1]}${TOKEN_HINT_MASK}${legacy[2]}`;
  return trimmed;
}

export async function fetchDiscordTokenStatus(): Promise<DiscordTokenStatus> {
  const { data } = await api.get("/config/discord-user/token-status");
  return data;
}

export async function saveDiscordToken(userToken: string) {
  const { data } = await api.post("/config/discord-user/save-token", { user_token: userToken });
  return data as { ok: boolean; hint: string; user: string };
}

export async function validateDiscordToken(userToken: string) {
  const { data } = await api.post("/config/discord-user/validate", { user_token: userToken });
  return data.user as { username?: string; global_name?: string };
}

export async function fetchGuilds(userToken?: string): Promise<DiscordGuild[]> {
  const body = userToken?.trim() ? { user_token: userToken.trim() } : {};
  const { data } = await api.post("/config/discord-user/guilds", body);
  return data.guilds;
}

export async function fetchGuildChannels(userToken: string | undefined, guildId: string): Promise<DiscordChannel[]> {
  const body = userToken?.trim()
    ? { user_token: userToken.trim(), guild_id: guildId }
    : { guild_id: guildId };
  const { data } = await api.post("/config/discord-user/channels", body);
  return data.channels;
}

export async function startTestListen(
  channelIds: string[],
  channelLabels: Record<string, string>,
  userToken?: string,
): Promise<string> {
  const body: Record<string, unknown> = {
    channel_ids: channelIds,
    channel_labels: channelLabels,
  };
  if (userToken?.trim()) body.user_token = userToken.trim();
  const { data } = await api.post("/config/discord-user/test-listen", body);
  return data.session_id as string;
}

export async function stopTestListen(sessionId: string): Promise<void> {
  await api.post("/config/discord-user/test-stop", null, { params: { session_id: sessionId } });
}

export async function fetchTestMessages(sessionId: string): Promise<TestMessage[]> {
  const { data } = await api.get("/config/discord-user/test-messages", { params: { session_id: sessionId } });
  return data.messages;
}

export async function fetchPreviewMessages(sourceId: string): Promise<TestMessage[]> {
  const { data } = await api.get(`/config/discord-user/preview-messages/${sourceId}`);
  return data.messages;
}

export async function updateDiscordBridgeSource(
  sourceId: string,
  payload: {
    label?: string;
    channel_ids: string[];
    channel_labels: Record<string, string>;
    guild_id?: string;
    user_token?: string;
  },
): Promise<void> {
  await api.patch(`/config/discord-bridge-source/${sourceId}`, payload);
}

export async function stopDiscordBridgeSource(sourceId: string): Promise<void> {
  await api.post(`/config/discord-bridge-source/${sourceId}/stop`);
}

/** 复制频道配置为新 source_id（同频道可有多条独立流水线）。 */
export async function cloneDiscordPipelineSource(payload: {
  label: string;
  channel_ids: string[];
  channel_labels?: Record<string, string>;
  guild_id?: string;
}): Promise<string> {
  const { data } = await api.post("/config/discord-bridge-source", {
    label: payload.label || "My Discord",
    channel_ids: payload.channel_ids,
    channel_labels: payload.channel_labels || {},
    guild_id: payload.guild_id,
    action: "confirm_trade",
    order_type_policy: "MKT_only",
  });
  return data.source_id as string;
}

export async function renameDiscordPipelineSource(sourceId: string, label: string): Promise<void> {
  const trimmed = label.trim();
  if (!trimmed) return;
  await api.patch(`/config/discord-bridge-source/${sourceId}`, { label: trimmed });
}
