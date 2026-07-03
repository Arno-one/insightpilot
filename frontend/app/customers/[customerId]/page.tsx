"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import {
  formatDate,
  formatDateTime,
  getPriorityMeta,
  getReportTypeLabel,
  getRiskMeta,
  getStatusMeta
} from "@/lib/presentation";

type Customer = {
  customer_id: string;
  customer_name: string;
  owner_user_id: string;
  owner_user_name: string | null;
  industry: string | null;
  region: string | null;
  source: string | null;
  lifecycle_stage: string;
  intent_level: string;
  customer_level: string;
  company_size: string | null;
  budget_min: number | null;
  budget_max: number | null;
  expected_purchase_at: string | null;
  decision_maker_status: string;
  competitor_involved: number;
  next_follow_up_at: string | null;
  last_follow_up_at: string | null;
  last_sentiment: string;
  lost_reason: string | null;
  remark: string | null;
  created_at: string;
  updated_at: string;
};

type RiskSnapshot = {
  risk_snapshot_id: string;
  customer_id: string;
  deal_id: string | null;
  owner_user_id: string;
  owner_user_name: string | null;
  risk_score: number;
  risk_level: string;
  rule_hits_json: Array<{ rule_name?: string; score?: number }>;
  evidence_json: Record<string, unknown>;
  llm_reason: string | null;
  llm_suggestion: string | null;
  suggested_task_json: {
    title?: string;
    description?: string;
    priority?: string;
    recommended_script?: string;
  };
  status: string;
  created_at: string;
};

type Deal = {
  deal_id: string;
  owner_user_id: string;
  owner_user_name: string | null;
  deal_name: string;
  stage: string;
  amount: number;
  quote_amount: number | null;
  quoted_at: string | null;
  expected_close_at: string | null;
  closed_at: string | null;
  close_result: string;
  updated_at: string;
};

type FollowUp = {
  follow_up_id: string;
  deal_id: string | null;
  owner_user_id: string;
  owner_user_name: string | null;
  follow_up_type: string;
  content: string;
  sentiment: string;
  customer_feedback: string | null;
  next_action: string | null;
  next_follow_up_at: string | null;
  occurred_at: string;
};

type WorkflowEvent = {
  event_id: string;
  entity_type: "approval" | "task";
  entity_id: string;
  approval_id: string | null;
  task_id: string | null;
  customer_id: string;
  risk_snapshot_id: string | null;
  action_type: string;
  operator_user_id: string;
  operator_user_name: string | null;
  note: string | null;
  detail_json: Record<string, unknown>;
  happened_at: string;
};

type Approval = {
  approval_id: string;
  approval_type: string;
  risk_snapshot_id: string | null;
  status: string;
  requested_by_user_id: string;
  requested_by_user_name: string | null;
  reviewer_user_id: string | null;
  reviewer_user_name: string | null;
  review_comment: string | null;
  created_at: string;
  reviewed_at: string | null;
  proposed_payload_json: {
    title?: string;
    description?: string;
    recommended_script?: string;
    priority?: string;
  };
  events: WorkflowEvent[];
};

type Task = {
  task_id: string;
  approval_id: string | null;
  deal_id: string | null;
  assignee_user_id: string;
  assignee_user_name: string | null;
  task_type: string;
  title: string;
  description: string | null;
  recommended_script: string | null;
  priority: string;
  status: string;
  due_at: string | null;
  completed_at: string | null;
  result_note: string | null;
  created_at: string;
  events: WorkflowEvent[];
};

type ReportRef = {
  report_id: string;
  report_type: string;
  report_date: string;
  summary: string;
  suggestions: string | null;
  created_by_user_id: string;
  created_by_user_name: string | null;
  created_at: string;
};

type CustomerDetailData = {
  customer: Customer;
  selected_risk_snapshot_id: string | null;
  risk_snapshots: RiskSnapshot[];
  deals: Deal[];
  follow_ups: FollowUp[];
  approvals: Approval[];
  tasks: Task[];
  report_refs: ReportRef[];
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
};

function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "未记录";
  }
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0
  }).format(value);
}

function labelValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "未记录";
  }
  return String(value);
}

function evidenceEntries(evidence: Record<string, unknown>) {
  return Object.entries(evidence)
    .filter(([, value]) => value !== null && value !== "" && typeof value !== "object")
    .slice(0, 6);
}

function getWorkflowEventLabel(actionType: string) {
  const labels: Record<string, string> = {
    approval_created: "提交审批",
    approval_approved: "审批通过",
    approval_rejected: "审批驳回",
    approval_approved_with_changes: "修改后通过",
    task_created: "创建任务",
    task_in_progress: "开始执行",
    task_completed: "执行完成",
    task_cancelled: "取消任务"
  };
  return labels[actionType] || actionType;
}

export default function CustomerDetailPage() {
  const params = useParams<{ customerId: string }>();
  const searchParams = useSearchParams();
  const customerId = params.customerId;
  const highlightedRiskSnapshotId = searchParams.get("riskSnapshotId");

  const [detail, setDetail] = useState<CustomerDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [rescanLoading, setRescanLoading] = useState(false);
  const [chatSession, setChatSession] = useState<RiskChatSession | null>(null);
  const [chatLoading, setChatLoading] = useState(true);
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState("");
  const [chatDraft, setChatDraft] = useState("");

  async function loadDetail() {
    if (!customerId) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const query = highlightedRiskSnapshotId ? `?risk_snapshot_id=${encodeURIComponent(highlightedRiskSnapshotId)}` : "";
      const response = await apiFetch<CustomerDetailData>(`/api/crm/customers/${customerId}${query}`);
      setDetail(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "客户详情加载失败。");
    } finally {
      setLoading(false);
    }
  }

  async function triggerCustomerRescan() {
    if (!customerId) {
      return;
    }
    setRescanLoading(true);
    setMessage("");
    setError("");
    try {
      const response = await apiFetch<{ job_id: string }>(`/api/risk/customers/${customerId}/scan`, {
        method: "POST"
      });
      setMessage(`当前客户风险重算任务已提交，任务号：${response.data.job_id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "客户风险重算提交失败。");
    } finally {
      setRescanLoading(false);
    }
  }

  async function loadRiskChatSession() {
    if (!customerId) {
      return;
    }
    setChatLoading(true);
    setChatError("");
    try {
      const response = await apiFetch<RiskChatSession>(`/api/agent/risk-chat/customers/${customerId}/session`);
      setChatSession(response.data);
    } catch (exc) {
      setChatError(exc instanceof Error ? exc.message : "Risk Agent 对话加载失败。");
    } finally {
      setChatLoading(false);
    }
  }

  async function sendRiskChatMessage() {
    if (!customerId || !chatDraft.trim()) {
      return;
    }
    setChatSending(true);
    setChatError("");
    try {
      const response = await apiFetch<RiskChatMessageResult>(`/api/agent/risk-chat/customers/${customerId}/message`, {
        method: "POST",
        body: JSON.stringify({ message: chatDraft.trim() })
      });
      setChatSession((current) =>
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
      setChatDraft("");
    } catch (exc) {
      setChatError(exc instanceof Error ? exc.message : "Risk Agent 回复失败。");
    } finally {
      setChatSending(false);
    }
  }

  async function clearRiskChatSession() {
    if (!customerId) {
      return;
    }
    setChatSending(true);
    setChatError("");
    try {
      await apiFetch(`/api/agent/risk-chat/customers/${customerId}/session`, {
        method: "DELETE"
      });
      await loadRiskChatSession();
    } catch (exc) {
      setChatError(exc instanceof Error ? exc.message : "会话清空失败。");
    } finally {
      setChatSending(false);
    }
  }

  useEffect(() => {
    loadDetail();
    loadRiskChatSession();
  }, [customerId, highlightedRiskSnapshotId]);

  // 中文注释：优先高亮这次从风险中心点进来的那一条快照，没有上下文时再退回到最新快照。
  const selectedRisk = useMemo(() => {
    if (!detail?.risk_snapshots.length) {
      return null;
    }
    if (highlightedRiskSnapshotId) {
      return detail.risk_snapshots.find((item) => item.risk_snapshot_id === highlightedRiskSnapshotId) || detail.risk_snapshots[0];
    }
    return detail.risk_snapshots[0];
  }, [detail, highlightedRiskSnapshotId]);

  const pendingApprovalCount = detail?.approvals.filter((item) => item.status === "pending").length || 0;
  const activeTaskCount = detail?.tasks.filter((item) => ["pending", "in_progress"].includes(item.status)).length || 0;
  const latestRiskMeta = getRiskMeta(selectedRisk?.risk_level || "");
  const selectedPriorityMeta = getPriorityMeta(selectedRisk?.suggested_task_json?.priority || "medium");

  return (
    <AppShell>
      <section className="command-panel">
        <div>
          <p className="eyebrow">Customer Workbench</p>
          <h1>{detail?.customer.customer_name || customerId}</h1>
        </div>
        <div className="page-actions">
          <Link className="button-secondary" href={`/customers?customerId=${customerId}`}>
            打开 AI 对话工作台
          </Link>
          <Link className="button-secondary" href="/risks">
            返回风险中心
          </Link>
          <button className="button" onClick={triggerCustomerRescan} type="button" disabled={rescanLoading}>
            {rescanLoading ? "提交中..." : "重算当前客户风险"}
          </button>
        </div>
      </section>

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} detail="请确认客户权限、后端接口与 Worker 链路是否正常。" /> : null}
      {loading ? <LoadingCard detail="正在汇总客户基础信息、风险快照、跟进、审批和任务摘要。" /> : null}
      {!loading && !detail && !error ? (
        <EmptyCard text="未找到客户详情。" detail="请从风险中心重新进入，或确认当前账号是否有该客户查看权限。" />
      ) : null}

      {detail ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{latestRiskMeta.label}</strong>
              <span className="metric-label">当前风险等级</span>
              <p className="metric-detail">
                {selectedRisk ? `风险分数快照为 ${selectedRisk.risk_score}` : "当前还没有生成风险快照。"}
              </p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{detail.risk_snapshots.length}</strong>
              <span className="metric-label">最近风险快照</span>
              <p className="metric-detail">保留最近几次风险判断，方便回看状态是否在持续恶化或改善。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{pendingApprovalCount}</strong>
              <span className="metric-label">待审批动作</span>
              <p className="metric-detail">AI 建议是否真正进入执行，关键就在这里。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{activeTaskCount}</strong>
              <span className="metric-label">执行中任务</span>
              <p className="metric-detail">用来快速判断这个客户有没有人在持续跟进，而不是只停留在分析层。</p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Risk Context</p>
                  <h2>这次最值得看的风险上下文</h2>
                </div>
              </div>
              {selectedRisk ? (
                <>
                  <div className="meta-row">
                    <span className={`pill ${getRiskMeta(selectedRisk.risk_level).toneClass}`}>{getRiskMeta(selectedRisk.risk_level).label}</span>
                    <span className={`pill ${getStatusMeta(selectedRisk.status).toneClass}`}>{getStatusMeta(selectedRisk.status).label}</span>
                    <span className={`pill ${selectedPriorityMeta.toneClass}`}>{selectedPriorityMeta.label}</span>
                    <span className="meta-chip">快照时间 {formatDateTime(selectedRisk.created_at)}</span>
                  </div>
                  <div className="summary-list">
                    <div className="summary-item">
                      <strong>风险原因</strong>
                      <p>{selectedRisk.llm_reason || "当前没有风险解释。"}</p>
                    </div>
                    <div className="summary-item">
                      <strong>建议动作</strong>
                      <p>{selectedRisk.llm_suggestion || "当前没有动作建议。"}</p>
                    </div>
                    {selectedRisk.suggested_task_json?.recommended_script ? (
                      <div className="summary-item">
                        <strong>推荐话术</strong>
                        <blockquote>{selectedRisk.suggested_task_json.recommended_script}</blockquote>
                      </div>
                    ) : null}
                  </div>
                  <div className="detail-list">
                    <div className="detail-item">
                      <strong>命中规则</strong>
                      <p>
                        {selectedRisk.rule_hits_json.length
                          ? selectedRisk.rule_hits_json
                              .map((item) => `${item.rule_name || "未命名规则"}${item.score ? `（${item.score}）` : ""}`)
                              .join("、")
                          : "当前没有结构化规则命中明细。"}
                      </p>
                    </div>
                    <div className="detail-item">
                      <strong>证据线索</strong>
                      <p>
                        {evidenceEntries(selectedRisk.evidence_json).length
                          ? evidenceEntries(selectedRisk.evidence_json)
                              .map(([key, value]) => `${key}: ${String(value)}`)
                              .join("；")
                          : "当前没有可直接展示的证据摘要。"}
                      </p>
                    </div>
                  </div>
                </>
              ) : (
                <EmptyCard text="当前还没有风险快照。" detail="可以先触发「重算当前客户风险」，再回到这里查看结果。" />
              )}
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Customer Profile</p>
                  <h2>客户当前全貌</h2>
                </div>
              </div>
              <div className="meta-row">
                <span className="meta-chip">负责人 {detail.customer.owner_user_name || detail.customer.owner_user_id}</span>
                <span className="meta-chip">生命周期 {labelValue(detail.customer.lifecycle_stage)}</span>
                <span className="meta-chip">意向等级 {labelValue(detail.customer.intent_level)}</span>
                <span className="meta-chip">客户分级 {labelValue(detail.customer.customer_level)}</span>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>基础信息</strong>
                  <p>
                    行业 {labelValue(detail.customer.industry)}，区域 {labelValue(detail.customer.region)}，来源 {labelValue(detail.customer.source)}，
                    企业规模 {labelValue(detail.customer.company_size)}。
                  </p>
                </div>
                <div className="detail-item">
                  <strong>采购与预算</strong>
                  <p>
                    预算区间 {formatCurrency(detail.customer.budget_min)} ~ {formatCurrency(detail.customer.budget_max)}，预计采购日期{" "}
                    {formatDate(detail.customer.expected_purchase_at)}。
                  </p>
                </div>
                <div className="detail-item">
                  <strong>跟进状态</strong>
                  <p>
                    最近跟进 {formatDateTime(detail.customer.last_follow_up_at)}，下次跟进 {formatDateTime(detail.customer.next_follow_up_at)}，
                    最近情绪 {labelValue(detail.customer.last_sentiment)}，决策人状态 {labelValue(detail.customer.decision_maker_status)}。
                  </p>
                </div>
                <div className="detail-item">
                  <strong>补充备注</strong>
                  <p>
                    竞品介入 {detail.customer.competitor_involved ? "是" : "否"}，流失原因 {labelValue(detail.customer.lost_reason)}，
                    备注 {labelValue(detail.customer.remark)}。
                  </p>
                </div>
              </div>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Risk Agent Chat</p>
                  <h2>当前客户对话面板</h2>
                </div>
                <div className="page-actions">
                  <button className="button-secondary" type="button" onClick={clearRiskChatSession} disabled={chatSending || chatLoading}>
                    清空会话
                  </button>
                </div>
              </div>
              <div className="meta-row">
                <span className="meta-chip">短期记忆：最近 {chatSession?.memory_window.recent_rounds || 5} 轮全量</span>
                <span className="meta-chip">超过后自动压缩为历史摘要</span>
                <span className="meta-chip">长期记忆：客户经营记忆</span>
              </div>
              {chatError ? <p className="form-error">{chatError}</p> : null}
              {chatLoading ? (
                <LoadingCard detail="正在载入当前客户的 Risk Agent 会话记忆。" />
              ) : (
                <>
                  <div className="summary-list">
                    {chatSession?.recent_messages.length ? (
                      chatSession.recent_messages.map((item, index) => (
                        <div className="summary-item" key={`${item.created_at}-${index}`}>
                          <div className="meta-row">
                            <span className={`pill ${item.role === "user" ? "tone-info" : "tone-success"}`}>
                              {item.role === "user" ? "你" : "Risk Agent"}
                            </span>
                            <span className="meta-chip">{formatDateTime(item.created_at)}</span>
                          </div>
                          <p>{item.content}</p>
                        </div>
                      ))
                    ) : (
                      <div className="summary-item">
                        <strong>当前还没有对话记录</strong>
                        <p>你可以直接问这个客户为什么有风险、应该怎么回访，或者下一步是否值得升级动作。</p>
                      </div>
                    )}
                  </div>
                  <textarea
                    className="input-like textarea-like"
                    placeholder="例如：这个客户现在最值得先确认的风险点是什么？"
                    value={chatDraft}
                    onChange={(event) => setChatDraft(event.target.value)}
                    rows={5}
                    disabled={chatSending}
                  />
                  <div className="page-actions">
                    <button className="button" type="button" onClick={sendRiskChatMessage} disabled={chatSending || !chatDraft.trim()}>
                      {chatSending ? "发送中..." : "发送给 Risk Agent"}
                    </button>
                  </div>
                </>
              )}
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Memory View</p>
                  <h2>记忆命中情况</h2>
                </div>
              </div>
              <div className="summary-list">
                <div className="summary-item">
                  <strong>长期客户记忆</strong>
                  <p>{chatSession?.customer_memory_summary || "当前还没有写入客户长期记忆，建议先完成一次风险分析后再来对话。"}</p>
                  <div className="meta-row">
                    <span className="meta-chip">
                      最近编译时间 {chatSession?.customer_memory_updated_at ? formatDateTime(chatSession.customer_memory_updated_at) : "未生成"}
                    </span>
                  </div>
                </div>
                <div className="summary-item">
                  <strong>更早对话摘要</strong>
                  <p>{chatSession?.history_summary || "当前还没有触发对话压缩，超过最近 5 轮后会把更早内容沉淀到这里。"}</p>
                </div>
                <div className="summary-item">
                  <strong>当前风险参考</strong>
                  <p>
                    {chatSession?.latest_risk?.risk_level
                      ? `${getRiskMeta(chatSession.latest_risk.risk_level).label}，风险分 ${chatSession.latest_risk.risk_score ?? "未记录"}。`
                      : "当前还没有关联风险快照，Risk Agent 会先基于客户资料和长期记忆回答。"}
                  </p>
                </div>
              </div>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Risk History</p>
                  <h2>最近几次风险快照</h2>
                </div>
              </div>
              <div className="summary-list">
                {detail.risk_snapshots.length ? (
                  detail.risk_snapshots.map((item) => (
                    <div className="summary-item" key={item.risk_snapshot_id}>
                      <strong>
                        {getRiskMeta(item.risk_level).label} · 风险分 {item.risk_score}
                      </strong>
                      <p>{item.llm_reason || "当前没有风险解释。"}</p>
                      <div className="meta-row">
                        <span className={`pill ${getStatusMeta(item.status).toneClass}`}>{getStatusMeta(item.status).label}</span>
                        <span className="meta-chip">快照时间 {formatDateTime(item.created_at)}</span>
                        <Link className="button-secondary" href={`/customers/${customerId}?riskSnapshotId=${item.risk_snapshot_id}`}>
                          查看这次上下文
                        </Link>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="summary-item">
                    <strong>暂时没有历史风险快照</strong>
                    <p>这说明当前客户还没有进入风险识别链路，或本地演示数据尚未覆盖到该客户。</p>
                  </div>
                )}
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Recent Deals</p>
                  <h2>最近商机摘要</h2>
                </div>
              </div>
              <div className="summary-list">
                {detail.deals.length ? (
                  detail.deals.map((item) => (
                    <div className="summary-item" key={item.deal_id}>
                      <strong>{item.deal_name}</strong>
                      <p>
                        阶段 {labelValue(item.stage)}，金额 {formatCurrency(item.amount)}，报价 {formatCurrency(item.quote_amount)}，
                        关闭结果 {labelValue(item.close_result)}。
                      </p>
                      <div className="meta-row">
                        <span className="meta-chip">负责人 {item.owner_user_name || item.owner_user_id}</span>
                        <span className="meta-chip">最近报价 {formatDateTime(item.quoted_at)}</span>
                        <span className="meta-chip">预计关闭 {formatDate(item.expected_close_at)}</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="summary-item">
                    <strong>当前没有关联商机</strong>
                    <p>这不一定代表客户没有价值，也可能说明 CRM 侧的商机维护还没有跟上。</p>
                  </div>
                )}
              </div>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Follow Ups</p>
                  <h2>最近跟进记录</h2>
                </div>
              </div>
              <div className="summary-list">
                {detail.follow_ups.length ? (
                  detail.follow_ups.map((item) => (
                    <div className="summary-item" key={item.follow_up_id}>
                      <strong>{item.follow_up_type}</strong>
                      <p>{item.content}</p>
                      <div className="meta-row">
                        <span className="meta-chip">记录人 {item.owner_user_name || item.owner_user_id}</span>
                        <span className="meta-chip">客户情绪 {labelValue(item.sentiment)}</span>
                        <span className="meta-chip">发生时间 {formatDateTime(item.occurred_at)}</span>
                        <span className="meta-chip">下次跟进 {formatDateTime(item.next_follow_up_at)}</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="summary-item">
                    <strong>当前没有跟进记录</strong>
                    <p>如果一个客户长期没有跟进，这本身就可能是风险识别里最值得优先处理的信号。</p>
                  </div>
                )}
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Approvals & Tasks</p>
                  <h2>审批与执行摘要</h2>
                </div>
                <div className="page-actions">
                  <Link className="button-secondary" href={`/approvals?customerId=${customerId}`}>
                    查看该客户审批
                  </Link>
                  <Link className="button-secondary" href={`/tasks?customerId=${customerId}`}>
                    查看该客户任务
                  </Link>
                </div>
              </div>
              <div className="summary-list">
                {detail.approvals.length ? (
                  detail.approvals.map((item) => {
                    const priorityMeta = getPriorityMeta(item.proposed_payload_json.priority || "medium");
                    return (
                      <div className="summary-item" key={item.approval_id}>
                        <strong>{item.proposed_payload_json.title || item.approval_type}</strong>
                        <p>{item.proposed_payload_json.description || "当前审批记录没有补充动作描述。"}</p>
                        <div className="meta-row">
                          <span className={`pill ${getStatusMeta(item.status).toneClass}`}>{getStatusMeta(item.status).label}</span>
                          <span className={`pill ${priorityMeta.toneClass}`}>{priorityMeta.label}</span>
                          <span className="meta-chip">发起人 {item.requested_by_user_name || item.requested_by_user_id}</span>
                          <span className="meta-chip">审批时间 {formatDateTime(item.created_at)}</span>
                        </div>
                        {item.events.length ? (
                          <div className="detail-list">
                            {item.events.map((event) => (
                              <div className="detail-item" key={event.event_id}>
                                <strong>
                                  {getWorkflowEventLabel(event.action_type)} · {event.operator_user_name || event.operator_user_id}
                                </strong>
                                <p>{event.note || "当前动作没有补充说明。"}</p>
                                <span className="meta-chip">发生时间 {formatDateTime(event.happened_at)}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="detail-list">
                            <div className="detail-item">
                              <strong>暂时没有操作留痕</strong>
                              <p>这条审批多半是历史数据，后续一旦继续被处理，新的操作会自动补进轨迹。</p>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className="summary-item">
                    <strong>当前没有审批记录</strong>
                    <p>说明该客户的风险建议还没进入人工决策环节，或者之前的风险已经被处理干净。</p>
                  </div>
                )}

                {detail.tasks.length ? (
                  detail.tasks.map((item) => (
                    <div className="summary-item" key={item.task_id}>
                      <strong>{item.title}</strong>
                      <p>{item.description || item.result_note || "当前任务还没有补充说明。"}</p>
                      <div className="meta-row">
                        <span className={`pill ${getStatusMeta(item.status).toneClass}`}>{getStatusMeta(item.status).label}</span>
                        <span className={`pill ${getPriorityMeta(item.priority).toneClass}`}>{getPriorityMeta(item.priority).label}</span>
                        <span className="meta-chip">负责人 {item.assignee_user_name || item.assignee_user_id}</span>
                        <span className="meta-chip">截止时间 {formatDateTime(item.due_at)}</span>
                      </div>
                      {item.events.length ? (
                        <div className="detail-list">
                          {item.events.map((event) => (
                            <div className="detail-item" key={event.event_id}>
                              <strong>
                                {getWorkflowEventLabel(event.action_type)} · {event.operator_user_name || event.operator_user_id}
                              </strong>
                              <p>{event.note || "当前动作没有补充说明。"}</p>
                              <span className="meta-chip">发生时间 {formatDateTime(event.happened_at)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="detail-list">
                          <div className="detail-item">
                            <strong>暂时没有操作留痕</strong>
                            <p>如果这是旧任务数据，后续开始执行、完成或取消时，会自动把轨迹补齐。</p>
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="summary-item">
                    <strong>当前没有正式销售任务</strong>
                    <p>如果风险已经被识别但任务还没出现，通常需要回看审批是否卡住，或者建议是否被驳回。</p>
                  </div>
                )}
              </div>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Report References</p>
                  <h2>最近被哪些经营报告提到</h2>
                </div>
                <Link className="button-secondary" href={`/reports?customerId=${customerId}`}>
                  查看该客户报告
                </Link>
              </div>
              <div className="summary-list">
                {detail.report_refs.length ? (
                  detail.report_refs.map((item) => (
                    <div className="summary-item" key={item.report_id}>
                      <strong>
                        {getReportTypeLabel(item.report_type)} · {formatDate(item.report_date)}
                      </strong>
                      <p>{item.summary}</p>
                      <div className="meta-row">
                        <span className="meta-chip">归属人 {item.created_by_user_name || item.created_by_user_id}</span>
                        <span className="meta-chip">生成时间 {formatDateTime(item.created_at)}</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="summary-item">
                    <strong>最近没有报告引用</strong>
                    <p>这通常意味着该客户还没进入最近几期的重点风险名单，或者报告链路还没有覆盖到这个客户。</p>
                  </div>
                )}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
