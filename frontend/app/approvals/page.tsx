"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { ThemedSelect } from "@/components/ui/ThemedSelect";
import { apiFetch, getStoredUser } from "@/lib/api";
import { formatDateTime, getPriorityMeta, getStatusMeta } from "@/lib/presentation";

type Approval = {
  approval_id: string;
  approval_type: string;
  risk_snapshot_id: string | null;
  customer_id: string;
  customer_name: string | null;
  proposed_payload_json: Record<string, string> | string;
  status: string;
  requested_by_user_id: string;
  requested_by_user_name: string | null;
  reviewer_user_id: string | null;
  reviewer_user_name: string | null;
  created_at: string;
};

type ApprovalPayload = {
  title?: string;
  description?: string;
  recommended_script?: string;
  priority?: string;
  agent_review?: {
    approved?: boolean;
    summary?: string;
    review_note?: string;
    evidence_used?: string[];
  };
  agent_context?: {
    risk_score?: number | string;
    risk_level?: string;
    rag_status?: string;
    rag_trace_id?: string | null;
    rag_hit_count?: number;
    report_count?: number;
    tool_names?: string[];
    context_summary?: string;
  };
};

type ApprovalFilters = {
  status: string;
  reviewerKeyword: string;
  requesterKeyword: string;
  dateFrom: string;
  dateTo: string;
};

type ApprovalBatchFailureItem = {
  approval_id: string;
  message: string;
};

type ApprovalBatchResult = {
  actionLabel: string;
  successCount: number;
  failedCount: number;
  failedItems: ApprovalBatchFailureItem[];
};

const EMPTY_FILTERS: ApprovalFilters = {
  status: "",
  reviewerKeyword: "",
  requesterKeyword: "",
  dateFrom: "",
  dateTo: ""
};

function payloadOf(item: Approval): ApprovalPayload {
  if (typeof item.proposed_payload_json === "string") {
    try {
      return JSON.parse(item.proposed_payload_json) as ApprovalPayload;
    } catch {
      return {};
    }
  }

  return item.proposed_payload_json || {};
}

function ApprovalsPageContent() {
  const searchParams = useSearchParams();
  const customerFilter = searchParams.get("customerId");
  const relatedUserFilter = searchParams.get("relatedUserId");
  const relatedUserName = searchParams.get("relatedUserName");
  const currentUser = useMemo(() => getStoredUser(), []);
  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingApprovalId, setSavingApprovalId] = useState("");
  const [batchAction, setBatchAction] = useState<"" | "approve" | "reject">("");
  const [batchResult, setBatchResult] = useState<ApprovalBatchResult | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [filters, setFilters] = useState<ApprovalFilters>(EMPTY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<ApprovalFilters>(EMPTY_FILTERS);
  const [quickView, setQuickView] = useState<"all" | "pending" | "approved" | "rejected" | "mine">("all");
  const [approvalView, setApprovalView] = useState<"queue" | "batch">("queue");

  async function loadApprovals() {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams();
      if (customerFilter) {
        query.set("customer_id", customerFilter);
      }
      if (relatedUserFilter) {
        query.set("related_user_id", relatedUserFilter);
      }
      if (filters.status) {
        query.set("status", filters.status);
      }
      if (filters.reviewerKeyword) {
        query.set("reviewer_keyword", filters.reviewerKeyword);
      }
      if (filters.requesterKeyword) {
        query.set("requester_keyword", filters.requesterKeyword);
      }
      if (filters.dateFrom) {
        query.set("date_from", filters.dateFrom);
      }
      if (filters.dateTo) {
        query.set("date_to", filters.dateTo);
      }
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const response = await apiFetch<Approval[]>(`/api/approvals${suffix}`);
      setItems(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "审批列表加载失败。");
    } finally {
      setLoading(false);
    }
  }

  async function review(approvalId: string, action: "approve" | "reject") {
    setSavingApprovalId(approvalId);
    setMessage("");
    setError("");
    setBatchResult(null);
    try {
      const response = await apiFetch(`/api/approvals/${approvalId}/${action}`, {
        method: "POST",
        body: action === "reject" ? JSON.stringify({ review_comment: "前端手动驳回该条建议" }) : undefined
      });
      setMessage(response.msg);
      await loadApprovals();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "审批操作失败。");
    } finally {
      setSavingApprovalId("");
    }
  }

  async function batchReview(action: "approve" | "reject") {
    if (!selectedIds.length) {
      return;
    }
    setBatchAction(action);
    setMessage("");
    setError("");
    setBatchResult(null);
    try {
      const response = await apiFetch<{
        items: Array<{ approval_id: string; status: string; task_id?: string }>;
        failed_items: ApprovalBatchFailureItem[];
        success_count: number;
        failed_count: number;
      }>("/api/approvals/batch-review", {
        method: "POST",
        body: JSON.stringify({
          approval_ids: selectedIds,
          action,
          review_comment: action === "reject" ? "前端批量驳回该批建议" : undefined
        })
      });
      setMessage(response.msg);
      setBatchResult({
        actionLabel: action === "approve" ? "批量通过" : "批量驳回",
        successCount: response.data.success_count,
        failedCount: response.data.failed_count,
        failedItems: response.data.failed_items
      });
      setSelectedIds([]);
      await loadApprovals();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "批量审批失败。");
    } finally {
      setBatchAction("");
    }
  }

  useEffect(() => {
    loadApprovals();
  }, [customerFilter, filters, relatedUserFilter]);

  const filteredItems = useMemo(() => {
    if (quickView === "pending") {
      return items.filter((item) => item.status === "pending");
    }
    if (quickView === "approved") {
      return items.filter((item) => item.status === "approved");
    }
    if (quickView === "rejected") {
      return items.filter((item) => item.status === "rejected");
    }
    if (quickView === "mine" && currentUser) {
      return items.filter((item) => item.requested_by_user_id === currentUser.user_id || item.reviewer_user_id === currentUser.user_id);
    }
    return items;
  }, [currentUser, items, quickView]);

  const selectableIds = useMemo(
    () => filteredItems.filter((item) => item.status === "pending").map((item) => item.approval_id),
    [filteredItems]
  );

  useEffect(() => {
    const selectableIdSet = new Set(selectableIds);
    setSelectedIds((current) => {
      const next = current.filter((id) => selectableIdSet.has(id));
      return next.length === current.length ? current : next;
    });
  }, [selectableIds]);

  const allSelectableChecked =
    selectableIds.length > 0 && selectableIds.every((approvalId) => selectedIds.includes(approvalId));

  const overview = useMemo(() => {
    return {
      pending: filteredItems.filter((item) => item.status === "pending").length,
      approved: filteredItems.filter((item) => item.status === "approved").length,
      rejected: filteredItems.filter((item) => item.status === "rejected").length
    };
  }, [filteredItems]);

  function toggleSelected(approvalId: string) {
    setSelectedIds((current) =>
      current.includes(approvalId) ? current.filter((id) => id !== approvalId) : [...current, approvalId]
    );
  }

  function toggleAllSelectable() {
    setSelectedIds(allSelectableChecked ? [] : selectableIds);
  }

  return (
    <AppShell>
      {customerFilter ? (
        <section className="command-panel">
          <div className="page-actions">
            <Link className="button-secondary" href={`/customers/${customerFilter}`}>
              返回客户详情
            </Link>
            <Link className="ghost-button inline" href="/approvals">
              查看全部审批
            </Link>
          </div>
        </section>
      ) : null}

      {relatedUserFilter ? (
        <section className="command-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Report Drilldown</p>
              <h2>当前负责人相关审批</h2>
              <p className="panel-copy">
                当前列表已按负责人 {relatedUserName || relatedUserFilter} 过滤，会同时命中发起人、审批人以及审批 payload 里的任务负责人。
              </p>
            </div>
            <div className="page-actions">
              <Link className="button-secondary" href={customerFilter ? `/approvals?customerId=${customerFilter}` : "/approvals"}>
                清除负责人过滤
              </Link>
            </div>
          </div>
        </section>
      ) : null}

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} detail="请确认审批接口、权限与后端服务是否运行正常。" /> : null}
      {loading ? <LoadingCard detail="正在同步审批队列、建议 payload 与当前状态。" /> : null}
      {!loading && !items.length && !error ? (
        <EmptyCard text="当前没有待处理审批。" detail="可以先运行风险扫描，让系统生成新的 AI 动作建议。" />
      ) : null}

      {items.length ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{overview.pending}</strong>
              <span className="metric-label">待确认</span>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.approved}</strong>
              <span className="metric-label">已批准</span>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.rejected}</strong>
              <span className="metric-label">已驳回</span>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{filteredItems.length}</strong>
              <span className="metric-label">当前视图</span>
            </article>
          </section>

          <div className="section-eyebrow-row">
            <p className="eyebrow">Workspace</p>
            <div className="workspace-tabs">
              <button
                className={`workspace-tab ${approvalView === "queue" ? "workspace-tab-active" : ""}`}
                onClick={() => setApprovalView("queue")}
                type="button"
              >
                <span className="workspace-tab-dot" />
                审批队列
              </button>
              <button
                className={`workspace-tab ${approvalView === "batch" ? "workspace-tab-active" : ""}`}
                onClick={() => setApprovalView("batch")}
                type="button"
              >
                <span className="workspace-tab-dot" />
                批量处理
              </button>
            </div>
          </div>

          {approvalView === "queue" ? (
            <>
              <section className="command-panel">
                <div className="eval-control-bar">
                  <label>
                    状态
                    <ThemedSelect
                      onChange={(value) => setDraftFilters((current) => ({ ...current, status: value }))}
                      options={[
                        { value: "", label: "全部状态" },
                        { value: "pending", label: "待审批" },
                        { value: "approved", label: "已通过" },
                        { value: "rejected", label: "已驳回" },
                      ]}
                      value={draftFilters.status}
                    />
                  </label>
                  <label>
                    审批人
                    <input
                      placeholder="输入审批人姓名或 ID"
                      value={draftFilters.reviewerKeyword}
                      onChange={(event) =>
                        setDraftFilters((current) => ({ ...current, reviewerKeyword: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    发起人
                    <input
                      placeholder="输入发起人姓名或 ID"
                      value={draftFilters.requesterKeyword}
                      onChange={(event) =>
                        setDraftFilters((current) => ({ ...current, requesterKeyword: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    开始日期
                    <input
                      type="date"
                      value={draftFilters.dateFrom}
                      onChange={(event) => setDraftFilters((current) => ({ ...current, dateFrom: event.target.value }))}
                    />
                  </label>
                  <label>
                    结束日期
                    <input
                      type="date"
                      value={draftFilters.dateTo}
                      onChange={(event) => setDraftFilters((current) => ({ ...current, dateTo: event.target.value }))}
                    />
                  </label>
                </div>
                <div className="page-actions">
                  <button className="button" onClick={() => setFilters(draftFilters)} type="button">
                    应用筛选
                  </button>
                  <button
                    className="button-secondary"
                    onClick={() => {
                      setDraftFilters(EMPTY_FILTERS);
                      setFilters(EMPTY_FILTERS);
                      setQuickView("all");
                    }}
                    type="button"
                  >
                    重置筛选
                  </button>
                </div>
                <div className="page-actions">
                  <button className={quickView === "all" ? "button" : "button-secondary"} onClick={() => setQuickView("all")} type="button">
                    全部记录
                  </button>
                  <button className={quickView === "pending" ? "button" : "button-secondary"} onClick={() => setQuickView("pending")} type="button">
                    待处理
                  </button>
                  <button className={quickView === "approved" ? "button" : "button-secondary"} onClick={() => setQuickView("approved")} type="button">
                    已通过
                  </button>
                  <button className={quickView === "rejected" ? "button" : "button-secondary"} onClick={() => setQuickView("rejected")} type="button">
                    已驳回
                  </button>
                  <button className={quickView === "mine" ? "button" : "button-secondary"} onClick={() => setQuickView("mine")} type="button">
                    与我相关
                  </button>
                </div>
              </section>

              {selectableIds.length ? (
                <section className="command-panel">
                  <div className="section-eyebrow-row">
                    <p className="eyebrow">Quick Batch</p>
                    <span className="meta-chip">{selectedIds.length} / {selectableIds.length} 已选</span>
                  </div>
                  <div className="page-actions">
                    <button className="button-secondary" onClick={toggleAllSelectable} type="button">
                      {allSelectableChecked ? "清空当前页" : "全选待审批"}
                    </button>
                    <button className="button-secondary" onClick={() => setSelectedIds([])} type="button" disabled={!selectedIds.length}>
                      清空选择
                    </button>
                    <button className="button" onClick={() => batchReview("approve")} type="button" disabled={!selectedIds.length || Boolean(batchAction)}>
                      {batchAction === "approve" ? "批量通过中..." : "批量通过"}
                    </button>
                    <button
                      className="ghost-button inline"
                      onClick={() => batchReview("reject")}
                      type="button"
                      disabled={!selectedIds.length || Boolean(batchAction)}
                    >
                      {batchAction === "reject" ? "批量驳回中..." : "批量驳回"}
                    </button>
                  </div>
                </section>
              ) : null}

              <section className="card-stack card-stack-lg">
                {filteredItems.map((item) => {
                  const payload = payloadOf(item);
                  const statusMeta = getStatusMeta(item.status);
                  const priorityMeta = getPriorityMeta(payload.priority || "medium");
                  const checked = selectedIds.includes(item.approval_id);

	                  return (
	                    <article className="approval-card" key={item.approval_id}>
                      <div className="approval-card-header">
                        <div>
                          <p className="eyebrow">Customer {item.customer_id}</p>
                          <h2 className="section-title">{payload.title || item.approval_type}</h2>
                          <p className="lead">{item.customer_name || item.customer_id}</p>
                        </div>
                        <div className="approval-meta">
                          {item.status === "pending" ? (
                            <label className="meta-chip">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleSelected(item.approval_id)}
                              />
                              批量选择
                            </label>
                          ) : null}
                          <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                          <span className={`pill ${priorityMeta.toneClass}`}>{priorityMeta.label}</span>
                        </div>
                      </div>

                      <div className="meta-row">
                        <span className="meta-chip">发起人 {item.requested_by_user_name || item.requested_by_user_id}</span>
                        <span className="meta-chip">{formatDateTime(item.created_at)}</span>
                        <span className="meta-chip">审批人 {item.reviewer_user_name || item.reviewer_user_id || "待分配"}</span>
                      </div>

	                      <div className="summary-list">
	                        <div className="summary-item">
	                          <strong>动作描述</strong>
	                          <p>{payload.description || "等待主管确认这条 AI 建议是否值得转成正式销售任务。"}</p>
	                        </div>
	                        {payload.agent_review?.summary ? (
	                          <div className="summary-item">
	                            <strong>Agent 复核结论</strong>
	                            <p>{payload.agent_review.summary}</p>
	                            <p>{payload.agent_review.review_note || "当前没有额外复核备注。"}</p>
	                            <div className="meta-row">
	                              {(Array.isArray(payload.agent_review.evidence_used) ? payload.agent_review.evidence_used : []).map(
	                                (evidence) => (
	                                  <span className="meta-chip" key={`${item.approval_id}-${evidence}`}>
	                                    {evidence}
	                                  </span>
	                                )
	                              )}
	                            </div>
	                          </div>
	                        ) : null}
	                        {payload.agent_context ? (
	                          <div className="summary-item">
	                            <strong>Agent 证据摘要</strong>
	                            <p>{payload.agent_context.context_summary || "当前没有额外上下文摘要。"}</p>
	                            <div className="meta-row">
	                              {payload.agent_context.risk_level ? (
	                                <span className="meta-chip">
	                                  风险 {payload.agent_context.risk_level} / {String(payload.agent_context.risk_score ?? "-")}
	                                </span>
	                              ) : null}
	                              {payload.agent_context.report_count ? (
	                                <span className="meta-chip">报告 {payload.agent_context.report_count}</span>
	                              ) : null}
	                              {payload.agent_context.rag_trace_id ? (
	                                <span className="meta-chip">Trace {payload.agent_context.rag_trace_id}</span>
	                              ) : null}
	                              {(Array.isArray(payload.agent_context.tool_names) ? payload.agent_context.tool_names : []).map(
	                                (toolName) => (
	                                  <span className="meta-chip" key={`${item.approval_id}-${toolName}`}>
	                                    {toolName}
	                                  </span>
	                                )
	                              )}
	                            </div>
	                          </div>
	                        ) : null}
	                        {payload.recommended_script ? (
	                          <div className="summary-item">
	                            <strong>推荐话术</strong>
	                            <blockquote>{payload.recommended_script}</blockquote>
                          </div>
                        ) : null}
                      </div>

                      {item.status === "pending" ? (
                        <div className="action-row">
                          <button
                            className="button"
                            onClick={() => review(item.approval_id, "approve")}
                            type="button"
                            disabled={Boolean(batchAction) || savingApprovalId === item.approval_id}
                          >
                            {savingApprovalId === item.approval_id ? "处理中..." : "批准并创建任务"}
                          </button>
                          <button
                            className="ghost-button inline"
                            onClick={() => review(item.approval_id, "reject")}
                            type="button"
                            disabled={Boolean(batchAction) || savingApprovalId === item.approval_id}
                          >
                            驳回建议
                          </button>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </section>
            </>
          ) : (
            <>
              <section className="command-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Batch Review</p>
                    <h2>批量审批</h2>
                  </div>
                  <span className="meta-chip">当前选中 {selectedIds.length} / {selectableIds.length}</span>
                </div>
                <div className="page-actions">
                  <button className="button-secondary" onClick={toggleAllSelectable} type="button">
                    {allSelectableChecked ? "清空当前页选择" : "全选当前页待审批"}
                  </button>
                  <button className="button-secondary" onClick={() => setSelectedIds([])} type="button" disabled={!selectedIds.length}>
                    清空选择
                  </button>
                  <button className="button" onClick={() => batchReview("approve")} type="button" disabled={!selectedIds.length || Boolean(batchAction)}>
                    {batchAction === "approve" ? "批量通过中..." : "批量通过并创建任务"}
                  </button>
                  <button
                    className="ghost-button inline"
                    onClick={() => batchReview("reject")}
                    type="button"
                    disabled={!selectedIds.length || Boolean(batchAction)}
                  >
                    {batchAction === "reject" ? "批量驳回中..." : "批量驳回建议"}
                  </button>
                </div>
              </section>

              {batchResult ? (
                <section className="command-panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Batch Result</p>
                      <h2>上次批量审批结果</h2>
                    </div>
                    <span className="meta-chip">
                      {batchResult.actionLabel}：成功 {batchResult.successCount} 条，失败 {batchResult.failedCount} 条
                    </span>
                  </div>
                  {batchResult.failedItems.length ? (
                    <div className="detail-list">
                      {batchResult.failedItems.map((item) => (
                        <div className="detail-item" key={`${item.approval_id}-${item.message}`}>
                          <strong>审批 {item.approval_id}</strong>
                          <p>{item.message}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="lead">本次批量审批没有失败项。</p>
                  )}
                </section>
              ) : null}

              {!selectableIds.length ? (
                <section className="command-panel">
                  <p className="lead">当前没有可批量操作的待审批记录，请先回到审批队列中确认视图范围。</p>
                </section>
              ) : null}
            </>
          )}
        </>
      ) : null}
    </AppShell>
  );
}

export default function ApprovalsPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <LoadingCard detail="正在同步审批队列、建议 payload 与当前状态。" />
        </AppShell>
      }
    >
      <ApprovalsPageContent />
    </Suspense>
  );
}
