"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
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
};

type ApprovalFilters = {
  status: string;
  reviewerKeyword: string;
  requesterKeyword: string;
  dateFrom: string;
  dateTo: string;
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
  const currentUser = useMemo(() => getStoredUser(), []);
  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingApprovalId, setSavingApprovalId] = useState("");
  const [batchAction, setBatchAction] = useState<"" | "approve" | "reject">("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [filters, setFilters] = useState<ApprovalFilters>(EMPTY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<ApprovalFilters>(EMPTY_FILTERS);
  const [quickView, setQuickView] = useState<"all" | "pending" | "approved" | "rejected" | "mine">("all");

  async function loadApprovals() {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams();
      if (customerFilter) {
        query.set("customer_id", customerFilter);
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
    try {
      const response = await apiFetch("/api/approvals/batch-review", {
        method: "POST",
        body: JSON.stringify({
          approval_ids: selectedIds,
          action,
          review_comment: action === "reject" ? "前端批量驳回该批建议" : undefined
        })
      });
      setMessage(response.msg);
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
  }, [customerFilter, filters]);

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
      <section className="page-hero">
        <div>
          <p className="eyebrow">Human Checkpoint</p>
          <h1>AI 可以提建议，但真正进入执行队列之前，必须先过人这一关。</h1>
          <p className="lead">
            审批页负责把 AI 的速度和业务的安全感平衡起来，避免错误动作直接打到客户一线。
            {customerFilter ? ` 当前已聚焦客户 ${customerFilter}。` : ""}
          </p>
        </div>
        {customerFilter ? (
          <div className="page-actions">
            <Link className="button-secondary" href={`/customers/${customerFilter}`}>
              返回客户详情
            </Link>
            <Link className="ghost-button inline" href="/approvals">
              查看全部审批
            </Link>
          </div>
        ) : null}
      </section>

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
              <p className="metric-detail">主管还没拍板的动作数量，决定系统建议能否继续向下游流动。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.approved}</strong>
              <span className="metric-label">已批准</span>
              <p className="metric-detail">这些建议已经转成正式销售任务，可以去任务页继续追踪。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overview.rejected}</strong>
              <span className="metric-label">已驳回</span>
              <p className="metric-detail">被驳回的动作值得回看规则命中与建议质量是否合理。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{filteredItems.length}</strong>
              <span className="metric-label">当前视图记录</span>
              <p className="metric-detail">可以快速确认当前筛选条件下还有多少条审批需要回看或处理。</p>
            </article>
          </section>

          <section className="command-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Queue Filters</p>
                <h2>审批筛选与快捷视图</h2>
              </div>
            </div>
            <div className="eval-control-bar">
              <label>
                状态
                <select
                  className="input-like compact-input"
                  value={draftFilters.status}
                  onChange={(event) => setDraftFilters((current) => ({ ...current, status: event.target.value }))}
                >
                  <option value="">全部状态</option>
                  <option value="pending">待审批</option>
                  <option value="approved">已通过</option>
                  <option value="rejected">已驳回</option>
                </select>
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
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Batch Review</p>
                  <h2>批量审批工具条</h2>
                </div>
                <span className="meta-chip">当前选中 {selectedIds.length} / {selectableIds.length}</span>
              </div>
              <p className="lead">只允许勾选当前视图中的待审批记录，避免把已处理记录误带进批量动作。</p>
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
          ) : null}

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Approval Standard</p>
                  <h2>审批时建议优先看三件事</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>建议是不是对准了真实风险</strong>
                  <p>如果风险原因本身判断偏了，再好的任务标题也会把销售带离正确方向。</p>
                </div>
                <div className="detail-item">
                  <strong>动作有没有明确负责人和价值</strong>
                  <p>审批通过后会直接进入任务页，因此建议应尽量可执行、可衡量、可交付。</p>
                </div>
                <div className="detail-item">
                  <strong>推荐话术是否适合当前客户关系</strong>
                  <p>话术可以给销售参考，但是否直接使用，仍然需要业务负责人二次判断。</p>
                </div>
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Queue Reminder</p>
                  <h2>这页的核心价值</h2>
                </div>
              </div>
              <div className="summary-list">
                <div className="summary-item">
                  <strong>不是为了拖慢 AI，而是为了保证方向正确。</strong>
                  <p>审批机制让系统更像真实企业工程，而不是一个只会吐建议的聊天机器人。</p>
                </div>
                <div className="summary-item">
                  <strong>批准越快，执行越闭环。</strong>
                  <p>如果高价值动作在待审批里堆积，前端看起来很聪明，但业务上仍然没有真正发生任何事。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="approval-stack">
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
                    <span className="meta-chip">审批时间 {formatDateTime(item.created_at)}</span>
                    <span className="meta-chip">审批人 {item.reviewer_user_name || item.reviewer_user_id || "待分配"}</span>
                  </div>

                  <div className="summary-list">
                    <div className="summary-item">
                      <strong>动作描述</strong>
                      <p>{payload.description || "等待主管确认这条 AI 建议是否值得转成正式销售任务。"}</p>
                    </div>
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
