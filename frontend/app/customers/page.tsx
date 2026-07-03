"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useDeferredValue, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDateTime, getRiskMeta } from "@/lib/presentation";
import styles from "./workbench.module.css";

type CustomerListItem = {
  customer_id: string;
  customer_name: string;
  owner_user_id: string;
  owner_user_name: string | null;
  lifecycle_stage: string;
  intent_level: string;
  customer_level: string;
  competitor_involved: number;
  last_follow_up_at: string | null;
  next_follow_up_at: string | null;
};

type RiskChatHistoryItem = {
  customer_id: string;
  customer_name: string;
  session_key: string;
  title: string;
  preview: string;
  updated_at: string;
  latest_risk_level: string | null;
};

type RiskChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type RiskChatSession = {
  session_key: string;
  recent_messages: RiskChatMessage[];
  history_summary: string;
  memory_window: {
    recent_rounds: number;
    max_recent_messages: number;
  };
  updated_at: string | null;
  customer_brief: {
    customer_id: string;
    customer_name: string | null;
    owner_user_id: string;
    owner_user_name: string | null;
    lifecycle_stage: string | null;
    intent_level: string | null;
    last_follow_up_at: string | null;
    next_follow_up_at: string | null;
    last_sentiment: string | null;
  };
  latest_risk: {
    risk_snapshot_id?: string;
    risk_score?: number;
    risk_level?: string;
    llm_reason?: string | null;
    llm_suggestion?: string | null;
  };
  customer_memory_summary: string;
  customer_memory_updated_at: string | null;
};

type RiskChatMessageResult = {
  reply: string;
  session_key: string;
  recent_messages: RiskChatMessage[];
  history_summary: string;
  memory_window: {
    recent_rounds: number;
    max_recent_messages: number;
  };
  updated_at: string | null;
  compacted: boolean;
  customer_memory_summary: string;
  latest_risk: RiskChatSession["latest_risk"];
  session_history: RiskChatHistoryItem[];
};

function suggestPrompts(customerName: string) {
  return [
    `这个客户现在最值得先确认的风险点是什么？`,
    `如果今天只做一件事，应该怎么回访 ${customerName}？`,
    `这个客户现在是否值得升级给主管介入？`
  ];
}

function CustomerWorkbenchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedFromQuery = searchParams.get("customerId") || "";
  const [customers, setCustomers] = useState<CustomerListItem[]>([]);
  const [sessionHistory, setSessionHistory] = useState<RiskChatHistoryItem[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState(selectedFromQuery);
  const [customerLoading, setCustomerLoading] = useState(true);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [keyword, setKeyword] = useState("");
  const [currentSession, setCurrentSession] = useState<RiskChatSession | null>(null);
  const deferredKeyword = useDeferredValue(keyword);

  const selectedCustomer = useMemo(
    () => customers.find((item) => item.customer_id === selectedCustomerId) || null,
    [customers, selectedCustomerId]
  );

  async function loadCustomers() {
    setCustomerLoading(true);
    setError("");
    try {
      const query = new URLSearchParams();
      if (deferredKeyword.trim()) {
        query.set("keyword", deferredKeyword.trim());
      }
      query.set("limit", "100");
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const response = await apiFetch<CustomerListItem[]>(`/api/crm/customers${suffix}`);
      setCustomers(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "客户列表加载失败。");
    } finally {
      setCustomerLoading(false);
    }
  }

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const response = await apiFetch<RiskChatHistoryItem[]>("/api/agent/risk-chat/sessions");
      setSessionHistory(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "会话历史加载失败。");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadSession(customerId: string) {
    if (!customerId) {
      setCurrentSession(null);
      return;
    }
    setSessionLoading(true);
    setError("");
    try {
      const response = await apiFetch<RiskChatSession>(`/api/agent/risk-chat/customers/${customerId}/session`);
      setCurrentSession(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "对话会话加载失败。");
      setCurrentSession(null);
    } finally {
      setSessionLoading(false);
    }
  }

  function syncSelectedCustomer(customerId: string) {
    setSelectedCustomerId(customerId);
    const query = new URLSearchParams(searchParams.toString());
    if (customerId) {
      query.set("customerId", customerId);
    } else {
      query.delete("customerId");
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    router.replace(`/customers${suffix}`, { scroll: false });
  }

  async function sendMessage(prefilledMessage?: string) {
    const finalMessage = (prefilledMessage ?? draft).trim();
    if (!selectedCustomerId || !finalMessage) {
      return;
    }
    setSending(true);
    setError("");
    try {
      const response = await apiFetch<RiskChatMessageResult>(`/api/agent/risk-chat/customers/${selectedCustomerId}/message`, {
        method: "POST",
        body: JSON.stringify({ message: finalMessage })
      });
      setCurrentSession((current) =>
        current
          ? {
              ...current,
              session_key: response.data.session_key,
              recent_messages: response.data.recent_messages,
              history_summary: response.data.history_summary,
              memory_window: response.data.memory_window,
              updated_at: response.data.updated_at,
              customer_memory_summary: response.data.customer_memory_summary,
              latest_risk: response.data.latest_risk
            }
          : null
      );
      setSessionHistory(response.data.session_history);
      setDraft("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Risk Agent 回复失败。");
    } finally {
      setSending(false);
    }
  }

  async function clearSession() {
    if (!selectedCustomerId) {
      return;
    }
    setSending(true);
    setError("");
    try {
      const response = await apiFetch<{ session_history: RiskChatHistoryItem[] }>(`/api/agent/risk-chat/customers/${selectedCustomerId}/session`, {
        method: "DELETE"
      });
      setSessionHistory(response.data.session_history);
      await loadSession(selectedCustomerId);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "会话清空失败。");
    } finally {
      setSending(false);
    }
  }

  useEffect(() => {
    loadCustomers();
  }, [deferredKeyword]);

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    if (!selectedFromQuery && selectedCustomerId) {
      return;
    }
    if (selectedFromQuery && selectedFromQuery !== selectedCustomerId) {
      setSelectedCustomerId(selectedFromQuery);
    }
  }, [selectedFromQuery, selectedCustomerId]);

  useEffect(() => {
    if (!customers.length && !sessionHistory.length) {
      return;
    }
    if (selectedCustomerId) {
      return;
    }
    // 中文注释：优先恢复最近聊过的客户，没有历史时再退回到当前可见客户列表的第一位。
    const fallbackCustomerId = sessionHistory[0]?.customer_id || customers[0]?.customer_id || "";
    if (fallbackCustomerId) {
      syncSelectedCustomer(fallbackCustomerId);
    }
  }, [customers, selectedCustomerId, sessionHistory]);

  useEffect(() => {
    if (!selectedCustomerId) {
      setCurrentSession(null);
      return;
    }
    loadSession(selectedCustomerId);
  }, [selectedCustomerId]);

  const promptList = suggestPrompts(selectedCustomer?.customer_name || "该客户");

  return (
    <AppShell>
      <section className="command-panel">
        <div>
          <p className="eyebrow">Customer Workbench</p>
          <h1>客户工作台</h1>
          <p className="panel-copy">左侧直接找回历史对话或切换客户，中间连续和 Risk Agent 协作，不再把对话入口藏在详情页深处。</p>
        </div>
      </section>

      {error ? <ErrorCard message={error} detail="请确认登录权限、客户可见范围以及后端接口是否正常。" /> : null}

      <section className={styles.workbench}>
        <aside className={styles.sidebar}>
          <article className={`command-panel ${styles.sidebarPanel}`}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">Recent Chats</p>
                <h2>会话历史</h2>
              </div>
            </div>
            {historyLoading ? (
              <LoadingCard detail="正在恢复最近会话。" />
            ) : sessionHistory.length ? (
              <div className={styles.sessionList}>
                {sessionHistory.map((item) => (
                  <button
                    className={`${styles.sessionItem} ${item.customer_id === selectedCustomerId ? styles.sessionItemActive : ""}`}
                    key={item.session_key}
                    onClick={() => syncSelectedCustomer(item.customer_id)}
                    type="button"
                  >
                    <div className={styles.sessionItemTop}>
                      <strong>{item.title}</strong>
                      <span>{formatDateTime(item.updated_at)}</span>
                    </div>
                    <p>{item.customer_name}</p>
                    <small>{item.preview || "这条会话还没有可展示的预览。"}</small>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyCard text="当前还没有历史对话" detail="你第一次发消息后，最近会话会自动出现在这里。" />
            )}
          </article>

          <article className={`command-panel ${styles.sidebarPanel}`}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">Customers</p>
                <h2>客户入口</h2>
              </div>
            </div>
            <input
              className={`input-like ${styles.searchInput}`}
              placeholder="搜索客户名 / 客户 ID / 负责人"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            {customerLoading ? (
              <LoadingCard detail="正在读取你当前可见的客户。" />
            ) : customers.length ? (
              <div className={styles.customerList}>
                {customers.map((item) => (
                  <button
                    className={`${styles.customerItem} ${item.customer_id === selectedCustomerId ? styles.customerItemActive : ""}`}
                    key={item.customer_id}
                    onClick={() => syncSelectedCustomer(item.customer_id)}
                    type="button"
                  >
                    <strong>{item.customer_name}</strong>
                    <p>{item.customer_id}</p>
                    <small>
                      负责人 {item.owner_user_name || item.owner_user_id} · {item.lifecycle_stage} · {item.intent_level}
                    </small>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyCard text="当前没有可用客户" detail="请先确认 CRM 数据是否已导入，或当前账号是否拥有对应客户权限。" />
            )}
          </article>
        </aside>

        <main className={styles.chatMain}>
          {!selectedCustomerId ? (
            <EmptyCard text="先从左侧选一个客户" detail="选中客户后，这里会进入 ChatGPT 风格的连续对话工作区。" />
          ) : (
            <>
              <article className={`command-panel ${styles.chatHeaderPanel}`}>
                <div className={styles.chatHeader}>
                  <div>
                    <p className="eyebrow">Risk Agent</p>
                    <h2>{selectedCustomer?.customer_name || currentSession?.customer_brief.customer_name || selectedCustomerId}</h2>
                    <p className="panel-copy">
                      负责人 {selectedCustomer?.owner_user_name || currentSession?.customer_brief.owner_user_name || currentSession?.customer_brief.owner_user_id}
                      ，最近跟进 {formatDateTime(currentSession?.customer_brief.last_follow_up_at || null)}。
                    </p>
                  </div>
                  <div className="page-actions">
                    <Link className="button-secondary" href={`/customers/${selectedCustomerId}`}>
                      查看客户详情
                    </Link>
                    <button className="button-secondary" onClick={clearSession} type="button" disabled={sending || sessionLoading}>
                      清空当前对话
                    </button>
                  </div>
                </div>

                {/* 中文注释：把当前风险摘要顶在主对话区上方，避免用户每次问问题前还要回头翻客户详情。 */}
                <div className={styles.riskSummary}>
                  <div className={styles.riskSummaryMain}>
                    <span className={`pill ${getRiskMeta(currentSession?.latest_risk?.risk_level || "").toneClass}`}>
                      {currentSession?.latest_risk?.risk_level ? getRiskMeta(currentSession.latest_risk.risk_level).label : "暂未识别风险"}
                    </span>
                    <strong>
                      {currentSession?.latest_risk?.risk_level
                        ? `当前风险分 ${currentSession.latest_risk.risk_score ?? "未记录"}`
                        : "当前还没有关联风险快照"}
                    </strong>
                    <p>{currentSession?.latest_risk?.llm_reason || "Risk Agent 会优先结合客户资料、长期记忆和会话记忆来回答你的问题。"}</p>
                  </div>
                  {currentSession?.history_summary ? (
                    <div className={styles.historyBrief}>
                      <strong>历史摘要已接入</strong>
                      <p>{currentSession.history_summary}</p>
                    </div>
                  ) : null}
                </div>
              </article>

              <article className={`command-panel ${styles.chatPanel}`}>
                {sessionLoading ? (
                  <LoadingCard detail="正在恢复这位客户的会话上下文。" />
                ) : (
                  <>
                    <div className={styles.chatThread}>
                      {currentSession?.recent_messages.length ? (
                        currentSession.recent_messages.map((item, index) => (
                          <div
                            className={`${styles.chatBubble} ${item.role === "user" ? styles.chatBubbleUser : styles.chatBubbleAssistant}`}
                            key={`${item.created_at}-${index}`}
                          >
                            <div className={styles.chatBubbleMeta}>
                              <strong>{item.role === "user" ? "你" : "Risk Agent"}</strong>
                              <span>{formatDateTime(item.created_at)}</span>
                            </div>
                            <p>{item.content}</p>
                          </div>
                        ))
                      ) : (
                        <div className={styles.chatEmpty}>
                          <strong>这位客户还没有开始对话</strong>
                          <p>你可以直接问风险原因、回访策略或是否值得升级给主管介入，Risk Agent 会沿着这位客户持续记忆。</p>
                          <div className={styles.promptList}>
                            {promptList.map((prompt) => (
                              <button className="button-secondary" key={prompt} onClick={() => sendMessage(prompt)} type="button" disabled={sending}>
                                {prompt}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    <div className={styles.chatComposer}>
                      <div className={styles.memoryNote}>
                        <span className="meta-chip">短期记忆：最近 {currentSession?.memory_window.recent_rounds || 5} 轮全量</span>
                        <span className="meta-chip">长期记忆：客户经营摘要已接入</span>
                      </div>
                      <textarea
                        className={`input-like textarea-like ${styles.chatTextarea}`}
                        placeholder="直接问：这个客户为什么现在有风险？应该怎么回访？"
                        rows={5}
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        disabled={sending}
                      />
                      <div className="page-actions">
                        <button className="button" onClick={() => sendMessage()} type="button" disabled={sending || !draft.trim()}>
                          {sending ? "发送中..." : "发送给 Risk Agent"}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </article>
            </>
          )}
        </main>
      </section>
    </AppShell>
  );
}

export default function CustomerWorkbenchPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <LoadingCard detail="正在恢复客户工作台与最近会话。" />
        </AppShell>
      }
    >
      <CustomerWorkbenchContent />
    </Suspense>
  );
}
