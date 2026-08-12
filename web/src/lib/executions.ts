export type ExecutionRecord = {
  source_id: string;
  signal_id: string;
  broker: string;
  account_label?: string | null;
  status: string;
  fill_price?: number | null;
  realized_pnl?: number | null;
  order_id?: string | null;
  created_at?: string;
  signal?: Record<string, unknown>;
  detail?: string | null;
};

export type ExecutionsListResponse = {
  items: ExecutionRecord[];
  total: number;
  limit: number;
  offset: number;
};

/** 兼容旧版数组响应与新版分页对象。 */
export function normalizeExecutionsResponse(data: unknown): ExecutionsListResponse {
  if (Array.isArray(data)) {
    return {
      items: data as ExecutionRecord[],
      total: data.length,
      limit: data.length,
      offset: 0,
    };
  }
  const page = data as Partial<ExecutionsListResponse>;
  const items = Array.isArray(page.items) ? page.items : [];
  return {
    items,
    total: typeof page.total === "number" ? page.total : items.length,
    limit: typeof page.limit === "number" ? page.limit : items.length,
    offset: typeof page.offset === "number" ? page.offset : 0,
  };
}
