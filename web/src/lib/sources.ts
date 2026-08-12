import api from "./api";

export async function deleteSource(sourceId: string): Promise<void> {
  await api.delete(`/config/sources/${encodeURIComponent(sourceId)}`);
}

export async function deleteWebhook(token: string): Promise<void> {
  await api.delete(`/config/webhooks/${encodeURIComponent(token)}`);
}
