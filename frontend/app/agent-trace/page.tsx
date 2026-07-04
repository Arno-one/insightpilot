"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDateTime, formatDuration, getRunTypeLabel, getStatusMeta } from "@/lib/presentation";
import styles from "./page.module.css";

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

type ActionRunStep = {
  step_run_id: string;
  action_run_id: string;
  approval_id: string | null;
  customer_id: string | null;
  step_code: string;
  tool_name: string;
  step_order: number;
  status: string;
  input_payload_json: unknown;
  output_payload_json: unknown;
  error_message: string | null;
  retry_count: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
};

type ActionRun = {
  action_run_id: string;
  chain_code: string;
  approval_id: string | null;
  customer_id: string | null;
  trigger_source: string;
  triggered_by_user_id: string | null;
  status: string;
  current_step_code: string | null;
  context_payload_json: unknown;
  error_message: string | null;
  created_at: string | null;
  finished_at: string | null;
  task_id: string | null;
  notification_id: string | null;
  can_retry: boolean;
  steps: ActionRunStep[];
};

type RecoveryEvent = {
  action?: string;
  title?: string;
  status?: string;
  source_run_id?: string | null;
  new_run_id?: string | null;
  resume_from_step?: string | null;
  error?: string | null;
};

type RecoveryLink = {
  message_id: string;
  session_id: string;
  run_id: string | null;
  content: string;
  metadata_json: Record<string, unknown>;
  recovery_event: RecoveryEvent;
  created_at: string | null;
};

type TimelineItem = {
  event_type: "run" | "plan" | "step" | "rag" | "action_run" | "action_step" | "recovery" | string;
  title: string;
  status: string | null;
  occurred_at: string | null;
  finished_at: string | null;
  duration_ms: number;
  ref_id: string | null;
  metadata: Record<string, unknown>;
};

type ToolFailureMetric = {
  tool_name: string;
  total_count: number;
  success_count: number;
  failed_count: number;
  skipped_count: number;
  running_count: number;
  avg_duration_ms: number;
  failure_rate: number;
  latest_failed_step: {
    step_id: string;
    run_id: string;
    node_name: string;
    error_message: string | null;
    created_at: string | null;
  } | null;
};

type ToolFailureMetrics = {
  sample_size: number;
  tool_count: number;
  total_failed_count: number;
  tools: ToolFailureMetric[];
};

type RunDetail = {
  run: AgentRun & {
    input_json: unknown;
    output_json: unknown;
    error_message: string | null;
  };
  steps: AgentStep[];
  rag_traces: RagTrace[];
  action_runs: ActionRun[];
  recovery_links: RecoveryLink[];
  timeline: TimelineItem[];
};

type ApprovalSummary = {
  total_count?: number;
  pending_count?: number;
  approved_count?: number;
  rejected_count?: number;
  processed_count?: number;
  converted_task_count?: number;
  all_reviewed?: boolean;
  latest_reviewed_at?: string | null;
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

type RunFilter = "all" | "failed";

const STEP_META: Record<string, StepMeta> = {
  agent_chat_intent_route: {
    stage: "Router",
    label: "识别对话意图",
    description: "先解析用户问题和会话上下文，确定后续要交给哪个工具处理。",
  },
  agent_chat_planner: {
    stage: "Planner",
    label: "生成执行计划",
    description: "使用稳定模板拆解本次任务，生成可审计的步骤计划。",
  },
  agent_chat_tool_router: {
    stage: "Router",
    label: "选择执行工具",
    description: "按意图、会话范围和权限选择本次要调用的工具。",
  },
  agent_chat_tool: {
    stage: "Executor",
    label: "执行对话工具",
    description: "按 Planner 生成的计划调用具体工具，并记录输入输出。",
  },
  agent_chat_coordinator: {
    stage: "Coordinator",
    label: "合并最终结果",
    description: "汇总上游步骤输出，生成本轮可追踪的最终回复。",
  },
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
  load_customer_memory: {
    stage: "Memory",
    label: "加载客户记忆",
    description: "先读取客户长期记忆，给 Planner 和 Reviewer 提供历史上下文。",
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
    description: "只把通过复核的建议写成审批草稿，保持人审后再落地。",
  },
  persist_customer_memory: {
    stage: "Memory",
    label: "回写客户记忆",
    description: "把本次风险判断、审批草稿和执行证据沉淀为客户长期记忆。",
  },
  persist_agent_trace: {
    stage: "Trace",
    label: "落盘执行追踪",
    description: "把本次 Run 的最终结果、状态和关键指标写回 Trace。",
  },
};

const ACTION_STEP_LABELS: Record<string, string> = {
  create_task: "创建任务",
  send_notification: "发送通知",
  create_calendar_event: "创建日程",
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

function formatValue(value: unknown): string {
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
    return value.map((item) => formatValue(item)).join("、");
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

function getActionStepLabel(stepCode: string) {
  return ACTION_STEP_LABELS[stepCode] || stepCode;
}

function getRecoveryActionLabel(action: string | null | undefined) {
  const labels: Record<string, string> = {
    step_retry: "步骤重试",
    partial_resume: "局部恢复",
    retry: "整轮重试",
  };
  return labels[action || ""] || action || "恢复动作";
}

function getTimelineTypeLabel(eventType: string) {
  const labels: Record<string, string> = {
    run: "Run",
    plan: "Plan",
    step: "Step",
    rag: "RAG",
    action_run: "Action",
    action_step: "Action Step",
    recovery: "Recovery",
  };
  return labels[eventType] || eventType || "Event";
}

function getTimelineTitle(item: TimelineItem) {
  if (item.event_type === "step") {
    return getStepMeta(String(item.metadata?.node_name || item.title)).label;
  }
  if (item.event_type === "action_step") {
    return getActionStepLabel(item.title);
  }
  if (item.event_type === "recovery") {
    return getRecoveryActionLabel(String(item.metadata?.action || item.title));
  }
  return item.title;
}

function getTimelineDescription(item: TimelineItem) {
  if (item.event_type === "step") {
    const toolName = item.metadata?.tool_name ? `工具 ${String(item.metadata.tool_name)}` : "无工具";
    return `${toolName} · ${item.ref_id || "无引用"}`;
  }
  if (item.event_type === "plan") {
    return `计划步骤 ${formatValue(item.metadata?.step_count)} · 意图 ${formatValue(item.metadata?.source_intent)}`;
  }
  if (item.event_type === "rag") {
    return `命中 ${formatValue(item.metadata?.hit_count)} 条 · 策略 ${formatValue(item.metadata?.strategy)}`;
  }
  if (item.event_type === "recovery") {
    return `源 Run ${formatValue(item.metadata?.source_run_id)} · 新 Run ${formatValue(item.metadata?.new_run_id)}`;
  }
  return item.ref_id || "无引用 ID";
}

function getApprovalSummaryFromRunOutput(output: unknown): ApprovalSummary | null {
  if (!isRecord(output)) {
    return null;
  }
  const summary = output.approval_summary;
  if (!isRecord(summary)) {
    return null;
  }
  return summary as ApprovalSummary;
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

  if (step.node_name === "load_customer_memory") {
    return [
      { label: "客户数", value: formatValue(output.customer_count) },
      { label: "命中记忆", value: formatValue(output.memory_hit_count) },
      { label: "未命中", value: formatValue(output.memory_miss_count) },
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
      { label: "记忆命中", value: formatValue(output.memory_hit_count) },
      { label: "记忆更新", value: formatValue(output.memory_updated_count) },
      { label: "最终状态", value: formatValue(output.status) },
    ];
  }

  if (step.node_name === "persist_customer_memory") {
    return [{ label: "更新记忆", value: formatValue(output.memory_updated_count) }];
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
  if (step.node_name === "load_customer_memory" && Array.isArray(output.memory_preview)) {
    return output.memory_preview.filter(isRecord);
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
  if (step.node_name === "persist_customer_memory" && Array.isArray(output.memory_preview)) {
    return output.memory_preview.filter(isRecord);
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

  if (step.node_name === "load_customer_memory") {
    return (
      <div className="summary-item" key={`${step.step_id}-memory-load-${index}`}>
        <strong>{customerName}</strong>
        <p>
          {row.memory_hit
            ? "已命中历史客户记忆，可直接参与本次规划。"
            : "当前还没有沉淀好的客户记忆，本次运行会首次建立。"}
        </p>
        <div className="meta-row">
          <span className="meta-chip">{row.memory_hit ? "Memory Hit" : "Memory Miss"}</span>
          {row.last_compiled_at ? <span className="meta-chip">上次编译 {String(row.last_compiled_at)}</span> : null}
        </div>
      </div>
    );
  }

  if (step.node_name === "execute_risk_tools") {
    return (
      <div className="summary-item" key={`${step.step_id}-exec-${index}`}>
        <strong>{customerName}</strong>
        <p>{row.advice_ready ? "工具链执行完成，建议草稿已准备好。" : "工具链执行完成，但建议草稿尚未准备好。"}</p>
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
          {(Array.isArray(row.evidence_used) ? row.evidence_used : []).map((evidence) => (
            <span className="meta-chip" key={`${step.step_id}-${index}-${String(evidence)}`}>
              {String(evidence)}
            </span>
          ))}
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

  if (step.node_name === "persist_customer_memory") {
    return (
      <div className="summary-item" key={`${step.step_id}-memory-write-${index}`}>
        <strong>{customerName}</strong>
        <p>{formatValue(row.summary_text)}</p>
        <div className="meta-row">
          <span className="meta-chip">Memory {formatValue(row.memory_id)}</span>
          <span className="meta-chip">编译于 {formatValue(row.last_compiled_at)}</span>
        </div>
      </div>
    );
  }

  return null;
}

async function fetchAgentRuns() {
  const response = await apiFetch<AgentRun[]>("/api/agent/runs");
  return response.data;
}

async function fetchAgentRunDetail(runId: string) {
  const response = await apiFetch<RunDetail>(`/api/agent/runs/${runId}`);
  return response.data;
}

async function fetchToolFailureMetrics() {
  const response = await apiFetch<ToolFailureMetrics>("/api/agent/tool-metrics/failures?limit=1000");
  return response.data;
}

export default function AgentTracePage() {
  const initialRunId = typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("runId") || "";
  const [items, setItems] = useState<AgentRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState(initialRunId);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [toolMetrics, setToolMetrics] = useState<ToolFailureMetrics | null>(null);
  const [error, setError] = useState("");
  const [runFilter, setRunFilter] = useState<RunFilter>("all");
  const [retryingActionRunId, setRetryingActionRunId] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadRuns() {
      try {
        const data = await fetchAgentRuns();
        if (cancelled) {
          return;
        }
        setItems(data);
        setSelectedRunId((current) => current || initialRunId || data[0]?.run_id || "");
        try {
          const metrics = await fetchToolFailureMetrics();
          if (!cancelled) {
            setToolMetrics(metrics);
          }
        } catch {
          if (!cancelled) {
            setToolMetrics(null);
          }
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Agent 执行记录加载失败。");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredItems = useMemo(() => {
    if (runFilter === "failed") {
      return items.filter((item) => item.status === "failed");
    }
    return items;
  }, [items, runFilter]);

  useEffect(() => {
    if (!filteredItems.length) {
      setSelectedRunId("");
      setDetail(null);
      return;
    }
    if (!filteredItems.some((item) => item.run_id === selectedRunId)) {
      setSelectedRunId(filteredItems[0].run_id);
    }
  }, [filteredItems, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }

    let cancelled = false;

    async function loadDetail() {
      setDetailLoading(true);
      setError("");
      try {
        const data = await fetchAgentRunDetail(selectedRunId);
        if (!cancelled) {
          setDetail(data);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Agent 详情加载失败。");
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    }

    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

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

    return {
      plannerStepCount: detail.steps.filter((step) => step.node_name === "plan_risk_actions").length,
      executorStepCount: detail.steps.filter((step) => step.node_name === "execute_risk_tools").length,
      reviewerStepCount: detail.steps.filter((step) => step.node_name === "review_risk_actions").length,
      actionRunCount: detail.action_runs.length,
      failedActionRunCount: detail.action_runs.filter((item) => item.status === "failed").length,
    };
  }, [detail]);

  const toolMetricsOverview = useMemo(() => {
    const tools = toolMetrics?.tools || [];
    const failedTools = tools.filter((item) => item.failed_count > 0);
    const totalFinished = tools.reduce(
      (sum, item) => sum + item.success_count + item.failed_count + item.skipped_count,
      0
    );
    const totalFailures = tools.reduce((sum, item) => sum + item.failed_count, 0);
    const avgDuration = tools.length
      ? Math.round(tools.reduce((sum, item) => sum + item.avg_duration_ms, 0) / tools.length)
      : 0;
    return {
      failedToolCount: failedTools.length,
      totalFailures,
      overallFailureRate: totalFinished ? totalFailures / totalFinished : 0,
      avgDuration,
      riskiestTool: tools[0] || null,
      topFailedTools: failedTools.slice(0, 5),
    };
  }, [toolMetrics]);

  const approvalSummary = useMemo(() => {
    if (!detail) {
      return null;
    }
    return getApprovalSummaryFromRunOutput(detail.run.output_json);
  }, [detail]);

  async function refreshRuns(preferredRunId?: string) {
    const data = await fetchAgentRuns();
    setItems(data);
    setSelectedRunId((current) => {
      const nextRunId = preferredRunId || current;
      if (nextRunId && data.some((item) => item.run_id === nextRunId)) {
        return nextRunId;
      }
      return data[0]?.run_id || "";
    });
  }

  async function refreshDetail(runId: string) {
    const data = await fetchAgentRunDetail(runId);
    setDetail(data);
  }

  async function handleRetryActionRun(actionRunId: string) {
    if (!selectedRunId) {
      return;
    }

    setRetryingActionRunId(actionRunId);
    setActionMessage("");
    setError("");

    try {
      await apiFetch(`/api/approvals/action-runs/${actionRunId}/retry`, { method: "POST" });
      await refreshRuns(selectedRunId);
      await refreshDetail(selectedRunId);
      setActionMessage("动作链已重新执行，当前 Run 状态已刷新。");
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "动作链重试失败。";
      setActionMessage(message);
      setError(message);
    } finally {
      setRetryingActionRunId("");
    }
  }

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
              <p className="metric-detail">说明系统已经把异步任务沉淀成可回放的执行记录。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.successCount}</strong>
              <span className="metric-label">成功完成</span>
              <p className="metric-detail">成功率越高，说明主链路越稳定。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.failedCount}</strong>
              <span className="metric-label">失败告警</span>
              <p className="metric-detail">失败 Run 越多，越需要结合节点输出来定位瓶颈。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{formatDuration(overview.avgDuration)}</strong>
              <span className="metric-label">平均耗时</span>
              <p className="metric-detail">帮助快速判断系统响应是否健康。</p>
            </article>
          </section>

          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{toolMetrics?.tool_count || 0}</strong>
              <span className="metric-label">纳入统计工具</span>
              <p className="metric-detail">基于最近 {toolMetrics?.sample_size || 0} 条 Agent Step 聚合。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{toolMetricsOverview.failedToolCount}</strong>
              <span className="metric-label">出现失败工具</span>
              <p className="metric-detail">有失败记录的工具越多，越需要优先治理工具稳定性。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{(toolMetricsOverview.overallFailureRate * 100).toFixed(1)}%</strong>
              <span className="metric-label">工具失败率</span>
              <p className="metric-detail">按成功、失败和跳过三类完成态计算。</p>
            </article>
            <article className="metric-card">
              <strong className={`metric-value ${styles.wrapText}`}>
                {toolMetricsOverview.riskiestTool?.tool_name || "暂无"}
              </strong>
              <span className="metric-label">最高风险工具</span>
              <p className="metric-detail">平均耗时 {formatDuration(toolMetricsOverview.avgDuration)}</p>
            </article>
          </section>

          {toolMetricsOverview.topFailedTools.length ? (
            <section className="command-panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Tool Failure Metrics</p>
                  <h2>最近失败工具 TopN</h2>
                </div>
                <span className="meta-chip">失败 {toolMetricsOverview.totalFailures} 次</span>
              </div>
              <div className={styles.toolMetricGrid}>
                {toolMetricsOverview.topFailedTools.map((item) => (
                  <article className={styles.toolMetricCard} key={item.tool_name}>
                    <div className={styles.toolMetricHeader}>
                      <strong className={styles.wrapText}>{item.tool_name}</strong>
                      <span className={`pill ${item.failure_rate > 0.2 ? "tone-danger" : "tone-warning"}`}>
                        {(item.failure_rate * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="meta-row">
                      <span className="meta-chip">成功 {item.success_count}</span>
                      <span className="meta-chip">失败 {item.failed_count}</span>
                      <span className="meta-chip">跳过 {item.skipped_count}</span>
                      <span className="meta-chip">均耗 {formatDuration(item.avg_duration_ms)}</span>
                    </div>
                    {item.latest_failed_step ? (
                      <p className={`panel-copy ${styles.wrapText}`}>
                        最近失败：{item.latest_failed_step.error_message || "未记录错误"} ·{" "}
                        {formatDateTime(item.latest_failed_step.created_at)}
                      </p>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <section className="trace-layout">
            <div className="run-list">
              <div className={styles.traceToolbar}>
                <div>
                  <p className="eyebrow">Run Filters</p>
                  <h2 className={styles.traceToolbarTitle}>历史 Run</h2>
                </div>
                <div className={styles.traceFilterTabs}>
                  <button
                    className={`${styles.traceFilterTab} ${runFilter === "all" ? styles.traceFilterTabActive : ""}`}
                    onClick={() => setRunFilter("all")}
                    type="button"
                  >
                    全部记录
                  </button>
                  <button
                    className={`${styles.traceFilterTab} ${runFilter === "failed" ? styles.traceFilterTabActive : ""}`}
                    onClick={() => setRunFilter("failed")}
                    type="button"
                  >
                    只看失败
                  </button>
                </div>
                <div className="meta-row">
                  <span className="meta-chip">当前展示 {filteredItems.length} 条</span>
                  <span className="meta-chip">失败 {overview.failedCount} 条</span>
                </div>
              </div>

              {!filteredItems.length ? (
                <div className={styles.emptyFilterState}>
                  <EmptyCard text="当前筛选下没有 Run。" detail="切回全部记录，可以查看完整执行历史。" />
                </div>
              ) : (
                filteredItems.map((item) => {
                  const statusMeta = getStatusMeta(item.status);

                  return (
                    <button
                      className={`run-item ${styles.runItem} ${item.run_id === selectedRunId ? "selected" : ""}`}
                      key={item.run_id}
                      onClick={() => setSelectedRunId(item.run_id)}
                      type="button"
                    >
                      <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                      <div className={styles.runItemTitle}>
                        <strong className={styles.runItemName}>{getRunTypeLabel(item.run_type)}</strong>
                        <small className={styles.runItemGraph}>{item.graph_name}</small>
                      </div>
                      <div className={styles.runItemMeta}>
                        <small className={styles.runItemMetaLine}>发起人 {item.user_real_name || item.user_id}</small>
                        <small className={styles.runItemMetaLine}>开始于 {formatDateTime(item.started_at)}</small>
                        <small className={styles.runItemMetaLine}>耗时 {formatDuration(item.total_duration_ms)}</small>
                      </div>
                    </button>
                  );
                })
              )}
            </div>

            <div className="trace-detail">
              {detailLoading ? <LoadingCard text="正在读取链路详情..." detail="包括节点输出、RAG 证据与动作链状态。" /> : null}

              {detail ? (
                <>
                  <article className="command-panel">
                    <div className="trace-summary">
                      <div className={styles.traceSummaryMain}>
                        <p className="eyebrow">{detail.run.graph_name}</p>
                        <h2>{getRunTypeLabel(detail.run.run_type)}</h2>
                        <p className={`panel-copy ${styles.traceRunId}`}>Run ID：{detail.run.run_id}</p>
                      </div>
                      <span className={`pill ${getStatusMeta(detail.run.status).toneClass}`}>
                        {getStatusMeta(detail.run.status).label}
                      </span>
                    </div>

                    <div className={`trace-overview ${styles.traceOverview}`}>
                      <div className={`trace-stat ${styles.traceStat}`}>
                        <strong className={styles.traceStatValue}>{formatDuration(detail.run.total_duration_ms)}</strong>
                        <span>总耗时</span>
                      </div>
                      <div className={`trace-stat ${styles.traceStat}`}>
                        <strong className={styles.traceStatValue}>{detail.steps.length}</strong>
                        <span>节点数量</span>
                      </div>
                      <div className={`trace-stat ${styles.traceStat}`}>
                        <strong className={styles.traceStatValue}>{detail.rag_traces.length}</strong>
                        <span>RAG 检索链路</span>
                      </div>
                      <div className={`trace-stat ${styles.traceStat}`}>
                        <strong className={styles.traceStatValue}>{formatDateTime(detail.run.finished_at)}</strong>
                        <span>完成时间</span>
                      </div>
                    </div>

                    {selectedOverview ? (
                      <div className={`trace-overview ${styles.traceOverview}`}>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{selectedOverview.plannerStepCount}</strong>
                          <span>Planner 阶段</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{selectedOverview.executorStepCount}</strong>
                          <span>Executor 阶段</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{selectedOverview.reviewerStepCount}</strong>
                          <span>Reviewer 阶段</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{selectedOverview.actionRunCount}</strong>
                          <span>动作链总数</span>
                        </div>
                      </div>
                    ) : null}

                    {selectedOverview ? (
                      <div className={`trace-overview ${styles.traceOverview}`}>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{selectedOverview.failedActionRunCount}</strong>
                          <span>失败动作链</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>
                            {detail.run.status === "awaiting_approval" ? "是" : "否"}
                          </strong>
                          <span>等待人工审批</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{detail.action_runs.filter((item) => item.can_retry).length}</strong>
                          <span>可重试动作链</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{formatDateTime(detail.run.started_at)}</strong>
                          <span>开始时间</span>
                        </div>
                      </div>
                    ) : null}

                    {approvalSummary ? (
                      <div className={`trace-overview ${styles.traceOverview}`}>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{approvalSummary.approved_count || 0}</strong>
                          <span>人工已通过</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{approvalSummary.rejected_count || 0}</strong>
                          <span>人工已驳回</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{approvalSummary.converted_task_count || 0}</strong>
                          <span>已转任务</span>
                        </div>
                        <div className={`trace-stat ${styles.traceStat}`}>
                          <strong className={styles.traceStatValue}>{formatDateTime(approvalSummary.latest_reviewed_at)}</strong>
                          <span>最近人工处理</span>
                        </div>
                      </div>
                    ) : null}

                    {detail.run.error_message ? <p className={`danger-text ${styles.errorMessage}`}>{detail.run.error_message}</p> : null}

                    {detail.recovery_links.length ? (
                      <div className={styles.recoveryLinkStack}>
                        {detail.recovery_links.map((link) => {
                          const event = link.recovery_event || {};
                          const statusMeta = getStatusMeta(event.status || "running");
                          const isCurrentNewRun = event.new_run_id === detail.run.run_id;
                          const relatedRunId = isCurrentNewRun ? event.source_run_id : event.new_run_id;

                          return (
                            <article className={styles.recoveryLinkCard} key={link.message_id}>
                              <div className={styles.recoveryLinkHeader}>
                                <div>
                                  <p className="eyebrow">Recovery Link</p>
                                  <h3>{getRecoveryActionLabel(event.action)}</h3>
                                </div>
                                <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                              </div>
                              <div className="meta-row">
                                <span className="meta-chip">{isCurrentNewRun ? "当前 Run 为恢复结果" : "当前 Run 为恢复来源"}</span>
                                <span className="meta-chip">源 Run {event.source_run_id || "无"}</span>
                                <span className="meta-chip">新 Run {event.new_run_id || "无"}</span>
                                <span className="meta-chip">恢复起点 {event.resume_from_step || "未指定"}</span>
                                <span className="meta-chip">记录于 {formatDateTime(link.created_at)}</span>
                              </div>
                              {relatedRunId ? (
                                <button
                                  className="button-secondary"
                                  onClick={() => setSelectedRunId(relatedRunId)}
                                  type="button"
                                >
                                  查看关联 Run
                                </button>
                              ) : null}
                              {event.error ? <p className={`danger-text ${styles.errorMessage}`}>{event.error}</p> : null}
                            </article>
                          );
                        })}
                      </div>
                    ) : null}

                    <details>
                      <summary>查看 Run 输入与输出</summary>
                      <pre>{prettyJson({ input: detail.run.input_json, output: detail.run.output_json })}</pre>
                    </details>
                  </article>

                  <article className="command-panel">
                    <div className="section-heading">
                      <div>
                        <p className="eyebrow">Trace Timeline V2</p>
                        <h2>统一时间线</h2>
                      </div>
                      <span className="meta-chip">{detail.timeline.length} 个事件</span>
                    </div>

                    {!detail.timeline.length ? <p className="muted-text">当前 Run 暂无可展示的时间线事件。</p> : null}

                    {detail.timeline.length ? (
                      <div className={styles.timelineV2}>
                        {detail.timeline.map((item, index) => {
                          const statusMeta = getStatusMeta(item.status || "running");
                          const title = getTimelineTitle(item);

                          return (
                            <article className={styles.timelineItem} key={`${item.event_type}-${item.ref_id || index}`}>
                              <div className={styles.timelineMarker}>
                                <span>{index + 1}</span>
                              </div>
                              <div className={styles.timelineBody}>
                                <div className={styles.timelineHeader}>
                                  <div>
                                    <p className="eyebrow">{getTimelineTypeLabel(item.event_type)}</p>
                                    <h3>{title}</h3>
                                  </div>
                                  <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                                </div>
                                <p className={`panel-copy ${styles.wrapText}`}>{getTimelineDescription(item)}</p>
                                <div className="meta-row">
                                  <span className="meta-chip">发生于 {formatDateTime(item.occurred_at)}</span>
                                  <span className="meta-chip">完成于 {formatDateTime(item.finished_at)}</span>
                                  <span className="meta-chip">耗时 {formatDuration(item.duration_ms)}</span>
                                  <span className="meta-chip">引用 {item.ref_id || "无"}</span>
                                </div>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    ) : null}
                  </article>

                  <article className="command-panel">
                    <div className="section-heading">
                      <div>
                        <p className="eyebrow">Action Recovery</p>
                        <h2>审批后动作链</h2>
                      </div>
                      <span className="meta-chip">{detail.action_runs.length} 条动作链</span>
                    </div>

                    {actionMessage ? (
                      <p
                        className={`${styles.actionMessage} ${
                          error && actionMessage === error ? styles.actionMessageError : styles.actionMessageSuccess
                        }`}
                      >
                        {actionMessage}
                      </p>
                    ) : null}

                    {!detail.action_runs.length ? <p className="muted-text">当前 Run 暂无审批后动作链记录。</p> : null}

                    {detail.action_runs.length ? (
                      <div className={styles.actionRunStack}>
                        {detail.action_runs.map((actionRun) => {
                          const statusMeta = getStatusMeta(actionRun.status);

                          return (
                            <article className={styles.actionRunCard} key={actionRun.action_run_id}>
                              <div className={styles.actionRunHeader}>
                                <div className={styles.actionRunHeaderMain}>
                                  <p className="eyebrow">{actionRun.chain_code}</p>
                                  <h3>{actionRun.chain_code === "post_approval_followup" ? "审批后外部动作闭环" : actionRun.chain_code}</h3>
                                  <p className={styles.actionRunId}>Action Run ID：{actionRun.action_run_id}</p>
                                </div>
                                <div className={styles.actionRunHeaderSide}>
                                  <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                                  {actionRun.can_retry ? (
                                    <button
                                      className="button-secondary"
                                      disabled={retryingActionRunId === actionRun.action_run_id}
                                      onClick={() => void handleRetryActionRun(actionRun.action_run_id)}
                                      type="button"
                                    >
                                      {retryingActionRunId === actionRun.action_run_id ? "重试中..." : "重试当前动作链"}
                                    </button>
                                  ) : null}
                                </div>
                              </div>

                              <div className="meta-row">
                                <span className="meta-chip">审批单 {actionRun.approval_id || "无"}</span>
                                <span className="meta-chip">客户 {actionRun.customer_id || "无"}</span>
                                <span className="meta-chip">当前步骤 {getActionStepLabel(actionRun.current_step_code || "未开始")}</span>
                                <span className="meta-chip">触发来源 {actionRun.trigger_source}</span>
                              </div>

                              <div className="summary-list">
                                <div className="summary-item">
                                  <strong>任务 ID</strong>
                                  <p className={styles.wrapText}>{actionRun.task_id || "尚未生成"}</p>
                                </div>
                                <div className="summary-item">
                                  <strong>通知 ID</strong>
                                  <p className={styles.wrapText}>{actionRun.notification_id || "尚未发送"}</p>
                                </div>
                                <div className="summary-item">
                                  <strong>创建时间</strong>
                                  <p>{formatDateTime(actionRun.created_at)}</p>
                                </div>
                                <div className="summary-item">
                                  <strong>完成时间</strong>
                                  <p>{formatDateTime(actionRun.finished_at)}</p>
                                </div>
                              </div>

                              {actionRun.error_message ? (
                                <p className={`danger-text ${styles.errorMessage}`}>{actionRun.error_message}</p>
                              ) : null}

                              <div className={styles.actionRunStepList}>
                                {actionRun.steps.map((step) => {
                                  const stepStatusMeta = getStatusMeta(step.status);

                                  return (
                                    <article className={styles.actionRunStepItem} key={step.step_run_id}>
                                      <div className={styles.actionRunStepHeader}>
                                        <div>
                                          <h4>{getActionStepLabel(step.step_code)}</h4>
                                          <p className={styles.wrapText}>{step.tool_name}</p>
                                        </div>
                                        <span className={`pill ${stepStatusMeta.toneClass}`}>{stepStatusMeta.label}</span>
                                      </div>

                                      <div className="meta-row">
                                        <span className="meta-chip">步骤序号 {step.step_order}</span>
                                        <span className="meta-chip">重试次数 {step.retry_count}</span>
                                        <span className="meta-chip">开始于 {formatDateTime(step.started_at)}</span>
                                        <span className="meta-chip">完成于 {formatDateTime(step.finished_at)}</span>
                                      </div>

                                      {step.error_message ? (
                                        <p className={`danger-text ${styles.errorMessage}`}>{step.error_message}</p>
                                      ) : null}

                                      <details className="detail-toggle">
                                        <summary>查看步骤输入 / 输出 JSON</summary>
                                        <pre>{prettyJson({ input: step.input_payload_json, output: step.output_payload_json })}</pre>
                                      </details>
                                    </article>
                                  );
                                })}
                              </div>

                              <details className="detail-toggle">
                                <summary>查看动作链上下文</summary>
                                <pre>{prettyJson(actionRun.context_payload_json)}</pre>
                              </details>
                            </article>
                          );
                        })}
                      </div>
                    ) : null}
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
                              {step.error_message ? <p className={`danger-text ${styles.errorMessage}`}>{step.error_message}</p> : null}

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
