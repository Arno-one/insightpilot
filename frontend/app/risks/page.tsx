"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDateTime, getRiskMeta, getStatusMeta } from "@/lib/presentation";

type RiskSnapshot = {
  risk_snapshot_id: string;
  customer_id: string;
  customer_name: string | null;
  owner_user_id: string;
  owner_user_name: string | null;
  risk_score: number;
  risk_level: string;
  llm_reason: string;
  llm_suggestion: string;
  status: string;
  created_at: string;
};

function customerLabel(item: RiskSnapshot) {
  return item.customer_name ? `${item.customer_name} / ${item.customer_id}` : item.customer_id;
}

function customerDetailHref(item: RiskSnapshot) {
  return `/customers/${item.customer_id}?riskSnapshotId=${item.risk_snapshot_id}`;
}

function RisksPageContent() {
  const searchParams = useSearchParams();
  const customerFilter = searchParams.get("customerId");
  const ownerUserFilter = searchParams.get("ownerUserId");
  const ownerUserName = searchParams.get("ownerUserName");

  const [items, setItems] = useState<RiskSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadRisks() {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams();
      if (customerFilter) {
        query.set("customer_id", customerFilter);
      }
      if (ownerUserFilter) {
        query.set("owner_user_id", ownerUserFilter);
      }
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const response = await apiFetch<RiskSnapshot[]>(`/api/risk/snapshots${suffix}`);
      setItems(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "风险列表加载失败。");
    } finally {
      setLoading(false);
    }
  }

  async function triggerScan() {
    setMessage("");
    setError("");
    try {
      const response = await apiFetch<{ job_id: string }>("/api/risk/scan", { method: "POST" });
      setMessage(`风险扫描任务已提交，任务号：${response.data.job_id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "风险扫描提交失败，请确认 Redis/RQ 是否已启动。");
    }
  }

  useEffect(() => {
    void loadRisks();
  }, [customerFilter, ownerUserFilter]);

  // 中文注释：风险页仍然先按风险分倒序，保证从经营报告跳过来时第一眼看到的就是最危险的客户。
  const sortedItems = useMemo(() => [...items].sort((a, b) => b.risk_score - a.risk_score), [items]);
  const highRiskCount = sortedItems.filter((item) => item.risk_level === "high").length;
  const mediumRiskCount = sortedItems.filter((item) => item.risk_level === "medium").length;
  const pendingCount = sortedItems.filter((item) => item.status === "pending").length;
  const topRisk = sortedItems[0];
  const clearFilterHref = customerFilter ? `/risks?customerId=${customerFilter}` : "/risks";

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Risk Signals</p>
          <h1>先看客户为什么会失速，再决定团队今天该先做什么。</h1>
          <p className="lead">
            这里集中展示规则引擎识别出的风险级别、AI 解释、建议动作与待审批状态，现在也可以直接下钻到客户级工作台。
            {customerFilter ? ` 当前已聚焦客户 ${customerFilter}。` : ""}
            {ownerUserFilter ? ` 当前已按负责人 ${ownerUserName || ownerUserFilter} 过滤。` : ""}
          </p>
        </div>
        <div className="page-actions">
          <button className="button" onClick={triggerScan} type="button">
            触发风险扫描
          </button>
          <button className="button-secondary" onClick={loadRisks} type="button">
            刷新风险快照
          </button>
        </div>
      </section>

      {ownerUserFilter ? (
        <section className="command-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Report Drilldown</p>
              <h2>当前负责人风险明细</h2>
              <p className="panel-copy">
                当前列表已按负责人 {ownerUserName || ownerUserFilter} 精确过滤，方便从经营报告直接落到这位负责人的风险客户名单。
              </p>
            </div>
            <div className="page-actions">
              <Link className="button-secondary" href={clearFilterHref}>
                清除负责人过滤
              </Link>
            </div>
          </div>
        </section>
      ) : null}

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} detail="如果刚启动本地环境，请确认后端、Redis 与 Worker 都已就绪。" /> : null}
      {loading ? <LoadingCard detail="正在同步客户风险快照、AI 建议与审批状态。" /> : null}
      {!loading && !sortedItems.length && !error ? (
        <EmptyCard
          text={ownerUserFilter ? "当前负责人还没有命中的风险快照。" : "当前还没有风险快照。"}
          detail={
            ownerUserFilter
              ? "可以先回到经营报告，确认这位负责人当前更多是执行压力还是风险客户压力。"
              : "可以先触发一轮风险扫描，系统会把结果写回这里。"
          }
        />
      ) : null}

      {sortedItems.length ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{highRiskCount}</strong>
              <span className="metric-label">高风险客户</span>
              <p className="metric-detail">建议优先进入人工确认与动作派发。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{mediumRiskCount}</strong>
              <span className="metric-label">中风险客户</span>
              <p className="metric-detail">值得持续盯防，防止进一步恶化。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{pendingCount}</strong>
              <span className="metric-label">待审批动作</span>
              <p className="metric-detail">AI 已提出建议，但还没有变成正式任务。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{topRisk?.risk_score ?? 0}</strong>
              <span className="metric-label">最高风险分</span>
              <p className="metric-detail">{topRisk ? `当前来自 ${customerLabel(topRisk)}` : "暂无风险数据"}</p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Highest Alert</p>
                  <h2>{ownerUserFilter ? "这位负责人当前最值得先处理的风险" : "当前最需要优先处理的风险"}</h2>
                </div>
                {topRisk ? (
                  <Link className="button-secondary" href={customerDetailHref(topRisk)}>
                    打开客户工作台
                  </Link>
                ) : null}
              </div>
              {topRisk ? (
                <div className="summary-item">
                  <strong>{customerLabel(topRisk)}</strong>
                  <p>{topRisk.llm_reason}</p>
                  <div className="meta-row">
                    <span className={`pill ${getRiskMeta(topRisk.risk_level).toneClass}`}>{getRiskMeta(topRisk.risk_level).label}</span>
                    <span className={`pill ${getStatusMeta(topRisk.status).toneClass}`}>{getStatusMeta(topRisk.status).label}</span>
                    <span className="meta-chip">负责人 {topRisk.owner_user_name || topRisk.owner_user_id}</span>
                    <span className="meta-chip">快照时间 {formatDateTime(topRisk.created_at)}</span>
                  </div>
                  <p>{topRisk.llm_suggestion}</p>
                </div>
              ) : null}
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Reading Guide</p>
                  <h2>{ownerUserFilter ? "负责人风险下钻要回答什么问题" : "风险看板要回答什么问题"}</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>先看最危险的客户是谁</strong>
                  <p>风险页默认按风险分倒序，保证管理层打开页面就先看到最需要马上介入的客户。</p>
                </div>
                <div className="detail-item">
                  <strong>再看问题集中在哪位负责人</strong>
                  <p>如果同一个负责人连续命中多条高风险客户，就要回到任务、审批和跟进节奏继续下钻。</p>
                </div>
                <div className="detail-item">
                  <strong>最后回到客户细节和动作闭环</strong>
                  <p>风险只是入口，真正的处理动作还是要回到客户详情页，把审批、任务和跟进链路串起来。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="risk-board">
            {sortedItems.map((item) => (
              <article className="risk-card" key={item.risk_snapshot_id}>
                <div className="risk-card-header">
                  <div>
                    <p className="eyebrow">{customerLabel(item)}</p>
                    <h2 className="report-title">{item.llm_reason || "当前没有风险解释。"}</h2>
                  </div>
                  <div className="risk-meta">
                    <span className={`pill ${getRiskMeta(item.risk_level).toneClass}`}>{getRiskMeta(item.risk_level).label}</span>
                    <span className={`pill ${getStatusMeta(item.status).toneClass}`}>{getStatusMeta(item.status).label}</span>
                    <span className="meta-chip">风险分 {item.risk_score}</span>
                    <span className="meta-chip">负责人 {item.owner_user_name || item.owner_user_id}</span>
                    <span className="meta-chip">快照时间 {formatDateTime(item.created_at)}</span>
                  </div>
                </div>

                <div className="summary-list">
                  <div className="summary-item">
                    <strong>风险解释</strong>
                    <p>{item.llm_reason || "当前没有风险解释。"}</p>
                  </div>
                  <div className="summary-item">
                    <strong>动作建议</strong>
                    <p>{item.llm_suggestion || "当前没有动作建议。"}</p>
                  </div>
                </div>

                <div className="page-actions">
                  <Link className="button-secondary" href={customerDetailHref(item)}>
                    查看客户详情
                  </Link>
                </div>
              </article>
            ))}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}

export default function RisksPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <LoadingCard detail="正在同步客户风险快照、AI 建议与审批状态。" />
        </AppShell>
      }
    >
      <RisksPageContent />
    </Suspense>
  );
}
