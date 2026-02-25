"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return <DashboardLayout>{children}</DashboardLayout>;
}
