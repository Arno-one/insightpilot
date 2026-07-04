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
};

type RuntimeResult = {
  handled: boolean;
  handler: string | null;
  reason?: string;
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

function MessageBody({ item }: { item: AgentChatMessage }) {
  const nl2sqlMeta = getNL2SQLMeta(item);
  if (!nl2sqlMeta) {
    return <p>{item.content}</p>;
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
    </div>
  );
}

function AgentChatContent() {
  const searchParams = useSearchParams();
  const initialCustomerId = searchParams.get("customerId") || "";

  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [sessions, setSessions] = useState<AgentChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState(initialCustomerId);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [runtime, setRuntime] = useState<RuntimeResult | null>(null);

  const selectedCustomer = useMemo(
    () => customers.find((item) => item.customer_id === selectedCustomerId) || null,
    [customers, selectedCustomerId]
  );
  const activeSession = useMemo(
    () => sessions.find((item) => item.session_id === activeSessionId) || null,
    [activeSessionId, sessions]
  );

  async function loadSessionDetail(sessionId: string) {
    const response = await apiFetch<AgentChatDetail>(`/api/agent/chat/sessions/${sessionId}`);
    setActiveSessionId(sessionId);
    setMessages(response.data.messages);
    setRuntime(null);
  }

  async function loadInitialData() {
    setLoading(true);
    setError("");
    try {
      const [customerResponse, sessionResponse] = await Promise.all([
        apiFetch<CustomerOption[]>("/api/crm/customers?limit=80"),
        apiFetch<AgentChatSession[]>("/api/agent/chat/sessions?limit=80"),
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

  async function loadSessions(nextActiveSessionId?: string) {
    const response = await apiFetch<AgentChatSession[]>("/api/agent/chat/sessions?limit=80");
    setSessions(response.data);
    if (nextActiveSessionId) {
      setActiveSessionId(nextActiveSessionId);
    }
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
    await loadSessions(response.data.session_id);
    setMessages([]);
    setRuntime(null);
    return response.data;
  }

  async function sendMessage() {
    const content = draft.trim();
    if (!content) {
      return;
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
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "消息发送失败。");
    } finally {
      setSending(false);
    }
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
                messages.map((item) => (
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
                    <MessageBody item={item} />
                  </div>
                ))
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
                <button className="button" type="button" onClick={sendMessage} disabled={sending || !draft.trim()}>
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
                    ? runtime.handled
                      ? `已由 ${runtime.handler} 处理并写入统一消息。`
                      : runtime.reason || "当前能力尚未接入运行时。"
                    : "发送消息后这里会展示路由和运行结果。"}
                </p>
                {runtime?.run_id ? (
                  <Link className={styles.runtimeTraceLink} href={`/agent-trace?runId=${encodeURIComponent(runtime.run_id)}`}>
                    查看本次 Trace
                  </Link>
                ) : null}
              </div>
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
