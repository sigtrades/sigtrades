export type WebhookIngestItem = {
  token: string;
  source_id: string;
  label?: string;
  url_path: string;
};

export type GroupedWebhookSource = {
  sourceId: string;
  name: string;
  tokens: WebhookIngestItem[];
};

/** 同一 source_id 下的多个 ingest token 合并为一个逻辑信号源。 */
export function groupWebhooksBySource(
  webhooks: WebhookIngestItem[],
  defaultName: string,
): GroupedWebhookSource[] {
  const bySource = new Map<string, WebhookIngestItem[]>();
  for (const w of webhooks) {
    const list = bySource.get(w.source_id) || [];
    list.push(w);
    bySource.set(w.source_id, list);
  }
  return [...bySource.entries()].map(([sourceId, tokens]) => ({
    sourceId,
    name: tokens.find((row) => row.label?.trim())?.label?.trim() || defaultName,
    tokens,
  }));
}

export function webhookIngestUrl(ingestBase: string, urlPath: string): string {
  return `${ingestBase.replace(/\/$/, "")}${urlPath}`;
}
