"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDateTime, formatDuration, getRunTypeLabel, getStatusMeta } from "@/lib/presentation";

type AgentRun = {
  run_id: string;
  user_id: string;
  user_real_name: string | null;
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

type StepSummaryItem = {
  label: string;
  value: string;
};

type StepMeta = {
  stage: string;
  label: string;
  description: string;
};

type StepPreviewRecord = Record<string, unknown>;

const STEP_META: Record<string, StepMeta> = {
  load_crm_data: {
    stage: "Data",
    label: "加载 CRM 数据",
    description: "先把本次风险判断需要的客户和商机基础数据读进来。",
  },
  calculate_rule_risk: {
    stage: "Scoring",
    label: "规则风险打分",
    description: "基于规则引擎先筛出值得继续分析的风险候选客户。",
  },
  plan_risk_actions: {
    stage: "Planner",
    label: "风险处置规划",
    description: "Planner 先决定要调用哪些内部工具，以及调用顺序。",
  },
  execute_risk_tools: {
    stage: "Executor",
    label: "执行内部工具",
    description: "Executor 按计划调用知识检索和建议生成工具。",
  },
  review_risk_actions: {
    stage: "Reviewer",
    label: "复核建议质量",
    description: "Reviewer 判断当前建议是否值得进入人工审批草稿。",
  },
  create_approval_drafts: {
    stage: "Approval",
    label: "创建审批草稿",
    description: "只把通过复核的建议写成审批草稿，仍然保持人审后落地。",
  },
  persist_agent_trace: {
    stage: "Trace",
    label: "落盘执行追踪",
    description: "把本次 Run 的最终结果、状态和关键指标写回 Trace。",
  },
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "无";
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.join("、");
  }
  return prettyJson(value);
}

function getStepMeta(nodeName: string): StepMeta {
  return (
    STEP_META[nodeName] || {
      stage: "Node",
      label: nodeName,
      description: "当前节点还没有单独的人类可读说明。",
    }
  );
}

function summarizeStepOutput(step: AgentStep): StepSummaryItem[] {
  if (!isRecord(step.output_json)) {
    return [];
  }

  const output = step.output_json;

  if (step.node_name === "load_crm_data") {
    return [
      { label: "客户数量", value: formatValue(output.customer_count) },
      { label: "商机数量", value: formatValue(output.deal_count) },
    ];
  }

  if (step.node_name === "calculate_rule_risk") {
    return [{ label: "风险候选客户", value: formatValue(output.candidate_count) }];
  }

  if (step.node_name === "plan_risk_actions") {
    return [
      { label: "规划客户数", value: formatValue(output.plan_count) },
      { label: "总步骤数", value: formatValue(output.total_steps) },
    ];
  }

  if (step.node_name === "execute_risk_tools") {
    return [
      { label: "执行客户数", value: formatValue(output.execution_count) },
      { label: "工具调用数", value: formatValue(output.tool_call_count) },
      { label: "RAG Trace", value: Array.isArray(output.trace_ids) ? String(output.trace_ids.length) : "0" },
    ];
  }

  if (step.node_name === "review_risk_actions") {
    return [
      { label: "复核总数", value: formatValue(output.review_count) },
      { label: "通过", value: formatValue(output.approved_count) },
      { label: "驳回", value: formatValue(output.rejected_count) },
    ];
  }

  if (step.node_name === "create_approval_drafts") {
    return [
      { label: "已创建草稿", value: formatValue(output.created_count) },
      { label: "跳过创建", value: formatValue(output.skipped_count) },
    ];
  }

  if (step.node_name === "persist_agent_trace") {
    return [
      { label: "风险结果", value: formatValue(output.risk_count) },
      { label: "审批草稿", value: formatValue(output.approval_count) },
      { label: "最终状态", value: formatValue(output.status) },
    ];
  }

  return Object.entries(output)
    .slice(0, 4)
    .map(([label, value]) => ({ label, value: formatValue(value) }));
}

function getStepPreviewRows(step: AgentStep): StepPreviewRecord[] {
  if (!isRecord(step.output_json)) {
    return [];
  }
  const output = step.output_json;

  if (step.node_name === "plan_risk_actions" && Array.isArray(output.plan_preview)) {
    return output.plan_preview.filter(isRecord);
  }
  if (step.node_name === "execute_risk_tools" && Array.isArray(output.execution_preview)) {
    return output.execution_preview.filter(isRecord);
  }
  if (step.node_name === "review_risk_actions" && Array.isArray(output.review_preview)) {
    return output.review_preview.filter(isRecord);
  }
  if (step.node_name === "create_approval_drafts" && Array.isArray(output.created_preview)) {
    return output.created_preview.filter(isRecord);
  }

  return [];
}

function renderPreviewRow(step: AgentStep, row: StepPreviewRecord, index: number) {
  const customerName = formatValue(row.customer_name || row.customer_id || `第 ${index + 1} 条`);

  if (step.node_name === "plan_risk_actions") {
    return (
      <div className="summary-item" key={`${step.step_id}-plan-${index}`}>
        <strong>{customerName}</strong>
        <p>{formatValue(row.thinking)}</p>
        <div className="meta-row">
          {(Array.isArray(row.tools) ? row.tools : []).map((toolName) => (
            <span className="meta-chip" key={`${step.step_id}-${index}-${String(toolName)}`}>
              {String(toolName)}
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (step.node_name === "execute_risk_tools") {
    return (
      <div className="summary-item" key={`${step.step_id}-exec-${index}`}>
        <strong>{customerName}</strong>
        <p>工具链已经执行，{row.advice_ready ? "建议草稿已准备好。" : "建议草稿尚未准备好。"} </p>
        <div className="meta-row">
          {(Array.isArray(row.tools) ? row.tools : []).map((toolName) => (
            <span className="meta-chip" key={`${step.step_id}-${index}-${String(toolName)}`}>
              {String(toolName)}
            </span>
          ))}
          {row.rag_trace_id ? <span className="meta-chip">Trace {String(row.rag_trace_id)}</span> : null}
        </div>
      </div>
    );
  }

  if (step.node_name === "review_risk_actions") {
    return (
      <div className="summary-item" key={`${step.step_id}-review-${index}`}>
        <strong>{customerName}</strong>
        <p>{formatValue(row.review_note)}</p>
        <div className="meta-row">
          <span className="meta-chip">{row.approved ? "允许进入审批" : "阻断审批创建"}</span>
        </div>
      </div>
    );
  }

  if (step.node_name === "create_approval_drafts") {
    return (
      <div className="summary-item" key={`${step.step_id}-draft-${index}`}>
        <strong>{customerName}</strong>
        <p>
          审批草稿 {formatValue(row.approval_id)}，风险快照 {formatValue(row.risk_snapshot_id)}。
        </p>
        <div className="meta-row">
          <span className="meta-chip">风险分 {formatValue(row.risk_score)}</span>
          <span className="meta-chip">等级 {formatValue(row.risk_level)}</span>
        </div>
      </div>
    );
  }

  return null;
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

  const selectedOverview = useMemo(() => {
    if (!detail) {
      return null;
    }

    const plannerStepCount = detail.steps.filter((step) => step.node_name === "plan_risk_actions").length;
    const executorStepCount = detail.steps.filter((step) => step.node_name === "execute_risk_tools").length;
    const reviewerStepCount = detail.steps.filter((step) => step.node_name === "review_risk_actions").length;

    return {
      plannerStepCount,
      executorStepCount,
      reviewerStepCount,
    };
  }, [detail]);

  return (
    <AppShell>
      <section className="command-panel">
        <div>
          <p className="eyebrow">Execution Trace</p>
          <h1>Agent 执行追踪</h1>
        </div>
      </section>

      {error ? <ErrorCard message={error} detail="如果详情拉取失败，请确认 Trace 接口与数据库记录是否正常。" /> : null}
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
              <p className="metric-detail">失败 Run 越多，越需要结合节点输出来定位瓶颈。</p>
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
                    <small>发起人 {item.user_real_name || item.user_id}</small>
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

                    {selectedOverview ? (
                      <div className="trace-overview">
                        <div className="trace-stat">
                          <strong>{selectedOverview.plannerStepCount}</strong>
                          <span>Planner 阶段</span>
                        </div>
                        <div className="trace-stat">
                          <strong>{selectedOverview.executorStepCount}</strong>
                          <span>Executor 阶段</span>
                        </div>
                        <div className="trace-stat">
                          <strong>{selectedOverview.reviewerStepCount}</strong>
                          <span>Reviewer 阶段</span>
                        </div>
                        <div className="trace-stat">
                          <strong>{detail.run.status === "awaiting_approval" ? "是" : "否"}</strong>
                          <span>等待人工审批</span>
                        </div>
                      </div>
                    ) : null}

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
                        const stepMeta = getStepMeta(step.node_name);
                        const summaryItems = summarizeStepOutput(step);
                        const previewRows = getStepPreviewRows(step);

                        return (
                          <article className="step-card" key={step.step_id}>
                            <div className="step-index">{index + 1}</div>
                            <div>
                              <div className="step-title">
                                <h3>{stepMeta.label}</h3>
                                <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                              </div>
                              <p className="panel-copy">{stepMeta.description}</p>
                              <div className="meta-row">
                                <span className="meta-chip">阶段 {stepMeta.stage}</span>
                                <span className="meta-chip">工具 {step.tool_name || "无"}</span>
                                <span className="meta-chip">耗时 {formatDuration(step.duration_ms)}</span>
                                <span className="meta-chip">开始于 {formatDateTime(step.started_at)}</span>
                              </div>
                              {step.error_message ? <p className="danger-text">{step.error_message}</p> : null}

                              {summaryItems.length ? (
                                <div className="summary-list">
                                  {summaryItems.map((item) => (
                                    <div className="summary-item" key={`${step.step_id}-${item.label}`}>
                                      <strong>{item.label}</strong>
                                      <p>{item.value}</p>
                                    </div>
                                  ))}
                                </div>
                              ) : null}

                              {previewRows.length ? (
                                <div className="summary-list">
                                  {previewRows.map((row, rowIndex) => renderPreviewRow(step, row, rowIndex))}
                                </div>
                              ) : null}

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
