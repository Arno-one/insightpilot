"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { clearSession, CurrentUser, getStoredUser, hasAnyPermission } from "@/lib/api";

const navItems = [
  { label: "经营驾驶舱", href: "/dashboard", permissions: ["crm:customer:read:self"] },
  { label: "客户风险中心", href: "/risks", permissions: ["crm:risk:read:team", "crm:risk:read:all"] },
  { label: "AI 任务审批", href: "/approvals", permissions: ["approval:review:agent_task"] },
  { label: "销售任务", href: "/tasks", permissions: ["task:read:self", "task:read:team", "task:read:all"] },
  { label: "经营报告", href: "/reports", permissions: ["report:read:team", "report:read:all"] },
  { label: "RAG 评估", href: "/rag-evaluation", permissions: ["rag:ingest:run"] },
  { label: "Agent 追踪", href: "/agent-trace", permissions: ["agent:log:read"] }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const storedUser = getStoredUser();
    if (!storedUser) {
      router.replace("/login");
      return;
    }
    setUser(storedUser);
    setReady(true);
  }, [router]);

  function handleLogout() {
    clearSession();
    router.replace("/login");
  }

  if (!ready) {
    return <main className="loading-page">正在进入 InsightPilot 工作台...</main>;
  }

  const visibleNav = navItems.filter((item) => hasAnyPermission(user, item.permissions));

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">I</span>
          InsightPilot
        </div>
        <div className="user-plate">
          <strong>{user?.real_name}</strong>
          <span>{user?.role_codes.join(" / ")}</span>
        </div>
        <nav className="nav">
          {visibleNav.map((item) => (
            <Link className={pathname === item.href ? "active" : ""} key={item.href} href={item.href}>
              {item.label}
            </Link>
          ))}
        </nav>
        <button className="ghost-button" onClick={handleLogout} type="button">
          退出登录
        </button>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
