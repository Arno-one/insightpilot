import Link from "next/link";

const navItems = [
  ["经营驾驶舱", "/dashboard"],
  ["客户风险中心", "/risks"],
  ["AI 任务审批", "/approvals"],
  ["销售任务", "/tasks"],
  ["经营报告", "/reports"],
  ["Agent 追踪", "/agent-trace"]
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">I</span>
          InsightPilot
        </div>
        <nav className="nav">
          {navItems.map(([label, href]) => (
            <Link key={href} href={href}>
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
