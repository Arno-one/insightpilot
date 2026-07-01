"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDateTime, getRiskMeta, getStatusMeta } from "@/lib/presentation";

type RiskSnapshot = {
  risk_snapshot_id: string;
  customer_id: string;
  owner_user_id: string;
  owner_user_name: string | null;
  risk_score: number;
  risk_level: string;
  llm_reason: string;
  llm_suggestion: string;
  status: string;
  created_at: string;
};

export default function RisksPage() {
  const [items, setItems] = useState<RiskSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadRisks() {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<RiskSnapshot[]>("/api/risk/snapshots");
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
    loadRisks();
  }, []);

  // 中文注释：前端先按风险分重排，确保主管打开页面第一眼就看到最危险的客户。
  const sortedItems = useMemo(() => [...items].sort((a, b) => b.risk_score - a.risk_score), [items]);
  const highRiskCount = sortedItems.filter((item) => item.risk_level === "high").length;
  const mediumRiskCount = sortedItems.filter((item) => item.risk_level === "medium").length;
  const pendingCount = sortedItems.filter((item) => item.status === "pending").length;
  const topRisk = sortedItems[0];

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Risk Signals</p>
          <h1>先看客户为什么会失速，再决定团队今天该先做什么。</h1>
          <p className="lead">这里集中展示规则引擎识别出的风险级别、AI 解释、建议动作与待审批状态。</p>
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

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} detail="如果刚启动本地环境，请确认后端、Redis 与 Worker 都已就绪。" /> : null}
      {loading ? <LoadingCard detail="正在同步客户风险快照、AI 建议与审批状态。" /> : null}
      {!loading && !sortedItems.length && !error ? (
        <EmptyCard text="当前还没有风险快照。" detail="可以先触发一轮风险扫描，系统会把结果写回这里。" />
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
              <p className="metric-detail">{topRisk ? `当前来自客户 ${topRisk.customer_id}` : "暂无风险数据"}</p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Highest Alert</p>
                  <h2>当前最需要优先处理的风险</h2>
                </div>
              </div>
              {topRisk ? (
                <div className="summary-item">
                  <strong>{topRisk.customer_id}</strong>
                  <p>{topRisk.llm_reason}</p>
                  <div className="meta-row">
                    <span className={`pill ${getRiskMeta(topRisk.risk_level).toneClass}`}>{getRiskMeta(topRisk.risk_level).label}</span>
                    <span className={`pill ${getStatusMeta(topRisk.status).toneClass}`}>{getStatusMeta(topRisk.status).label}</span>
                    <span className="meta-chip">风险分 {topRisk.risk_score}</span>
                    <span className="meta-chip">负责人 {topRisk.owner_user_name || topRisk.owner_user_id}</span>
                  </div>
                </div>
              ) : null}
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Response Rule</p>
                  <h2>处理建议</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>高风险先看原因</strong>
                  <p>如果是报价后无回应、竞品介入、长期未跟进，优先确认是否需要主管介入或重新设计跟进话术。</p>
                </div>
                <div className="detail-item">
                  <strong>审批不宜堆积</strong>
                  <p>风险建议若长时间停留在待审批，会让 AI 输出停在“纸面建议”，无法进入执行闭环。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="risk-board">
            {sortedItems.map((item) => {
              const riskMeta = getRiskMeta(item.risk_level);
              const statusMeta = getStatusMeta(item.status);

              return (
                <article className="risk-card" key={item.risk_snapshot_id}>
                  <div className="risk-card-header">
                    <div>
                      <p className="eyebrow">Customer {item.customer_id}</p>
                      <h2 className="section-title">风险分 {item.risk_score}</h2>
                    </div>
                    <div className="risk-meta">
                      <span className={`pill ${riskMeta.toneClass}`}>{riskMeta.label}</span>
                      <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                    </div>
                  </div>

                  <div className="meta-row">
                    <span className="meta-chip">负责人 {item.owner_user_name || item.owner_user_id}</span>
                    <span className="meta-chip">快照时间 {formatDateTime(item.created_at)}</span>
                  </div>

                  <div className="summary-list">
                    <div className="summary-item">
                      <strong>风险原因</strong>
                      <p>{item.llm_reason}</p>
                    </div>
                    <div className="summary-item">
                      <strong>建议动作</strong>
                      <p>{item.llm_suggestion}</p>
                    </div>
                  </div>
                </article>
              );
            })}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
