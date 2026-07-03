"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { clearSession, CurrentUser, fetchCurrentUser, getDefaultRoute, getStoredUser, hasAnyPermission, saveStoredUser } from "@/lib/api";

type NavItem = {
  label: string;
  href: string;
  permissions: string[];
  eyebrow: string;
  summary: string;
};

const SIDEBAR_SCROLL_KEY = "insightpilot_sidebar_scroll_top";

const navItems: NavItem[] = [
  {
    label: "经营驾驶舱",
    href: "/dashboard",
    permissions: ["crm:customer:read:self"],
    eyebrow: "Command Overview",
    summary: "汇总今日风险、审批、执行与日报信号，给管理层一个可立即行动的全景面板。"
  },
  {
    label: "数据导入",
    href: "/imports",
    permissions: ["crm:customer:read:self"],
    eyebrow: "CRM Intake",
    summary: "把客户、商机和跟进记录按统一模板导入系统，并在入库前就拿到清晰校验反馈。"
  },
  {
    label: "客户工作台",
    href: "/customers",
    permissions: ["crm:customer:read:self"],
    eyebrow: "Customer Workbench",
    summary: "按客户维度恢复历史对话、查看风险摘要，并直接和 Risk Agent 连续协作。"
  },
  {
    label: "客户风险中心",
    href: "/risks",
    permissions: ["crm:risk:read:team", "crm:risk:read:all"],
    eyebrow: "Risk Signals",
    summary: "把沉默客户、竞品介入与高金额商机的异常波动集中展示，方便快速排险。"
  },
  {
    label: "AI 任务审批",
    href: "/approvals",
    permissions: ["approval:review:agent_task"],
    eyebrow: "Human Checkpoint",
    summary: "所有 AI 动作先经过主管把关，再进入正式的销售执行闭环。"
  },
  {
    label: "销售任务",
    href: "/tasks",
    permissions: ["task:read:self", "task:read:team", "task:read:all"],
    eyebrow: "Execution Queue",
    summary: "聚焦谁来做、何时做、做到哪一步，让建议真正变成落地动作。"
  },
  {
    label: "经营报告",
    href: "/reports",
    permissions: ["report:read:team", "report:read:all"],
    eyebrow: "Executive Brief",
    summary: "把风险、任务与经营指标压缩成老板和主管都能快速消费的简报。"
  },
  {
    label: "RAG 评估",
    href: "/rag-evaluation",
    permissions: ["rag:ingest:run"],
    eyebrow: "Retrieval Quality",
    summary: "量化知识库命中质量，让检索调优有指标、有证据、可回看。"
  },
  {
    label: "Agent 追踪",
    href: "/agent-trace",
    permissions: ["agent:log:read"],
    eyebrow: "Execution Trace",
    summary: "把 Agent 节点、工具输出和 RAG 证据串成一条可审计的执行链路。"
  },
  {
    label: "系统管理",
    href: "/system/access-control",
    permissions: ["system:rbac:manage", "system:user_role:manage"],
    eyebrow: "Access Control",
    summary: "集中维护角色权限开关和用户角色分配，确保系统访问边界清晰可控。"
  }
];

function roleLabel(roleCodes: string[] | undefined) {
  if (!roleCodes?.length) {
    return "访客";
  }

  const role = roleCodes[0];
  if (role === "owner") {
    return "老板";
  }
  if (role === "manager") {
    return "销售主管";
  }
  if (role === "salesperson") {
    return "销售员";
  }
  if (role === "admin") {
    return "系统管理员";
  }
  return role;
}

function isNavActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const sidebarRef = useRef<HTMLElement | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const cachedUser = getStoredUser();
    if (!cachedUser) {
      router.replace("/login");
      return;
    }

    // 中文注释：先用本地登录态起屏，再主动向后端刷新一次，避免数据库真实姓名已更新但前端还停留在旧的 ???。
    setUser(cachedUser);
    setReady(true);

    let cancelled = false;

    async function refreshCurrentUser() {
      try {
        const response = await fetchCurrentUser();
        if (cancelled) {
          return;
        }
        setUser(response.data);
        saveStoredUser(response.data);
      } catch {
        if (cancelled) {
          return;
        }
      }
    }

    refreshCurrentUser();

    return () => {
      cancelled = true;
    };
  }, [router]);

  // 中文注释：导航仍然由权限控制，保证演示态和真实接口权限校验保持一致。
  const visibleNav = useMemo(() => navItems.filter((item) => hasAnyPermission(user, item.permissions)), [user]);
  const currentSection = visibleNav.find((item) => isNavActive(pathname, item.href)) || visibleNav[0] || navItems[0];

  useEffect(() => {
    if (!ready || !user || !visibleNav.length) {
      return;
    }
    if (!visibleNav.some((item) => isNavActive(pathname, item.href))) {
      router.replace(getDefaultRoute(user));
    }
  }, [pathname, ready, router, user, visibleNav]);

  useEffect(() => {
    if (!ready || typeof window === "undefined" || !sidebarRef.current) {
      return;
    }
    // 中文注释：记住左侧导航自己的滚动位置，切模块时只刷新右侧工作区，不把导航强行拉回顶部。
    const raw = window.sessionStorage.getItem(SIDEBAR_SCROLL_KEY);
    if (!raw) {
      return;
    }
    const scrollTop = Number(raw);
    if (Number.isNaN(scrollTop)) {
      return;
    }
    requestAnimationFrame(() => {
      if (sidebarRef.current) {
        sidebarRef.current.scrollTop = scrollTop;
      }
    });
  }, [ready, pathname]);

  function handleSidebarScroll() {
    if (typeof window === "undefined" || !sidebarRef.current) {
      return;
    }
    window.sessionStorage.setItem(SIDEBAR_SCROLL_KEY, String(sidebarRef.current.scrollTop));
  }

  function handleLogout() {
    clearSession();
    router.replace("/login");
  }

  if (!ready) {
    return (
      <main className="loading-page">
        <div className="loading-copy">
          <p className="eyebrow">Booting Command Deck</p>
          <h1 className="loading-title">正在接入 InsightPilot 指挥台</h1>
          <p className="loading-subtitle">正在校验身份、装载权限与今日经营链路，请稍候。</p>
        </div>
      </main>
    );
  }

  return (
    <div className="shell">
      <aside
        className="sidebar"
        ref={sidebarRef}
        onScroll={handleSidebarScroll}
        style={{ maxHeight: "100vh", overflowY: "auto", overscrollBehavior: "contain" }}
      >
        <div className="brand-block">
          <span className="brand-mark">IP</span>
          <div>
            <p className="brand-eyebrow">Sales War Room</p>
            <strong className="brand-title">InsightPilot</strong>
            <p className="brand-copy">把 CRM 的沉默信号翻译成今天就能执行的经营动作。</p>
          </div>
        </div>

        <div className="user-plate">
          <div>
            <p className="eyebrow">当前席位</p>
            <strong>{user?.real_name}</strong>
          </div>
          <span>{roleLabel(user?.role_codes)}</span>
          <small>{user?.username}</small>
        </div>

        <nav className="nav" aria-label="主导航">
          {visibleNav.map((item) => (
            <Link className={isNavActive(pathname, item.href) ? "active" : ""} key={item.href} href={item.href}>
              <span>{item.label}</span>
              <small>{item.eyebrow}</small>
            </Link>
          ))}
        </nav>

        <div className="sidebar-footer">
          <p className="eyebrow">协作规则</p>
          <p>AI 负责识别和建议，人来做最终决策，所有动作都保留证据链。</p>
          <button className="ghost-button" onClick={handleLogout} type="button">
            退出当前席位
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="shell-topbar">
          <div>
            <p className="eyebrow">{currentSection.eyebrow}</p>
            <h2 className="shell-section-title">{currentSection.label}</h2>
            <p className="shell-section-copy">{currentSection.summary}</p>
          </div>
          <div className="topbar-pills">
            <span className="info-pill">权限已载入</span>
            <span className="info-pill">人工审批开启</span>
            <span className="info-pill">Trace 可审计</span>
          </div>
        </header>

        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}
