"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ErrorCard, LoadingCard } from "@/components/DataState";
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
        setError(exc instanceof Error ? exc.message : "驾驶舱数据加载失败。");
      }
    }

    loadDashboard();
  }, []);

  // 中文注释：驾驶舱只做轻量聚合，不改后端接口，也能先把今天最关键的经营信号抬出来。
  const overview = useMemo(() => {
    const risks = state?.risks || [];
    const approvals = state?.approvals || [];
    const tasks = state?.tasks || [];
    const reports = state?.reports || [];

    return {
      highRiskCount: risks.filter((item) => item.risk_level === "high").length,
      mediumRiskCount: risks.filter((item) => item.risk_level === "medium").length,
      pendingApprovalCount: approvals.filter((item) => item.status === "pending").length,
      activeTaskCount: tasks.filter((item) => ["pending", "in_progress"].includes(item.status)).length,
      latestReport: reports[0]
    };
  }, [state]);

  const commandSignals = [
    {
      title: "优先清空高风险客户",
      text:
        overview.highRiskCount > 0
          ? `当前有 ${overview.highRiskCount} 个高风险客户暴露在成交流失面前，建议先进入风险中心查看原因与动作建议。`
          : "当前没有高风险客户压顶，可以把更多精力放到审批与跟进质量上。"
    },
    {
      title: "审批节奏决定动作落地速度",
      text:
        overview.pendingApprovalCount > 0
          ? `还有 ${overview.pendingApprovalCount} 条 AI 任务等待主管确认，处理越及时，销售执行闭环越完整。`
          : "审批队列已经清空，AI 建议当前没有被卡在人工确认环节。"
    },
    {
      title: "执行队列需要持续回看",
      text:
        overview.activeTaskCount > 0
          ? `共有 ${overview.activeTaskCount} 条任务正在推进，建议同步查看任务页，避免高优先级动作在执行端失速。`
          : "当前没有进行中的销售任务，可以考虑先跑一轮风险扫描补齐动作来源。"
    }
  ];

  const nextMoves = [
    "先运行风险扫描，刷新今天的风险快照和建议动作。",
    "处理 AI 审批队列，把高价值建议转成正式销售任务。",
    "查看任务页确认负责人、截止时间和执行节奏是否合理。",
    "生成日报，把今天的风险与执行质量压缩成经营摘要。"
  ];

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Today&apos;s Command Picture</p>
          <h1>把 CRM 里的沉默信号，变成今天就能推进的经营动作。</h1>
          <p className="lead">
            这一页不是传统“看数后台”，而是给老板和主管快速判断风险、审批与执行节奏的经营指挥台。
          </p>
        </div>
        <div className="page-actions">
          <Link className="button" href="/risks">
            进入风险中心
          </Link>
          <Link className="button-secondary" href="/reports">
            查看经营报告
          </Link>
        </div>
      </section>

      {error ? <ErrorCard message={error} detail="请确认后端接口、登录态与 Redis/RQ 链路是否正常。" /> : null}
      {!state && !error ? <LoadingCard detail="正在拉取风险快照、审批队列、销售任务与最近日报。" /> : null}

      {state ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{overview.highRiskCount}</strong>
              <span className="metric-label">高风险客户</span>
              <p className="metric-detail">需要今天优先排险的客户池规模。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.mediumRiskCount}</strong>
              <span className="metric-label">中风险客户</span>
              <p className="metric-detail">值得持续观察、避免滑向高风险的客户数量。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.pendingApprovalCount}</strong>
              <span className="metric-label">待审批动作</span>
              <p className="metric-detail">AI 已给出建议，但还没进入正式执行的任务数量。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.activeTaskCount}</strong>
              <span className="metric-label">执行中任务</span>
              <p className="metric-detail">当前需要销售团队持续跟进的动作总数。</p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Command Signals</p>
                  <h2>今天最值得盯住的三条信号</h2>
                </div>
              </div>
              <div className="highlight-strip">
                <div className="highlight-card">
                  <strong>风险</strong>
                  <span>{overview.highRiskCount > 0 ? "高风险客户已抬头" : "风险面暂时可控"}</span>
                </div>
                <div className="highlight-card">
                  <strong>审批</strong>
                  <span>{overview.pendingApprovalCount > 0 ? "需要主管尽快确认" : "审批队列流速正常"}</span>
                </div>
                <div className="highlight-card">
                  <strong>执行</strong>
                  <span>{overview.activeTaskCount > 0 ? "任务正在消化中" : "执行队列偏空，适合补动作"}</span>
                </div>
              </div>
              <div className="summary-list">
                {commandSignals.map((item) => (
                  <div className="summary-item" key={item.title}>
                    <strong>{item.title}</strong>
                    <p>{item.text}</p>
                  </div>
                ))}
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Next Move</p>
                  <h2>建议的推进顺序</h2>
                </div>
              </div>
              <div className="signal-list">
                {nextMoves.map((item, index) => (
                  <div className="signal-item" key={item}>
                    <strong>步骤 {index + 1}</strong>
                    <p>{item}</p>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Daily Brief</p>
                  <h2>最新经营摘要</h2>
                </div>
                <Link className="button-secondary" href="/reports">
                  打开日报
                </Link>
              </div>
              <div className="summary-item">
                <strong>{overview.latestReport?.summary || "还没有生成日报"}</strong>
                <p>
                  {overview.latestReport?.suggestions ||
                    "建议先触发风险扫描，再生成日报，让老板和主管看到当天完整的风险、审批与执行闭环。"}
                </p>
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Closed Loop</p>
                  <h2>系统闭环说明</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>1. 风险识别</strong>
                  <p>规则引擎先判断客户是否异常，避免 LLM 直接参与风险定级。</p>
                </div>
                <div className="detail-item">
                  <strong>2. AI 解释与建议</strong>
                  <p>Agent 结合知识库与上下文给出理由、建议和推荐话术。</p>
                </div>
                <div className="detail-item">
                  <strong>3. 人工审批与任务执行</strong>
                  <p>主管确认后，建议才会变成正式销售任务，执行结果继续回流经营视图。</p>
                </div>
              </div>
            </article>
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
