import api from "./api";

export type WebhookIngest = {
  token: string;
  source_id: string;
  label?: string;
  url_path: string;
};

export function buildWebhookIngestUrl(urlPath: string, ingestBase?: string): string {
  const base =
    ingestBase ||
    import.meta.env.VITE_INGEST_PUBLIC_URL ||
    import.meta.env.VITE_INGEST_URL ||
    window.location.origin;
  return `${String(base).replace(/\/$/, "")}${urlPath}`;
}

export async function createWebhookIngestToken(
  label: string,
  ingestBase?: string,
): Promise<{ source_id: string; url: string; token: string }> {
  const { data } = await api.post("/webhooks/ingest-token", {
    label: label.trim() || "Webhook",
  });
  const path = data?.url_path as string | undefined;
  if (!path) {
    throw new Error("missing webhook url_path");
  }
  return {
    source_id: data.source_id as string,
    token: data.token as string,
    url: buildWebhookIngestUrl(path, ingestBase),
  };
}
