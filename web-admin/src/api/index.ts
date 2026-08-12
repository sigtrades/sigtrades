import axios from "axios";
import { useAuthStore } from "@/store/auth";

const api = axios.create({
  baseURL: "/api/admin",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const { token } = useAuthStore.getState();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
    config.headers["X-Admin-Token"] = token;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

export default api;

export const authApi = {
  login: async (username: string, password: string) => {
    const response = await api.post("/login", { username, password });
    return response.data;
  },
  getMe: async () => {
    const response = await api.get("/me");
    return response.data;
  },
};

export const usersApi = {
  list: async (page = 1, limit = 20, q?: string) => {
    const response = await api.get("/users", { params: { page, limit, q: q || undefined } });
    const body = response.data;
    return {
      items: body.data?.users || body.users || [],
      total: body.data?.pagination?.total ?? body.pagination?.total ?? 0,
      page: body.data?.pagination?.page ?? page,
      pages: body.data?.pagination?.pages ?? 1,
    };
  },
  get: async (userId: string) => {
    const response = await api.get(`/users/${userId}`);
    return response.data.data || response.data;
  },
  pipeline: async (userId: string) => {
    const response = await api.get(`/users/${userId}/pipeline`);
    return response.data.data || response.data;
  },
  brokers: async (userId: string) => {
    const response = await api.get(`/users/${userId}/brokers`);
    return response.data.data || response.data;
  },
  agents: async (userId: string) => {
    const response = await api.get(`/users/${userId}/agents`);
    return response.data.data || response.data;
  },
  executions: async (userId: string, page = 1, limit = 20) => {
    const response = await api.get(`/users/${userId}/executions`, { params: { page, limit } });
    const body = response.data.data || response.data;
    return body.items || body;
  },
  riskDisclosures: async (userId: string) => {
    const response = await api.get(`/users/${userId}/risk-disclosures`);
    return response.data.data || response.data;
  },
  ban: async (userId: string, banned: boolean, note?: string) => {
    const response = await api.post(`/users/${userId}/ban`, { banned, note });
    return response.data;
  },
  killSwitch: async (userId: string, enabled: boolean) => {
    const response = await api.post(`/users/${userId}/kill-switch`, { enabled });
    return response.data;
  },
  revokeTokens: async (userId: string) => {
    const response = await api.post(`/users/${userId}/revoke-tokens`);
    return response.data;
  },
  geoDistribution: async () => {
    const response = await api.get("/users/geo-distribution");
    return response.data.data || response.data;
  },
};

export const analyticsApi = {
  overview: async () => {
    const response = await api.get("/analytics/overview");
    return response.data;
  },
  userTrends: async (days = 30) => {
    const response = await api.get("/analytics/users/trends", { params: { days } });
    return response.data.data || response.data;
  },
  channelStats: async (params?: { days?: number; kind?: string; source_id?: string }) => {
    const response = await api.get("/analytics/channel-stats", { params });
    return response.data.data || response.data;
  },
  channelStatsDetail: async (params: {
    source_id: string;
    channel_id?: string | null;
    days?: number;
  }) => {
    const response = await api.get("/analytics/channel-stats/detail", {
      params: {
        source_id: params.source_id,
        channel_id: params.channel_id ?? "",
        days: params.days,
      },
    });
    return response.data.data || response.data;
  },
};

export const membershipApi = {
  list: async () => {
    const response = await api.get("/membership-plans");
    return response.data.data || response.data || [];
  },
  upsert: async (code: string, body: Record<string, unknown>) => {
    const response = await api.put(`/membership-plans/${code}`, body);
    return response.data;
  },
  remove: async (code: string) => {
    const response = await api.delete(`/membership-plans/${code}`);
    return response.data;
  },
};

export const subscriptionsApi = {
  list: async (page = 1, limit = 20, status?: string) => {
    const response = await api.get("/subscriptions", { params: { page, limit, status: status || undefined } });
    const body = response.data.data || response.data;
    return { items: body.items || [], total: body.pagination?.total ?? 0 };
  },
  grant: async (user_id: string, plan_code: string, days?: number) => {
    const response = await api.post("/subscriptions/grant", { user_id, plan_code, status: "active", days });
    return response.data;
  },
  batchGrant: async (user_ids: string[], plan_code: string, days: number) => {
    const response = await api.post("/subscriptions/batch-grant", { user_ids, plan_code, days });
    return response.data;
  },
  cancel: async (id: string) => {
    const response = await api.post(`/subscriptions/${id}/cancel`);
    return response.data;
  },
  reactivate: async (id: string) => {
    const response = await api.post(`/subscriptions/${id}/reactivate`);
    return response.data;
  },
  extend: async (id: string, days: number) => {
    const response = await api.post(`/subscriptions/${id}/extend`, { days });
    return response.data;
  },
};

export type AdminPromotion = {
  id: string;
  name: string;
  description?: string | null;
  kind: string;
  code?: string | null;
  membership_days?: number;
  membership_period_end?: string | null;
  membership_plan_code?: string | null;
  max_uses?: number | null;
  max_uses_per_user?: number;
  current_uses?: number;
  is_active: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
  created_at?: string | null;
};

export const promotionsApi = {
  list: async (params?: { kind?: string; is_active?: boolean }) => {
    const response = await api.get("/promotions", { params });
    return (response.data.data || []) as AdminPromotion[];
  },
  create: async (body: Record<string, unknown>) => {
    const response = await api.post("/promotions", body);
    return response.data;
  },
  update: async (id: string, body: Record<string, unknown>) => {
    const response = await api.patch(`/promotions/${id}`, body);
    return response.data;
  },
  remove: async (id: string) => {
    const response = await api.delete(`/promotions/${id}`);
    return response.data;
  },
  redemptions: async (params?: { promotion_id?: string; user_email?: string; page?: number; limit?: number }) => {
    const response = await api.get("/promotions/redemptions", { params });
    return response.data.data || response.data;
  },
};

export const broadcastsApi = {
  list: async () => {
    const response = await api.get("/in-app-broadcasts");
    return (response.data.data || []) as Record<string, unknown>[];
  },
  get: async (id: string) => {
    const response = await api.get(`/in-app-broadcasts/${id}`);
    return response.data.data || response.data;
  },
  create: async (body: Record<string, unknown>) => {
    const response = await api.post("/in-app-broadcasts", body);
    return response.data;
  },
  update: async (id: string, body: Record<string, unknown>) => {
    const response = await api.put(`/in-app-broadcasts/${id}`, body);
    return response.data;
  },
  remove: async (id: string) => {
    const response = await api.delete(`/in-app-broadcasts/${id}`);
    return response.data;
  },
  send: async (id: string) => {
    const response = await api.post(`/in-app-broadcasts/${id}/send`);
    return response.data;
  },
  resend: async (id: string) => {
    const response = await api.post(`/in-app-broadcasts/${id}/resend`);
    return response.data;
  },
  revoke: async (id: string) => {
    const response = await api.post(`/in-app-broadcasts/${id}/revoke`);
    return response.data;
  },
  emailRecipients: async (id: string, audience: "all" | "members") => {
    const response = await api.get(`/in-app-broadcasts/${id}/email-recipients`, { params: { audience } });
    return response.data.data || response.data;
  },
};

export const paymentsApi = {
  stats: async (days = 30) => {
    const response = await api.get("/payments/stats", { params: { days } });
    return response.data;
  },
  consents: async (page = 1, limit = 20) => {
    const response = await api.get("/payments/consents", { params: { page, limit } });
    return response.data;
  },
  subscriptionPayments: async (page = 1, pageSize = 20, search?: string) => {
    const response = await api.get("/payments/subscription-payments", {
      params: { page, page_size: pageSize, search: search || undefined },
    });
    const body = response.data;
    return {
      items: body.data || [],
      total: body.total ?? 0,
      page: body.page ?? page,
      page_size: body.page_size ?? pageSize,
    };
  },
  resync: async (consentId: string) => {
    const response = await api.post(`/payments/subscription-payments/${consentId}/resync`);
    return response.data;
  },
};

export const settingsApi = {
  get: async () => {
    const response = await api.get("/settings");
    return response.data;
  },
  setKv: async (key: string, value: unknown) => {
    const response = await api.put(`/settings/kv/${key}`, { value });
    return response.data;
  },
};

export const sourcesApi = {
  list: async () => {
    const response = await api.get("/signal-sources");
    return response.data.data || [];
  },
  create: async (body: Record<string, unknown>) => {
    const response = await api.post("/signal-sources", body);
    return response.data;
  },
  update: async (sourceId: string, body: Record<string, unknown>) => {
    const response = await api.put(`/signal-sources/${sourceId}`, body);
    return response.data;
  },
  deactivate: async (sourceId: string) => {
    const response = await api.delete(`/signal-sources/${sourceId}`);
    return response.data;
  },
};

export const agentsApi = {
  list: async () => {
    const response = await api.get("/agents");
    return response.data.data || response.data.items || [];
  },
};

export const agentReleasesApi = {
  get: async () => {
    const response = await api.get("/agents/releases");
    return response.data.data || response.data;
  },
  save: async (body: { macos: Record<string, string>; windows: Record<string, string> }) => {
    const response = await api.put("/agents/releases", body);
    return response.data;
  },
  history: async (platform?: string, limit = 50) => {
    const response = await api.get("/agents/releases/history", { params: { platform, limit } });
    return response.data.data || response.data;
  },
  publish: async (platform: "macos" | "windows", release: Record<string, string>) => {
    const response = await api.post("/agents/releases/publish", { platform, release });
    return response.data.data || response.data;
  },
  restore: async (entryId: string) => {
    const response = await api.post(`/agents/releases/history/${entryId}/restore`);
    return response.data.data || response.data;
  },
  deleteHistory: async (entryId: string) => {
    const response = await api.delete(`/agents/releases/history/${entryId}`);
    return response.data.data || response.data;
  },
  localPackages: async () => {
    const response = await api.get("/agents/releases/local-packages");
    return response.data.data || response.data;
  },
  bumpVersion: async (version: string) => {
    const response = await api.post("/agents/releases/bump-version", { version });
    return response.data.data || response.data;
  },
};

export const executionsApi = {
  list: async (params?: { page?: number; limit?: number; status?: string; user_id?: string; broker?: string }) => {
    const response = await api.get("/executions", { params });
    const body = response.data.data || response.data;
    return {
      items: body.items || [],
      total: body.pagination?.total ?? 0,
    };
  },
  get: async (id: string) => {
    const response = await api.get(`/executions/${id}`);
    return response.data.data || response.data;
  },
};

export type InboundEmailListItem = {
  id: string;
  resend_email_id: string;
  from_address: string;
  to_addresses: string[];
  subject?: string | null;
  received_at?: string | null;
  created_at?: string | null;
  read_at?: string | null;
  is_read: boolean;
  fetch_error?: string | null;
  is_support_ticket?: boolean;
  reply_to_address?: string;
};

export type InboundEmailDetail = InboundEmailListItem & {
  cc?: string[];
  bcc?: string[];
  message_id?: string | null;
  html?: string | null;
  text?: string | null;
  headers?: Record<string, unknown> | null;
  attachments?: Array<{ id?: string; filename?: string; name?: string; content_type?: string }>;
};

export const inboundMailApi = {
  unreadCount: async () => {
    const response = await api.get("/inbound-mails/unread-count");
    return response.data.data || response.data;
  },
  list: async (params?: { page?: number; page_size?: number; email?: string }) => {
    const response = await api.get("/inbound-mails", { params });
    return response.data.data || response.data;
  },
  get: async (id: string) => {
    const response = await api.get(`/inbound-mails/${id}`);
    return response.data.data || response.data;
  },
  read: async (id: string) => {
    const response = await api.post(`/inbound-mails/${id}/read`);
    return response.data;
  },
  reply: async (id: string, body: { text: string; html?: string | null }) => {
    const response = await api.post(`/inbound-mails/${id}/reply`, body);
    return response.data;
  },
  send: async (body: {
    from_email?: string;
    to: string;
    subject: string;
    text: string;
    html?: string | null;
  }) => {
    const response = await api.post("/inbound-mails/send", body);
    return response.data;
  },
  attachmentUrl: (id: string, attachmentId: string) =>
    `/api/admin/inbound-mails/${id}/attachments/${attachmentId}`,
};
