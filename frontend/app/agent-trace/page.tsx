"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDateTime, formatDuration, getRunTypeLabel, getStatusMeta } from "@/lib/presentation";

type AgentRun = {
  run_id: string;
  user_id: string;
  run_type: string;
  graph_name: string;
  status: string;
  total_duration_ms: number;
  started_at: string | null;
  finished_at: string | null;
};

type AgentStep = {
  step_id: string;
  node_name: string;
  tool_name: string | null;
  input_json: unknown;
  output_json: unknown;
  status: string;
  error_message: string | null;
  duration_ms: number;
  started_at: string | null;
  finished_at: string | null;
};

type RagHit = {
  hit_id: string;
  source_type: string;
  doc_id: string;
  section_id: string | null;
  rank_no: number;
  rrf_score: number | null;
  text_preview: string | null;
};

type RagTrace = {
  trace_id: string;
  original_query: string;
  rewritten_query: string | null;
  strategy: string;
  total_ms: number;
  hit_count: number;
  hits: RagHit[];
};

type RunDetail = {
  run: AgentRun & {
    input_json: unknown;
    output_json: unknown;
    error_message: string | null;
  };
  steps: AgentStep[];
  rag_traces: RagTrace[];
};

function prettyJson(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "{}";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

export default function AgentTracePage() {
  const [items, setItems] = useState<AgentRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadRuns() {
      try {
        const response = await apiFetch<AgentRun[]>("/api/agent/runs");
        setItems(response.data);
        if (response.data[0]) {
          setSelectedRunId(response.data[0].run_id);
        }
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Agent 执行记录加载失败。");
      } finally {
        setLoading(false);
      }
    }

    loadRuns();
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }

    async function loadDetail() {
      setDetailLoading(true);
      setError("");
      try {
        const response = await apiFetch<RunDetail>(`/api/agent/runs/${selectedRunId}`);
        setDetail(response.data);
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Agent 详情加载失败。");
      } finally {
        setDetailLoading(false);
      }
    }

    loadDetail();
  }, [selectedRunId]);

  // 中文注释：Trace 页先给总体健康度，再下钻具体 Run，避免一上来就被长日志淹没。
  const overview = useMemo(() => {
    const successCount = items.filter((item) => item.status === "success").length;
    const failedCount = items.filter((item) => item.status === "failed").length;
    const avgDuration = items.length
      ? Math.round(items.reduce((sum, item) => sum + (item.total_duration_ms || 0), 0) / items.length)
      : 0;

    return { successCount, failedCount, avgDuration };
  }, [items]);

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Execution Trace</p>
          <h1>把 Agent 的每一步跑法摊开看，系统才真正具备“可审计”这件事。</h1>
          <p className="lead">这里同时展示 Run 列表、节点耗时、工具输出和 RAG 证据，适合排查问题，也适合面试时讲清楚技术深度。</p>
        </div>
      </section>

      {error ? <ErrorCard message={error} detail="如果详情拉取失败，请确认 Trace 相关接口与数据库记录是否正常。" /> : null}
      {loading ? <LoadingCard detail="正在读取 Agent Run 列表与链路摘要。" /> : null}
      {!loading && !items.length && !error ? (
        <EmptyCard text="当前没有 Agent 执行记录。" detail="先触发风险扫描或经营日报任务，再回来查看完整链路。" />
      ) : null}

      {items.length ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{items.length}</strong>
              <span className="metric-label">累计 Run</span>
              <p className="metric-detail">说明系统已经把异步任务跑成了可回放的执行记录。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.successCount}</strong>
              <span className="metric-label">成功完成</span>
              <p className="metric-detail">成功率越高，说明链路越稳定。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.failedCount}</strong>
              <span className="metric-label">失败告警</span>
              <p className="metric-detail">失败 Run 越多，越需要结合节点输出定位瓶颈。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{formatDuration(overview.avgDuration)}</strong>
              <span className="metric-label">平均耗时</span>
              <p className="metric-detail">有助于快速判断系统响应是否健康。</p>
            </article>
          </section>

          <section className="trace-layout">
            <div className="run-list">
              {items.map((item) => {
                const statusMeta = getStatusMeta(item.status);

                return (
                  <button
                    className={`run-item ${item.run_id === selectedRunId ? "selected" : ""}`}
                    key={item.run_id}
                    onClick={() => setSelectedRunId(item.run_id)}
                    type="button"
                  >
                    <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                    <strong>{getRunTypeLabel(item.run_type)}</strong>
                    <small>{item.graph_name}</small>
                    <small>发起人 {item.user_id}</small>
                    <small>开始于 {formatDateTime(item.started_at)}</small>
                    <small>耗时 {formatDuration(item.total_duration_ms)}</small>
                  </button>
                );
              })}
            </div>

            <div className="trace-detail">
              {detailLoading ? <LoadingCard text="正在读取链路详情..." detail="包括节点输出、RAG 证据与执行状态。" /> : null}

              {detail ? (
                <>
                  <article className="command-panel">
                    <div className="trace-summary">
                      <div>
                        <p className="eyebrow">{detail.run.graph_name}</p>
                        <h2>{getRunTypeLabel(detail.run.run_type)}</h2>
                        <p className="panel-copy">Run ID：{detail.run.run_id}</p>
                      </div>
                      <span className={`pill ${getStatusMeta(detail.run.status).toneClass}`}>{getStatusMeta(detail.run.status).label}</span>
                    </div>

                    <div className="trace-overview">
                      <div className="trace-stat">
                        <strong>{formatDuration(detail.run.total_duration_ms)}</strong>
                        <span>总耗时</span>
                      </div>
                      <div className="trace-stat">
                        <strong>{detail.steps.length}</strong>
                        <span>节点数量</span>
                      </div>
                      <div className="trace-stat">
                        <strong>{detail.rag_traces.length}</strong>
                        <span>RAG 检索链路</span>
                      </div>
                      <div className="trace-stat">
                        <strong>{formatDateTime(detail.run.finished_at)}</strong>
                        <span>完成时间</span>
                      </div>
                    </div>

                    {detail.run.error_message ? <p className="danger-text">{detail.run.error_message}</p> : null}

                    <details>
                      <summary>查看 Run 输入与输出</summary>
                      <pre>{prettyJson({ input: detail.run.input_json, output: detail.run.output_json })}</pre>
                    </details>
                  </article>

                  <article className="command-panel">
                    <div className="panel-header">
                      <div>
                        <p className="eyebrow">Node Timeline</p>
                        <h2>节点时间线</h2>
                      </div>
                    </div>

                    <div className="timeline">
                      {detail.steps.map((step, index) => {
                        const statusMeta = getStatusMeta(step.status);

                        return (
                          <article className="step-card" key={step.step_id}>
                            <div className="step-index">{index + 1}</div>
                            <div>
                              <div className="step-title">
                                <h3>{step.node_name}</h3>
                                <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                              </div>
                              <p className="panel-copy">
                                工具 {step.tool_name || "无"} · 耗时 {formatDuration(step.duration_ms)} · 开始于 {formatDateTime(step.started_at)}
                              </p>
                              {step.error_message ? <p className="danger-text">{step.error_message}</p> : null}
                              <details className="detail-toggle">
                                <summary>查看输入 / 输出 JSON</summary>
                                <pre>{prettyJson({ input: step.input_json, output: step.output_json })}</pre>
                              </details>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  </article>

                  <article className="command-panel">
                    <div className="section-heading">
                      <div>
                        <p className="eyebrow">RAG Evidence</p>
                        <h2>检索证据链</h2>
                      </div>
                      <span className="meta-chip">{detail.rag_traces.length} 条链路</span>
                    </div>

                    {!detail.rag_traces.length ? <p className="muted-text">当前 Run 没有关联 RAG 检索。</p> : null}

                    {detail.rag_traces.map((trace) => (
                      <article className="rag-trace-card" key={trace.trace_id}>
                        <div className="summary-list">
                          <div className="summary-item">
                            <strong>原始问题</strong>
                            <p>{trace.original_query}</p>
                          </div>
                          {trace.rewritten_query ? (
                            <div className="summary-item">
                              <strong>重写后的问题</strong>
                              <p>{trace.rewritten_query}</p>
                            </div>
                          ) : null}
                        </div>

                        <div className="meta-row">
                          <span className="meta-chip">Trace ID {trace.trace_id}</span>
                          <span className="meta-chip">策略 {trace.strategy}</span>
                          <span className="meta-chip">耗时 {formatDuration(trace.total_ms)}</span>
                          <span className="meta-chip">命中 {trace.hit_count} 条</span>
                        </div>

                        <div className="hit-list">
                          {trace.hits.map((hit) => (
                            <div className="hit-item" key={hit.hit_id}>
                              <span className="meta-chip">#{hit.rank_no}</span>
                              <strong>
                                {hit.doc_id}/{hit.section_id || "-"}
                              </strong>
                              <p>{hit.text_preview || "当前命中没有文本预览。"}</p>
                            </div>
                          ))}
                        </div>
                      </article>
                    ))}
                  </article>
                </>
              ) : null}
            </div>
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
