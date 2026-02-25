"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getToken, getUser } from "@/lib/auth";
import { UserRole } from "@/lib/types";

interface AuthGuardProps {
  roles?: UserRole[];
  children: React.ReactNode;
}

export default function AuthGuard({ roles, children }: AuthGuardProps) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getToken();
    const user = getUser();

    if (!token || !user) {
      router.replace("/login");
      return;
    }

    if (roles && !roles.includes(user.role)) {
      router.replace(user.role === "teacher" ? "/teacher" : "/dashboard");
      return;
    }

    setReady(true);
  }, [roles, router]);

  if (!ready) {
    return <div className="pageLoading">Загрузка...</div>;
  }

  return <>{children}</>;
}
