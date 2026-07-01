"use client";

import { useEffect, useState } from "react";

import { LoadingCard, ErrorCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch, getStoredUser, hasAnyPermission } from "@/lib/api";

type RiskSnapshot = { risk_level: string };
type Approval = { status: string };
type Task = { status: string };
type Report = { report_id: string; summary: string; suggestions: string };

type DashboardState = {
  risks: RiskSnapshot[];
  approvals: Approval[];
  tasks: Task[];
  reports: Report[];
};

export default function DashboardPage() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadDashboard() {
      try {
        const user = getStoredUser();
        const canReadRisk = hasAnyPermission(user, ["crm:risk:read:team", "crm:risk:read:all"]);
        const canReviewApproval = hasAnyPermission(user, ["approval:review:agent_task"]);
        const canReadReport = hasAnyPermission(user, ["report:read:team", "report:read:all"]);
        const [risks, approvals, tasks, reports] = await Promise.all([
          canReadRisk ? apiFetch<RiskSnapshot[]>("/api/risk/snapshots") : Promise.resolve({ data: [] }),
          canReviewApproval ? apiFetch<Approval[]>("/api/approvals") : Promise.resolve({ data: [] }),
          apiFetch<Task[]>("/api/tasks"),
          canReadReport ? apiFetch<Report[]>("/api/reports") : Promise.resolve({ data: [] })
        ]);
        setState({
          risks: risks.data,
          approvals: approvals.data,
          tasks: tasks.data,
          reports: reports.data
        });
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "驾驶舱数据加载失败");
      }
    }
    loadDashboard();
  }, []);

  const highRiskCount = state?.risks.filter((item) => item.risk_level === "high").length ?? 0;
  const pendingApprovalCount = state?.approvals.filter((item) => item.status === "pending").length ?? 0;
  const activeTaskCount = state?.tasks.filter((item) => ["pending", "in_progress"].includes(item.status)).length ?? 0;
  const latestReport = state?.reports[0];

  return (
    <AppShell>
      <section className="hero">
        <p className="eyebrow">Command room</p>
        <h1>把 CRM 里的沉默信号，变成今天就能执行的动作。</h1>
        <p className="lead">InsightPilot 会识别报价后无回应、竞品介入、长期未跟进等风险，并把 Agent 建议送入主管审批流。</p>
      </section>

      <section className="grid">
        {error ? <ErrorCard message={error} /> : null}
        {!state && !error ? <LoadingCard /> : null}
        {state ? (
          <>
            <div className="card">
              <strong className="danger">{highRiskCount}</strong>
              <span>高风险客户</span>
            </div>
            <div className="card">
              <strong>{state.risks.length}</strong>
              <span>风险快照</span>
            </div>
            <div className="card">
              <strong>{pendingApprovalCount}</strong>
              <span>待确认 AI 任务</span>
            </div>
            <div className="card">
              <strong>{activeTaskCount}</strong>
              <span>进行中销售任务</span>
            </div>
            <div className="card wide">
              <p className="eyebrow">今日经营摘要</p>
              <span>{latestReport?.summary || "暂无经营日报，请先在经营报告页生成日报。"}</span>
            </div>
            <div className="card wide">
              <p className="eyebrow">Agent next move</p>
              <span>{latestReport?.suggestions || "建议先运行风险扫描，再生成经营日报，形成完整经营闭环。"}</span>
            </div>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
