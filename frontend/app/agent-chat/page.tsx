"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/presentation";
import styles from "./page.module.css";

type CustomerOption = {
  customer_id: string;
  customer_name: string;
  owner_user_id: string;
  owner_user_name: string | null;
  lifecycle_stage: string | null;
  intent_level: string | null;
};

type AgentChatSession = {
  session_id: string;
  agent_scope: string;
  intent: string;
  title: string;
  status: string;
  related_customer_id: string | null;
  memory_key: string | null;
  last_message_role: string | null;
  last_message_preview: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  recovery_event_summary?: ServerRecoveryEventSummary | null;
};

type AgentChatMessage = {
  message_id: string;
  session_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  intent: string | null;
  tool_name: string | null;
  run_id: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

type AgentChatDetail = {
  session: AgentChatSession;
  messages: AgentChatMessage[];
  recovery_event_summary?: ServerRecoveryEventSummary | null;
};

type RuntimeResult = {
  handled: boolean;
  handler: string | null;
  status?: string;
  reason?: string;
  error?: string;
  reply?: string;
  run_id?: string;
  step_id?: string;
};

type SendMessageResult = {
  session: AgentChatSession;
  message: AgentChatMessage;
  assistant_message: AgentChatMessage | null;
  intent_route: {
    intent: string;
    confidence: number;
    reason: string;
    matched_keywords: string[];
  };
  runtime: RuntimeResult;
};

type NL2SQLMessageMeta = {
  sql: string;
  queryId: string;
  sessionId: string;
  rowCount: number;
  isCached: boolean;
  error: string;
};

type RecoveryPlanItem = {
  action?: string;
  title?: string;
  description?: string;
};

type RecoveryPlanListProps = {
  items: RecoveryPlanItem[];
  runId: string;
  retryContent: string;
  sending: boolean;
  onRetry: (content: string, sourceRunId: string, item: RecoveryPlanItem) => void;
  onInspectTrace: (item: RecoveryPlanItem, runId: string) => void;
};

type RecoveryActionStatus = {
  action: string;
  title: string;
  status: "opened" | "running" | "succeeded" | "failed";
  sourceRunId: string;
  newRunId?: string;
  error?: string;
};

type SendMessageOutcome = {
  data: SendMessageResult | null;
  error: string | null;
};

type RecoveryActionEventPayload = {
  action: string;
  title?: string;
  status: RecoveryActionStatus["status"];
  source_run_id?: string;
  new_run_id?: string;
  error?: string;
  metadata_json?: Record<string, unknown>;
};

type RecoveryEvent = {
  action?: string;
  title?: string;
  status?: RecoveryActionStatus["status"];
  source_run_id?: string;
  new_run_id?: string;
  error?: string;
};

type RecoveryEventDetail = {
  event: RecoveryEvent;
  source: string;
  content?: string;
};

type RecoveryEventRecord = {
  message_id: string;
  session_id: string;
  content: string;
  run_id: string | null;
  recovery_event: RecoveryEvent | null;
  created_at: string;
};

type RecoveryEventSummary = {
  total: number;
  failedCount: number;
  succeededCount: number;
  runningCount: number;
  lastEvent: RecoveryEvent;
};

type RecoverySessionFilter = "all" | "any" | "opened" | "running" | "succeeded" | "failed";

type ServerRecoveryEventSummary = {
  total: number;
  failed_count: number;
  succeeded_count: number;
  running_count: number;
  last_event: RecoveryEvent;
};

function intentLabel(intent: string | null | undefined) {
  const labels: Record<string, string> = {
    risk_analysis: "风险分析",
    customer_query: "客户问题",
    report_query: "报告问题",
    data_query: "数据查询",
    unknown: "待识别",
  };
  return labels[intent || "unknown"] || intent || "待识别";
}

function roleLabel(role: string) {
  if (role === "user") {
    return "你";
  }
  if (role === "assistant") {
    return "Agent";
  }
  if (role === "tool") {
    return "Tool";
  }
  return "System";
}

function sessionTitle(session: AgentChatSession, customers: CustomerOption[]) {
  if (session.title && session.title !== "新对话") {
    return session.title;
  }
  const customer = customers.find((item) => item.customer_id === session.related_customer_id);
  return customer?.customer_name || "统一 Agent 对话";
}

function getStringMeta(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "string" ? value : "";
}

function getNumberMeta(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "number" ? value : 0;
}

function getBooleanMeta(metadata: Record<string, unknown>, key: string) {
  return metadata[key] === true;
}

function getNL2SQLMeta(item: AgentChatMessage): NL2SQLMessageMeta | null {
  const metadata = item.metadata_json || {};
  if (!["nl2sql_tool", "data.query_sql"].includes(String(metadata.runtime_handler || ""))) {
    return null;
  }
  return {
    sql: getStringMeta(metadata, "sql"),
    queryId: getStringMeta(metadata, "query_id"),
    sessionId: getStringMeta(metadata, "nl2sql_session_id"),
    rowCount: getNumberMeta(metadata, "row_count"),
    isCached: getBooleanMeta(metadata, "is_cached"),
    error: getStringMeta(metadata, "error"),
  };
}

function shortRunId(runId: string) {
  return runId.length > 14 ? `${runId.slice(0, 10)}...${runId.slice(-4)}` : runId;
}

function getMessageRunId(item: AgentChatMessage) {
  return item.run_id || getStringMeta(item.metadata_json || {}, "runtime_run_id");
}

function getRecoveryPlan(item: AgentChatMessage): RecoveryPlanItem[] {
  const value = item.metadata_json?.recovery_plan;
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((entry): entry is RecoveryPlanItem => typeof entry === "object" && entry !== null);
}

function getRecoveryEvent(item: AgentChatMessage): RecoveryEvent | null {
  const value = item.metadata_json?.recovery_event;
  if (typeof value !== "object" || value === null) {
    return null;
  }
  return value as RecoveryEvent;
}

function getPreviousUserContent(messages: AgentChatMessage[], currentIndex: number) {
  for (let index = currentIndex - 1; index >= 0; index -= 1) {
    const item = messages[index];
    if (item.role === "user" && item.content.trim()) {
      return item.content;
    }
  }
  return "";
}

function recoveryEventStatusLabel(status: RecoveryEvent["status"]) {
  if (status === "opened") {
    return "已查看";
  }
  if (status === "running") {
    return "执行中";
  }
  if (status === "succeeded") {
    return "已成功";
  }
  if (status === "failed") {
    return "失败";
  }
  return "已记录";
}

function recoveryEventSessionLabel(summary: ServerRecoveryEventSummary | null | undefined) {
  if (!summary) {
    return "";
  }
  const status = recoveryEventStatusLabel(summary.last_event?.status);
  return `恢复${status} · ${summary.total} 条`;
}

function recoverySessionFilterLabel(filter: RecoverySessionFilter) {
  const labels: Record<RecoverySessionFilter, string> = {
    all: "全部会话",
    any: "有恢复事件",
    opened: "已查看 Trace",
    running: "恢复执行中",
    succeeded: "恢复成功",
    failed: "恢复失败",
  };
  return labels[filter];
}

function buildSessionsPath(filter: RecoverySessionFilter) {
  const params = new URLSearchParams({ limit: "80" });
  if (filter !== "all") {
    params.set("recovery_status", filter);
  }
  return `/api/agent/chat/sessions?${params.toString()}`;
}

function buildRecoveryEventSummary(messages: AgentChatMessage[]): RecoveryEventSummary | null {
  const events = messages.map(getRecoveryEvent).filter((event): event is RecoveryEvent => Boolean(event));
  if (!events.length) {
    return null;
  }
  return {
    total: events.length,
    failedCount: events.filter((event) => event.status === "failed").length,
    succeededCount: events.filter((event) => event.status === "succeeded").length,
    runningCount: events.filter((event) => event.status === "running").length,
    lastEvent: events[events.length - 1],
  };
}

function normalizeRecoveryEventSummary(summary: ServerRecoveryEventSummary | null | undefined): RecoveryEventSummary | null {
  if (!summary) {
    return null;
  }
  return {
    total: summary.total,
    failedCount: summary.failed_count,
    succeededCount: summary.succeeded_count,
    runningCount: summary.running_count,
    lastEvent: summary.last_event,
  };
}

function MessageTraceLink({ item }: { item: AgentChatMessage }) {
  const runId = getMessageRunId(item);
  if (!runId) {
    return null;
  }
  return (
    <Link className={styles.traceLink} href={`/agent-trace?runId=${encodeURIComponent(runId)}`}>
      Trace {shortRunId(runId)}
    </Link>
  );
}

function RecoveryEventMessage({
  item,
  event,
  onOpenDetail,
}: {
  item: AgentChatMessage;
  event: RecoveryEvent;
  onOpenDetail: (detail: RecoveryEventDetail) => void;
}) {
  const title = event.title || event.action || "恢复动作";
  return (
    <div className={styles.recoveryEventMessage}>
      <div>
        <strong>{title}</strong>
        <span>{recoveryEventStatusLabel(event.status)}</span>
      </div>
      <p>{event.error ? `错误：${event.error}` : item.content}</p>
      <div className={styles.recoveryEventLinks}>
        {event.source_run_id ? (
          <Link href={`/agent-trace?runId=${encodeURIComponent(event.source_run_id)}`}>原 Trace {shortRunId(event.source_run_id)}</Link>
        ) : null}
        {event.new_run_id ? (
          <Link href={`/agent-trace?runId=${encodeURIComponent(event.new_run_id)}`}>新 Trace {shortRunId(event.new_run_id)}</Link>
        ) : null}
        <button
          className={styles.inlineDetailButton}
          type="button"
          onClick={() => onOpenDetail({ event, source: "消息流恢复事件", content: item.content })}
        >
          详情
        </button>
      </div>
    </div>
  );
}

function RecoveryEventDrawer({
  detail,
  records,
  loading,
  onClose,
}: {
  detail: RecoveryEventDetail | null;
  records: RecoveryEventRecord[];
  loading: boolean;
  onClose: () => void;
}) {
  if (!detail) {
    return null;
  }
  const { event } = detail;
  return (
    <div className={styles.drawerBackdrop} role="presentation" onClick={onClose}>
      <aside className={styles.recoveryDrawer} role="dialog" aria-modal="true" aria-label="恢复事件详情" onClick={(event) => event.stopPropagation()}>
        <div className={styles.drawerHeader}>
          <div>
            <p className="eyebrow">{detail.source}</p>
            <h2>{event.title || event.action || "恢复动作"}</h2>
          </div>
          <button className="ghost-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className={styles.drawerGrid}>
          <div>
            <span>状态</span>
            <strong>{recoveryEventStatusLabel(event.status)}</strong>
          </div>
          <div>
            <span>动作</span>
            <strong>{event.action || "未记录"}</strong>
          </div>
          <div>
            <span>源 Run</span>
            <strong>{event.source_run_id || "未记录"}</strong>
          </div>
          <div>
            <span>新 Run</span>
            <strong>{event.new_run_id || "未生成"}</strong>
          </div>
        </div>
        {event.error ? (
          <div className={styles.drawerError}>
            <strong>错误信息</strong>
            <p>{event.error}</p>
          </div>
        ) : null}
        {detail.content ? (
          <div className={styles.drawerNote}>
            <strong>事件内容</strong>
            <p>{detail.content}</p>
          </div>
        ) : null}
        <div className={styles.drawerActions}>
          {event.source_run_id ? (
            <Link className={styles.recoveryAction} href={`/agent-trace?runId=${encodeURIComponent(event.source_run_id)}`}>
              查看原 Trace
            </Link>
          ) : null}
          {event.new_run_id ? (
            <Link className={styles.recoveryAction} href={`/agent-trace?runId=${encodeURIComponent(event.new_run_id)}`}>
              查看新 Trace
            </Link>
          ) : null}
        </div>
        <div className={styles.drawerHistory}>
          <div className={styles.drawerHistoryHeader}>
            <strong>同会话恢复历史</strong>
            <span>{loading ? "加载中" : `${records.length} 条`}</span>
          </div>
          {records.length ? (
            records.map((record) => {
              const recordEvent = record.recovery_event || {};
              return (
                <div className={styles.drawerHistoryItem} key={record.message_id}>
                  <strong>{recordEvent.title || recordEvent.action || "恢复动作"}</strong>
                  <span>{recoveryEventStatusLabel(recordEvent.status)}</span>
                  <p>{recordEvent.error || record.content}</p>
                </div>
              );
            })
          ) : (
            <p className={styles.drawerEmpty}>{loading ? "正在加载恢复事件历史。" : "当前会话暂无更多恢复事件。"}</p>
          )}
        </div>
      </aside>
    </div>
  );
}

function MessageBody({
  item,
  retryContent,
  sending,
  onRetry,
  onInspectTrace,
}: {
  item: AgentChatMessage;
  retryContent: string;
  sending: boolean;
  onRetry: (content: string, sourceRunId: string, item: RecoveryPlanItem) => void;
  onInspectTrace: (item: RecoveryPlanItem, runId: string) => void;
}) {
  const nl2sqlMeta = getNL2SQLMeta(item);
  const recoveryPlan = getRecoveryPlan(item);
  const runId = getMessageRunId(item);
  if (!nl2sqlMeta) {
    return (
      <>
        <p>{item.content}</p>
        {recoveryPlan.length ? (
          <RecoveryPlanList
            items={recoveryPlan}
            runId={runId}
            retryContent={retryContent}
            sending={sending}
            onRetry={onRetry}
            onInspectTrace={onInspectTrace}
          />
        ) : null}
      </>
    );
  }

  const [summary, ...previewLines] = item.content.split("\n");
  return (
    <div className={styles.nl2sqlArtifact}>
      <div className={styles.artifactHeader}>
        <div>
          <strong>NL2SQL 查询结果</strong>
          <span>{summary || "数据查询已完成"}</span>
        </div>
        <div className={styles.artifactStats}>
          <span>{nl2sqlMeta.rowCount} 行</span>
          <span>{nl2sqlMeta.isCached ? "缓存命中" : "实时查询"}</span>
        </div>
      </div>

      {nl2sqlMeta.error ? <p className={styles.artifactError}>{nl2sqlMeta.error}</p> : null}

      {nl2sqlMeta.sql ? (
        <details className={styles.sqlDetails}>
          <summary>查看 SQL</summary>
          <pre>{nl2sqlMeta.sql}</pre>
        </details>
      ) : null}

      {previewLines.length ? <pre className={styles.resultPreview}>{previewLines.join("\n")}</pre> : null}

      <div className={styles.artifactFooter}>
        {nl2sqlMeta.queryId ? <span>Query {nl2sqlMeta.queryId}</span> : null}
        {nl2sqlMeta.sessionId ? <span>Session {nl2sqlMeta.sessionId}</span> : null}
      </div>
      {recoveryPlan.length ? (
        <RecoveryPlanList
          items={recoveryPlan}
          runId={runId}
          retryContent={retryContent}
          sending={sending}
          onRetry={onRetry}
          onInspectTrace={onInspectTrace}
        />
      ) : null}
    </div>
  );
}

function RecoveryPlanList({ items, runId, retryContent, sending, onRetry, onInspectTrace }: RecoveryPlanListProps) {
  return (
    <div className={styles.recoveryPlan}>
      {items.map((item, index) => (
        <div className={styles.recoveryItem} key={`${item.action || "recovery"}-${index}`}>
          <strong>{item.title || item.action || "恢复建议"}</strong>
          <span>{item.description || "请查看 Trace 详情后继续处理。"}</span>
          <RecoveryPlanAction
            item={item}
            runId={runId}
            retryContent={retryContent}
            sending={sending}
            onRetry={onRetry}
            onInspectTrace={onInspectTrace}
          />
        </div>
      ))}
    </div>
  );
}

function RecoveryPlanAction({
  item,
  runId,
  retryContent,
  sending,
  onRetry,
  onInspectTrace,
}: {
  item: RecoveryPlanItem;
  runId: string;
  retryContent: string;
  sending: boolean;
  onRetry: (content: string, sourceRunId: string, item: RecoveryPlanItem) => void;
  onInspectTrace: (item: RecoveryPlanItem, runId: string) => void;
}) {
  if (item.action === "inspect_trace" && runId) {
    return (
      <Link className={styles.recoveryAction} href={`/agent-trace?runId=${encodeURIComponent(runId)}`} onClick={() => onInspectTrace(item, runId)}>
        查看 Trace
      </Link>
    );
  }

  if (item.action === "retry") {
    return (
      <button className={styles.recoveryAction} type="button" disabled={sending || !retryContent} onClick={() => onRetry(retryContent, runId, item)}>
        {sending ? "重试中..." : "重新发送"}
      </button>
    );
  }

  return null;
}

function AgentChatContent() {
  const searchParams = useSearchParams();
  const initialCustomerId = searchParams.get("customerId") || "";

  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [sessions, setSessions] = useState<AgentChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState(initialCustomerId);
  const [recoveryFilter, setRecoveryFilter] = useState<RecoverySessionFilter>("all");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [runtime, setRuntime] = useState<RuntimeResult | null>(null);
  const [recoveryAction, setRecoveryAction] = useState<RecoveryActionStatus | null>(null);
  const [recoveryEventDetail, setRecoveryEventDetail] = useState<RecoveryEventDetail | null>(null);
  const [recoveryEventRecords, setRecoveryEventRecords] = useState<RecoveryEventRecord[]>([]);
  const [recoveryEventsLoading, setRecoveryEventsLoading] = useState(false);
  const [serverRecoveryEventSummary, setServerRecoveryEventSummary] = useState<RecoveryEventSummary | null>(null);

  const selectedCustomer = useMemo(
    () => customers.find((item) => item.customer_id === selectedCustomerId) || null,
    [customers, selectedCustomerId]
  );
  const activeSession = useMemo(
    () => sessions.find((item) => item.session_id === activeSessionId) || null,
    [activeSessionId, sessions]
  );
  const localRecoveryEventSummary = useMemo(() => buildRecoveryEventSummary(messages), [messages]);
  const recoveryEventSummary = serverRecoveryEventSummary || localRecoveryEventSummary;

  async function loadSessionDetail(sessionId: string, options?: { preserveRecoveryAction?: boolean }) {
    const response = await apiFetch<AgentChatDetail>(`/api/agent/chat/sessions/${sessionId}`);
    setActiveSessionId(sessionId);
    setMessages(response.data.messages);
    setServerRecoveryEventSummary(normalizeRecoveryEventSummary(response.data.recovery_event_summary));
    setRuntime(null);
    if (!options?.preserveRecoveryAction) {
      setRecoveryAction(null);
    }
  }

  async function loadInitialData() {
    setLoading(true);
    setError("");
    try {
      const [customerResponse, sessionResponse] = await Promise.all([
        apiFetch<CustomerOption[]>("/api/crm/customers?limit=80"),
        apiFetch<AgentChatSession[]>(buildSessionsPath(recoveryFilter)),
      ]);
      setCustomers(customerResponse.data);
      setSessions(sessionResponse.data);
      if (!selectedCustomerId && customerResponse.data[0]) {
        setSelectedCustomerId(customerResponse.data[0].customer_id);
      }
      const candidate =
        sessionResponse.data.find((item) => initialCustomerId && item.related_customer_id === initialCustomerId) ||
        sessionResponse.data[0];
      if (candidate) {
        await loadSessionDetail(candidate.session_id);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "统一 Agent 对话加载失败。");
    } finally {
      setLoading(false);
    }
  }

  async function loadSessions(nextActiveSessionId?: string, nextRecoveryFilter: RecoverySessionFilter = recoveryFilter) {
    const response = await apiFetch<AgentChatSession[]>(buildSessionsPath(nextRecoveryFilter));
    setSessions(response.data);
    if (nextActiveSessionId) {
      setActiveSessionId(nextActiveSessionId);
    }
  }

  async function changeRecoveryFilter(nextFilter: RecoverySessionFilter) {
    setRecoveryFilter(nextFilter);
    await loadSessions(undefined, nextFilter);
  }

  async function createSession() {
    const customer = customers.find((item) => item.customer_id === selectedCustomerId);
    const response = await apiFetch<AgentChatSession>("/api/agent/chat/sessions", {
      method: "POST",
      body: JSON.stringify({
        agent_scope: customer ? "risk" : "general",
        intent: "unknown",
        title: customer ? `${customer.customer_name} 风险对话` : "统一 Agent 对话",
        related_customer_id: customer?.customer_id || null,
        context_json: {
          source: "agent_chat_page",
          customer_name: customer?.customer_name || null,
        },
      }),
    });
    setRecoveryFilter("all");
    await loadSessions(response.data.session_id, "all");
    setMessages([]);
    setServerRecoveryEventSummary(null);
    setRuntime(null);
    setRecoveryAction(null);
    return response.data;
  }

  async function recordRecoveryEvent(payload: RecoveryActionEventPayload) {
    if (!activeSessionId) {
      return null;
    }
    try {
      const response = await apiFetch<AgentChatMessage>(`/api/agent/chat/sessions/${activeSessionId}/recovery-events`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      return response.data;
    } catch (exc) {
      setMessage(exc instanceof Error ? `恢复动作已执行，但事件记录失败：${exc.message}` : "恢复动作已执行，但事件记录失败。");
      return null;
    }
  }

  async function openRecoveryEventDetail(detail: RecoveryEventDetail) {
    setRecoveryEventDetail(detail);
    if (!activeSessionId) {
      setRecoveryEventRecords([]);
      return;
    }
    setRecoveryEventsLoading(true);
    try {
      const response = await apiFetch<RecoveryEventRecord[]>(`/api/agent/chat/sessions/${activeSessionId}/recovery-events?limit=100`);
      setRecoveryEventRecords(response.data);
    } catch (exc) {
      setMessage(exc instanceof Error ? `恢复事件历史加载失败：${exc.message}` : "恢复事件历史加载失败。");
      setRecoveryEventRecords([]);
    } finally {
      setRecoveryEventsLoading(false);
    }
  }

  async function sendMessage(nextContent?: string): Promise<SendMessageOutcome | null> {
    const content = (nextContent ?? draft).trim();
    if (!content) {
      return null;
    }

    setSending(true);
    setError("");
    setMessage("");
    try {
      const session = activeSession || (await createSession());
      const response = await apiFetch<SendMessageResult>(`/api/agent/chat/sessions/${session.session_id}/messages`, {
        method: "POST",
        body: JSON.stringify({
          role: "user",
          content,
        }),
      });
      setDraft("");
      setRuntime(response.data.runtime);
      await loadSessions(response.data.session.session_id);
      await loadSessionDetail(response.data.session.session_id);
      if (!response.data.runtime.handled) {
        setMessage(response.data.runtime.reason || "当前意图已记录，后续版本会接入更多 Agent 能力。");
      }
      return { data: response.data, error: null };
    } catch (exc) {
      const detail = exc instanceof Error ? exc.message : "消息发送失败。";
      setError(detail);
      return { data: null, error: detail };
    } finally {
      setSending(false);
    }
  }

  async function retryMessage(content: string, sourceRunId: string, item: RecoveryPlanItem) {
    // 恢复建议里的重试动作复用原发送链路，继续走统一 Runtime 和后端审批边界。
    setDraft(content);
    setRecoveryAction({
      action: "retry",
      title: item.title || "重新发送",
      status: "running",
      sourceRunId,
    });
    await recordRecoveryEvent({
      action: item.action || "retry",
      title: item.title || "重新发送",
      status: "running",
      source_run_id: sourceRunId || undefined,
      metadata_json: {
        trigger: "retry_start",
      },
    });
    const outcome = await sendMessage(content);
    const nextStatus: RecoveryActionStatus = {
      action: "retry",
      title: item.title || "重新发送",
      status: outcome?.data ? "succeeded" : "failed",
      sourceRunId,
      newRunId: outcome?.data?.runtime.run_id,
      error: outcome?.error || undefined,
    };
    setRecoveryAction(nextStatus);
    await recordRecoveryEvent({
      action: item.action || "retry",
      title: item.title || "重新发送",
      status: nextStatus.status,
      source_run_id: sourceRunId || undefined,
      new_run_id: nextStatus.newRunId,
      error: nextStatus.error,
      metadata_json: {
        trigger: "retry_finish",
      },
    });
    if (activeSessionId) {
      await loadSessionDetail(activeSessionId, { preserveRecoveryAction: true });
    }
  }

  function recordTraceInspection(item: RecoveryPlanItem, runId: string) {
    setRecoveryAction({
      action: item.action || "inspect_trace",
      title: item.title || "查看 Trace",
      status: "opened",
      sourceRunId: runId,
    });
    void recordRecoveryEvent({
      action: item.action || "inspect_trace",
      title: item.title || "查看 Trace",
      status: "opened",
      source_run_id: runId,
      metadata_json: {
        trigger: "inspect_trace",
      },
    });
  }

  async function closeSession() {
    if (!activeSessionId) {
      return;
    }
    setSending(true);
    setError("");
    try {
      await apiFetch(`/api/agent/chat/sessions/${activeSessionId}/close`, { method: "POST" });
      setMessages([]);
      setServerRecoveryEventSummary(null);
      setActiveSessionId("");
      await loadSessions();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "会话关闭失败。");
    } finally {
      setSending(false);
    }
  }

  useEffect(() => {
    loadInitialData();
  }, []);

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Unified Agent Runtime</p>
          <h1>统一 Agent 对话</h1>
          <p className="lead">从一个入口发起客户、风险、报告和数据问题；当前版本已接入 Risk Agent 和 NL2SQL 数据查询。</p>
        </div>
        <div className="page-actions">
          <button className="button-secondary" type="button" onClick={createSession} disabled={sending}>
            新建会话
          </button>
          <button className="ghost-button" type="button" onClick={closeSession} disabled={!activeSessionId || sending}>
            关闭当前会话
          </button>
        </div>
      </section>

      {error ? <ErrorCard message="统一 Agent 对话异常" detail={error} /> : null}
      {message ? <p className="success-text">{message}</p> : null}

      {loading ? (
        <LoadingCard detail="正在装载统一会话、客户上下文和运行时状态。" />
      ) : (
        <section className={styles.layout}>
          <aside className={`command-panel ${styles.sidebar}`}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">Sessions</p>
                <h2>会话队列</h2>
              </div>
            </div>
            <label className={styles.field}>
              <span>关联客户</span>
              <select value={selectedCustomerId} onChange={(event) => setSelectedCustomerId(event.target.value)}>
                <option value="">不关联客户</option>
                {customers.map((customer) => (
                  <option key={customer.customer_id} value={customer.customer_id}>
                    {customer.customer_name}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>恢复状态</span>
              <select value={recoveryFilter} onChange={(event) => changeRecoveryFilter(event.target.value as RecoverySessionFilter)}>
                {(["all", "any", "failed", "running", "succeeded", "opened"] as RecoverySessionFilter[]).map((item) => (
                  <option key={item} value={item}>
                    {recoverySessionFilterLabel(item)}
                  </option>
                ))}
              </select>
            </label>
            <div className="summary-list">
              {sessions.length ? (
                sessions.map((session) => (
                  <button
                    className={`${styles.sessionItem} ${session.session_id === activeSessionId ? styles.sessionItemActive : ""}`}
                    key={session.session_id}
                    type="button"
                    onClick={() => loadSessionDetail(session.session_id)}
                  >
                    <strong>{sessionTitle(session, customers)}</strong>
                    <span>{session.last_message_preview || "还没有消息"}</span>
                    <small>
                      {intentLabel(session.intent)} · {session.message_count} 条
                    </small>
                    {session.recovery_event_summary ? (
                      <em
                        className={`${styles.sessionRecovery} ${
                          session.recovery_event_summary.last_event?.status === "failed" ? styles.sessionRecoveryFailed : ""
                        }`}
                      >
                        {recoveryEventSessionLabel(session.recovery_event_summary)}
                      </em>
                    ) : null}
                  </button>
                ))
              ) : (
                <EmptyCard text="还没有统一会话" detail="选择客户后新建会话，就可以从统一入口和 Risk Agent 连续协作。" />
              )}
            </div>
          </aside>

          <article className={`command-panel ${styles.thread}`}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">Conversation</p>
                <h2>{activeSession ? sessionTitle(activeSession, customers) : selectedCustomer?.customer_name || "新的统一对话"}</h2>
              </div>
              <div className="meta-row">
                <span className="meta-chip">{intentLabel(activeSession?.intent)}</span>
                <span className="meta-chip">{activeSession?.status || "draft"}</span>
              </div>
            </div>

            <div className={styles.messageList}>
              {messages.length ? (
                messages.map((item, index) => {
                  const recoveryEvent = getRecoveryEvent(item);
                  if (recoveryEvent) {
                    return (
                      <RecoveryEventMessage
                        event={recoveryEvent}
                        item={item}
                        key={item.message_id}
                        onOpenDetail={openRecoveryEventDetail}
                      />
                    );
                  }
                  return (
                    <div
                      className={`${styles.message} ${
                        item.role === "assistant" ? styles.messageAssistant : item.role === "user" ? styles.messageUser : ""
                      }`}
                      key={item.message_id}
                    >
                      <div className="meta-row">
                        <span className={`pill ${item.role === "assistant" ? "tone-success" : "tone-info"}`}>{roleLabel(item.role)}</span>
                        <span className="meta-chip">{intentLabel(item.intent)}</span>
                        <span className="meta-chip">{formatDateTime(item.created_at)}</span>
                        <MessageTraceLink item={item} />
                      </div>
                      <MessageBody
                        item={item}
                        retryContent={getPreviousUserContent(messages, index)}
                        sending={sending}
                        onRetry={retryMessage}
                        onInspectTrace={recordTraceInspection}
                      />
                    </div>
                  );
                })
              ) : (
                <div className={`${styles.message} ${styles.messageEmpty}`}>
                  <strong>还没有消息</strong>
                  <p>可以问“这个客户为什么风险高”，也可以直接问“本月高风险客户有多少”。</p>
                </div>
              )}
            </div>

            <div className={styles.composer}>
              <textarea
                className="input-like textarea-like"
                placeholder="例如：这个客户为什么风险这么高？本月高风险客户有多少？"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                rows={4}
                disabled={sending}
              />
              <div className="page-actions">
                <button className="button" type="button" onClick={() => sendMessage()} disabled={sending || !draft.trim()}>
                  {sending ? "运行中..." : "发送"}
                </button>
              </div>
            </div>
          </article>

          <aside className={`command-panel ${styles.context}`}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">Runtime</p>
                <h2>运行上下文</h2>
              </div>
            </div>
            <div className="summary-list">
              <div className="summary-item">
                <strong>当前客户</strong>
                {selectedCustomer ? (
                  <p>
                    {selectedCustomer.customer_name}，负责人 {selectedCustomer.owner_user_name || selectedCustomer.owner_user_id}，意向{" "}
                    {selectedCustomer.intent_level || "未记录"}。
                  </p>
                ) : (
                  <p>当前会话未关联客户；风险分析需要先选择客户。</p>
                )}
              </div>
              <div className="summary-item">
                <strong>本次运行</strong>
                <p>
                  {runtime
                    ? runtime.status === "failed"
                      ? `运行失败：${runtime.error || runtime.reason || "工具异常"}`
                      : runtime.handled
                      ? `已由 ${runtime.handler} 处理并写入统一消息。`
                      : runtime.reason || "当前能力尚未接入运行时。"
                    : "发送消息后这里会展示路由和运行结果。"}
                </p>
                {runtime?.run_id ? (
                  <Link className={styles.runtimeTraceLink} href={`/agent-trace?runId=${encodeURIComponent(runtime.run_id)}`}>
                    查看本次 Trace
                  </Link>
                ) : null}
                {recoveryAction ? (
                  <div className={styles.recoveryStatus}>
                    <strong>{recoveryAction.title}</strong>
                    <span>
                      {recoveryAction.status === "opened"
                        ? "已打开 Trace 查看入口。"
                        : recoveryAction.status === "running"
                        ? "正在重新提交上一条用户消息。"
                        : recoveryAction.status === "succeeded"
                        ? "重试已提交并生成新的运行结果。"
                        : `重试失败：${recoveryAction.error || "未知异常"}`}
                    </span>
                    <div className={styles.recoveryStatusLinks}>
                      {recoveryAction.sourceRunId ? (
                        <Link href={`/agent-trace?runId=${encodeURIComponent(recoveryAction.sourceRunId)}`}>
                          原 Trace {shortRunId(recoveryAction.sourceRunId)}
                        </Link>
                      ) : null}
                      {recoveryAction.newRunId ? (
                        <Link href={`/agent-trace?runId=${encodeURIComponent(recoveryAction.newRunId)}`}>
                          新 Trace {shortRunId(recoveryAction.newRunId)}
                        </Link>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
              {recoveryEventSummary ? (
                <div className="summary-item">
                  <strong>恢复事件</strong>
                  <p>
                    已记录 {recoveryEventSummary.total} 条，成功 {recoveryEventSummary.succeededCount} 条，失败{" "}
                    {recoveryEventSummary.failedCount} 条。
                  </p>
                  <div className={styles.recoverySummary}>
                    <span>最近状态：{recoveryEventStatusLabel(recoveryEventSummary.lastEvent.status)}</span>
                    {recoveryEventSummary.runningCount ? <span>仍有 {recoveryEventSummary.runningCount} 条执行中事件。</span> : null}
                    {recoveryEventSummary.lastEvent.error ? <span>最近错误：{recoveryEventSummary.lastEvent.error}</span> : null}
                    <div className={styles.recoveryStatusLinks}>
                      {recoveryEventSummary.lastEvent.source_run_id ? (
                        <Link href={`/agent-trace?runId=${encodeURIComponent(recoveryEventSummary.lastEvent.source_run_id)}`}>
                          原 Trace {shortRunId(recoveryEventSummary.lastEvent.source_run_id)}
                        </Link>
                      ) : null}
                      {recoveryEventSummary.lastEvent.new_run_id ? (
                        <Link href={`/agent-trace?runId=${encodeURIComponent(recoveryEventSummary.lastEvent.new_run_id)}`}>
                          新 Trace {shortRunId(recoveryEventSummary.lastEvent.new_run_id)}
                        </Link>
                      ) : null}
                      <button
                        className={styles.inlineDetailButton}
                        type="button"
                        onClick={() => openRecoveryEventDetail({ event: recoveryEventSummary.lastEvent, source: "运行上下文恢复摘要" })}
                      >
                        详情
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}
              <div className="summary-item">
                <strong>能力边界</strong>
                <p>当前版本已接 Risk Agent 和 NL2SQL 数据查询。报告解释和执行 Agent 会在后续版本挂入同一入口。</p>
              </div>
              {selectedCustomer ? (
                <Link className="button-secondary" href={`/customers/${selectedCustomer.customer_id}`}>
                  返回客户工作台
                </Link>
              ) : null}
            </div>
          </aside>
        </section>
      )}
      <RecoveryEventDrawer
        detail={recoveryEventDetail}
        records={recoveryEventRecords}
        loading={recoveryEventsLoading}
        onClose={() => setRecoveryEventDetail(null)}
      />
    </AppShell>
  );
}

export default function AgentChatPage() {
  return (
    <Suspense fallback={<LoadingCard detail="正在装载统一 Agent 对话入口。" />}>
      <AgentChatContent />
    </Suspense>
  );
}
