"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/presentation";
import styles from "./page.module.css";

type NL2SQLSession = {
  session_id: string;
  title: string;
  status: string;
  data_scope: string;
  last_question: string | null;
  last_query_status: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
};

type NL2SQLMessage = {
  message_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  query_id: string | null;
  question: string | null;
  generated_sql: string | null;
  result_json: QueryResult | Record<string, never>;
  cost_ms: number;
  is_cached: boolean;
  created_at: string;
};

type QueryResult = {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
};

type NL2SQLQueryResponse = {
  session_id: string;
  query_id: string;
  sql: string;
  result: QueryResult;
  message: NL2SQLMessage;
  is_cached: boolean;
  error?: string;
  cost_ms: number;
};

type NL2SQLDetail = {
  session: NL2SQLSession;
  messages: NL2SQLMessage[];
};

const quickQuestions = ["本月高风险客户有多少个？", "按负责人统计开放商机金额排行前5名", "待审批的 AI 动作数量是多少？"];

function statusLabel(status: string | null | undefined) {
  const labels: Record<string, string> = {
    created: "已创建",
    executed: "已执行",
    failed: "失败",
    active: "进行中",
  };
  return labels[status || ""] || status || "未运行";
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value);
  return text.length > 120 ? `${text.slice(0, 117)}...` : text;
}

function asQueryResult(value: NL2SQLMessage["result_json"]): QueryResult | null {
  if (!value || !("columns" in value) || !("rows" in value)) {
    return null;
  }
  return value as QueryResult;
}

function ResultTable({ result }: { result: QueryResult | null }) {
  if (!result || !result.columns.length) {
    return <div className={styles.emptyResult}>暂无可展示的查询结果。</div>;
  }
  return (
    <div className={styles.tableWrap}>
      <table className={styles.resultTable}>
        <thead>
          <tr>
            {result.columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {result.columns.map((column) => (
                <td key={column}>{formatCell(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NL2SQLPageContent() {
  const [sessions, setSessions] = useState<NL2SQLSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [messages, setMessages] = useState<NL2SQLMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [latestResult, setLatestResult] = useState<NL2SQLQueryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [querying, setQuerying] = useState(false);
  const [error, setError] = useState("");

  const activeSession = useMemo(
    () => sessions.find((item) => item.session_id === activeSessionId) || null,
    [activeSessionId, sessions]
  );
  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === "assistant") || null,
    [messages]
  );
  const visibleResult = latestResult?.result || asQueryResult(latestAssistantMessage?.result_json || {});
  const visibleSql = latestResult?.sql || latestAssistantMessage?.generated_sql || "";

  async function loadSessions(nextActiveSessionId?: string) {
    const response = await apiFetch<NL2SQLSession[]>("/api/nl2sql/sessions?limit=80");
    setSessions(response.data);
    if (nextActiveSessionId) {
      setActiveSessionId(nextActiveSessionId);
    }
  }

  async function loadSessionDetail(sessionId: string) {
    const response = await apiFetch<NL2SQLDetail>(`/api/nl2sql/sessions/${sessionId}`);
    setActiveSessionId(sessionId);
    setMessages(response.data.messages);
    const latest = [...response.data.messages].reverse().find((item) => item.role === "assistant");
    setLatestResult(null);
    if (latest?.question) {
      setQuestion(latest.question);
    }
  }

  async function loadInitialData() {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<NL2SQLSession[]>("/api/nl2sql/sessions?limit=80");
      setSessions(response.data);
      if (response.data[0]) {
        await loadSessionDetail(response.data[0].session_id);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "NL2SQL 智能问数加载失败。");
    } finally {
      setLoading(false);
    }
  }

  async function createSession() {
    const response = await apiFetch<NL2SQLSession>("/api/nl2sql/sessions", {
      method: "POST",
      body: JSON.stringify({
        title: "数据问答会话",
        data_scope: "self",
        context_json: { source: "nl2sql_page" },
      }),
    });
    await loadSessions(response.data.session_id);
    setMessages([]);
    setLatestResult(null);
    return response.data;
  }

  async function runQuery() {
    const content = question.trim();
    if (!content) {
      return;
    }
    setQuerying(true);
    setError("");
    try {
      const response = await apiFetch<NL2SQLQueryResponse>("/api/nl2sql/query", {
        method: "POST",
        body: JSON.stringify({
          question: content,
          session_id: activeSessionId || undefined,
        }),
      });
      await loadSessions(response.data.session_id);
      await loadSessionDetail(response.data.session_id);
      setLatestResult(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "NL2SQL 查询失败。");
    } finally {
      setQuerying(false);
    }
  }

  useEffect(() => {
    loadInitialData();
  }, []);

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Natural Language To SQL</p>
          <h1>智能问数</h1>
          <p className="lead">用中文直接查询 CRM、风险、审批、任务和经营数据，系统会生成只读 SQL 并保留审计链路。</p>
        </div>
        <div className="page-actions">
          <button className="button-secondary" type="button" onClick={createSession} disabled={querying}>
            新建问数会话
          </button>
        </div>
      </section>

      {error ? <ErrorCard message="智能问数异常" detail={error} /> : null}

      {loading ? (
        <LoadingCard detail="正在装载问数会话与历史查询。" />
      ) : (
        <section className={styles.layout}>
          <aside className={`command-panel ${styles.sidebar}`}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">History</p>
                <h2>问数会话</h2>
              </div>
            </div>
            <div className="summary-list">
              {sessions.length ? (
                sessions.map((session) => (
                  <button
                    className={`${styles.sessionItem} ${session.session_id === activeSessionId ? styles.sessionItemActive : ""}`}
                    key={session.session_id}
                    type="button"
                    onClick={() => loadSessionDetail(session.session_id)}
                  >
                    <strong>{session.title}</strong>
                    <span>{session.last_question || "还没有查询问题"}</span>
                    <small>
                      {statusLabel(session.last_query_status)} · {session.message_count} 条
                    </small>
                  </button>
                ))
              ) : (
                <EmptyCard text="还没有问数会话" detail="输入一个数据问题后，系统会自动创建会话并保存审计记录。" />
              )}
            </div>
          </aside>

          <article className={`command-panel ${styles.workspace}`}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">Query Desk</p>
                <h2>{activeSession?.title || "新的数据问题"}</h2>
              </div>
              <div className="meta-row">
                <span className="meta-chip">{statusLabel(activeSession?.last_query_status)}</span>
                <span className="meta-chip">{activeSession?.message_count || 0} 条消息</span>
              </div>
            </div>

            <div className={styles.questionBox}>
              <textarea
                className="input-like textarea-like"
                placeholder="例如：本月高风险客户有多少个？按负责人统计开放商机金额排行前5名。"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={4}
                disabled={querying}
              />
              <div className={styles.quickQuestions}>
                {quickQuestions.map((item) => (
                  <button key={item} type="button" onClick={() => setQuestion(item)} disabled={querying}>
                    {item}
                  </button>
                ))}
              </div>
              <div className="page-actions">
                <button className="button" type="button" onClick={runQuery} disabled={querying || !question.trim()}>
                  {querying ? "查询中..." : "运行查询"}
                </button>
              </div>
            </div>

            <div className={styles.resultShell}>
              <div className={styles.resultHeader}>
                <div>
                  <p className="eyebrow">Result</p>
                  <h3>查询结果</h3>
                </div>
                <div className="meta-row">
                  <span className="meta-chip">{visibleResult?.row_count || 0} 行</span>
                  <span className="meta-chip">{latestResult?.is_cached ? "缓存命中" : "实时结果"}</span>
                </div>
              </div>
              <ResultTable result={visibleResult} />
            </div>

            <div className={styles.history}>
              {messages.map((item) => (
                <div className={styles.historyItem} key={item.message_id}>
                  <div className="meta-row">
                    <span className={`pill ${item.role === "assistant" ? "tone-success" : "tone-info"}`}>
                      {item.role === "assistant" ? "结果" : "问题"}
                    </span>
                    <span className="meta-chip">{formatDateTime(item.created_at)}</span>
                  </div>
                  <strong>{item.question || item.content}</strong>
                  {item.role === "assistant" ? <p>{item.content}</p> : null}
                </div>
              ))}
            </div>
          </article>

          <aside className={`command-panel ${styles.context}`}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">Audit</p>
                <h2>SQL 与审计</h2>
              </div>
            </div>
            <div className="summary-list">
              <div className="summary-item">
                <strong>执行状态</strong>
                <p>{latestResult?.error || statusLabel(activeSession?.last_query_status)}</p>
              </div>
              <div className="summary-item">
                <strong>查询编号</strong>
                <p>{latestResult?.query_id || latestAssistantMessage?.query_id || "等待查询生成"}</p>
              </div>
              <div className="summary-item">
                <strong>耗时</strong>
                <p>{latestResult ? `${latestResult.cost_ms} ms` : "等待查询生成"}</p>
              </div>
              {latestResult?.error ? <div className={styles.errorBox}>{latestResult.error}</div> : null}
              <pre className={styles.sqlBlock}>{visibleSql || "运行查询后这里会展示最终执行 SQL。"}</pre>
            </div>
          </aside>
        </section>
      )}
    </AppShell>
  );
}

export default function NL2SQLPage() {
  return <NL2SQLPageContent />;
}
