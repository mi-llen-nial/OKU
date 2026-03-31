import type { UserRole } from "@/lib/types";

/**
 * Default home route after login for each global role (platform only).
 */
export function resolveRoleHome(role: string): string {
  if (role === "teacher") return "/teacher";
  if (role === "institution_admin") return "/institution-admin";
  if (role === "methodist") return "/methodist";
  if (role === "superadmin") return "/superadmin";
  return "/dashboard";
}

export function isUserRole(value: string): value is UserRole {
  return ["student", "teacher", "methodist", "institution_admin", "superadmin"].includes(value);
}
