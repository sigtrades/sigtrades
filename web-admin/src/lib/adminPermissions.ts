export type AdminRole = "admin" | "operations";

export const OPERATIONS_FORBIDDEN_PATHS = new Set([
  "/membership-plans",
  "/promotions",
  "/settings",
  "/signal-sources",
]);

export const OPERATIONS_GUARANTEED_PATHS = new Set(["/payments"]);

export function canAccessAdminPath(role: AdminRole | null | undefined, path: string): boolean {
  if (role !== "operations") return true;
  const base = path.split("?")[0];
  if (OPERATIONS_GUARANTEED_PATHS.has(base)) return true;
  return !OPERATIONS_FORBIDDEN_PATHS.has(base);
}

export function canManageUserStatus(role: AdminRole | null | undefined): boolean {
  return role === "admin";
}

export function canWriteAdmin(role: AdminRole | null | undefined): boolean {
  return role === "admin";
}

export function adminRoleLabel(role: AdminRole | null | undefined): string {
  return role === "operations" ? "运营" : "管理员";
}

export function filterNavigationGroups<T extends { items: { href: string }[] }>(
  groups: T[],
  role: AdminRole | null | undefined,
): T[] {
  if (!role || role === "admin") return groups;
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => canAccessAdminPath(role, item.href)),
    }))
    .filter((group) => group.items.length > 0);
}
