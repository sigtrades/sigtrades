import { useState, useEffect, useCallback, useMemo, type ComponentType, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import clsx from "clsx";
import {
  HomeIcon,
  UsersIcon,
  CreditCardIcon,
  ArrowRightOnRectangleIcon,
  Bars3Icon,
  XMarkIcon,
  Cog6ToothIcon,
  BanknotesIcon,
  EnvelopeIcon,
  TicketIcon,
  ChatBubbleLeftRightIcon,
  ChartBarIcon,
  CpuChipIcon,
  ClipboardDocumentListIcon,
  SignalIcon,
  ArrowDownTrayIcon,
} from "@heroicons/react/24/outline";
import { useAuthStore } from "@/store/auth";
import { adminRoleLabel, filterNavigationGroups } from "@/lib/adminPermissions";
import api, { inboundMailApi } from "@/api";

interface NavItem {
  name: string;
  href: string;
  icon: ComponentType<{ className?: string }>;
  badgeKey?: "inboundUnread";
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

/** 避免 /agents 与 /agents/release 同时高亮 */
function isNavItemActive(pathname: string, href: string, allHrefs: string[]): boolean {
  if (pathname === href) return true;
  if (href === "/") return false;
  if (!pathname.startsWith(`${href}/`)) return false;
  return !allHrefs.some(
    (other) =>
      other !== href &&
      other.startsWith(`${href}/`) &&
      (pathname === other || pathname.startsWith(`${other}/`)),
  );
}

const navigationGroups: NavGroup[] = [
  {
    title: "总览",
    items: [{ name: "仪表盘", href: "/", icon: HomeIcon }],
  },
  {
    title: "用户",
    items: [
      { name: "用户管理", href: "/users", icon: UsersIcon },
      { name: "用户数据", href: "/users/analytics", icon: ChartBarIcon },
      { name: "用户通知", href: "/in-app-messages", icon: ChatBubbleLeftRightIcon },
    ],
  },
  {
    title: "商业化",
    items: [
      { name: "支付管理", href: "/payments", icon: CreditCardIcon },
      { name: "会员套餐", href: "/membership-plans", icon: BanknotesIcon },
      { name: "活动 / 兑换码", href: "/promotions", icon: TicketIcon },
    ],
  },
  {
    title: "Agent 与执行",
    items: [
      { name: "Agent 连接", href: "/agents", icon: CpuChipIcon },
      { name: "Agent 发布", href: "/agents/release", icon: ArrowDownTrayIcon },
      { name: "执行记录", href: "/executions", icon: ClipboardDocumentListIcon },
      { name: "频道胜率", href: "/channel-stats", icon: ChartBarIcon },
      { name: "信号源", href: "/signal-sources", icon: SignalIcon },
    ],
  },
  {
    title: "支持",
    items: [{ name: "入站邮件", href: "/inbound-mail", icon: EnvelopeIcon, badgeKey: "inboundUnread" }],
  },
  {
    title: "系统",
    items: [{ name: "系统设置", href: "/settings", icon: Cog6ToothIcon }],
  },
];

function SidebarNavLinks({
  groups,
  pathname,
  badges,
  onItemClick,
}: {
  groups: NavGroup[];
  pathname: string;
  badges: { inboundUnread: number };
  onItemClick?: () => void;
}) {
  const allHrefs = groups.flatMap((g) => g.items.map((i) => i.href));

  return (
    <>
      {groups.map((group) => (
        <div key={group.title} className="mb-4 last:mb-0">
          <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            {group.title}
          </p>
          <div className="space-y-0.5">
            {group.items.map((item) => {
              const active = isNavItemActive(pathname, item.href, allHrefs);
              const badge = item.badgeKey ? badges[item.badgeKey] : 0;
              return (
                <Link
                  key={item.href}
                  to={item.href}
                  onClick={onItemClick}
                  className={clsx(
                    "flex items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    active ? "bg-brand-50 text-brand-700" : "text-slate-700 hover:bg-slate-100",
                  )}
                >
                  <item.icon className="mr-3 h-5 w-5 shrink-0" />
                  <span className="flex-1">{item.name}</span>
                  {badge > 0 ? (
                    <span className="ml-2 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-brand-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                      {badge > 99 ? "99+" : badge}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </>
  );
}

export default function MainLayout({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [badges, setBadges] = useState({ inboundUnread: 0 });
  const location = useLocation();
  const navigate = useNavigate();
  const { username, role, logout } = useAuthStore();

  const filteredGroups = useMemo(() => filterNavigationGroups(navigationGroups, role), [role]);

  useEffect(() => {
    void api.get("/me").catch(() => {});
  }, []);

  const fetchBadges = useCallback(async () => {
    try {
      const data = await inboundMailApi.unreadCount();
      setBadges({ inboundUnread: data.count ?? 0 });
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void fetchBadges();
    const interval = window.setInterval(() => void fetchBadges(), 60_000);
    return () => window.clearInterval(interval);
  }, [fetchBadges]);

  useEffect(() => {
    const onInboundUpdated = () => {
      void fetchBadges();
    };
    window.addEventListener("admin:inbound-mail-updated", onInboundUpdated);
    return () => window.removeEventListener("admin:inbound-mail-updated", onInboundUpdated);
  }, [fetchBadges]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-50 w-64 transform border-r border-slate-200 bg-white transition-transform lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-slate-200 px-4">
          <span className="text-lg font-bold text-brand-600">SigTrades Admin</span>
          <button type="button" className="lg:hidden" onClick={() => setSidebarOpen(false)}>
            <XMarkIcon className="h-6 w-6 text-slate-500" />
          </button>
        </div>
        <nav className="overflow-y-auto p-3">
          <SidebarNavLinks
            groups={filteredGroups}
            pathname={location.pathname}
            badges={badges}
            onItemClick={() => setSidebarOpen(false)}
          />
        </nav>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur lg:px-8">
          <button type="button" className="lg:hidden" onClick={() => setSidebarOpen(true)}>
            <Bars3Icon className="h-6 w-6 text-slate-600" />
          </button>
          <div className="hidden text-sm text-slate-500 lg:block">管理后台 · ET 时区</div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">
              {username || "admin"} · {adminRoleLabel(role)}
            </span>
            <button type="button" onClick={handleLogout} className="inline-flex items-center gap-1 text-slate-600 hover:text-slate-900">
              <ArrowRightOnRectangleIcon className="h-5 w-5" />
              退出
            </button>
          </div>
        </header>
        <main className="p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
