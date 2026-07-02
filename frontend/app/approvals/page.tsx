"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
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
  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadApprovals() {
    setLoading(true);
    setError("");
    try {
      const query = customerFilter ? `?customer_id=${encodeURIComponent(customerFilter)}` : "";
      const response = await apiFetch<Approval[]>(`/api/approvals${query}`);
      setItems(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "审批列表加载失败。");
    } finally {
      setLoading(false);
    }
  }

  async function review(approvalId: string, action: "approve" | "reject") {
    setMessage("");
    setError("");
    try {
      await apiFetch(`/api/approvals/${approvalId}/${action}`, {
        method: "POST",
        body: action === "reject" ? JSON.stringify({ review_comment: "演示环境前端触发驳回" }) : undefined
      });
      setMessage(action === "approve" ? "审批已通过，正式销售任务已创建。" : "审批已驳回。");
      await loadApprovals();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "审批操作失败。");
    }
  }

  useEffect(() => {
    loadApprovals();
  }, [customerFilter]);

  // 中文注释：审批页核心是把队列状态显性化，让“AI 建议是否落地”一眼可见。
  const overview = useMemo(() => {
    return {
      pending: items.filter((item) => item.status === "pending").length,
      approved: items.filter((item) => item.status === "approved").length,
      rejected: items.filter((item) => item.status === "rejected").length
    };
  }, [items]);

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
              <strong className="metric-value">{items.length}</strong>
              <span className="metric-label">累计记录</span>
              <p className="metric-detail">这部分数据也能帮助面试或演示时展示完整的人机协作链路。</p>
            </article>
          </section>

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
                  <p>如果高价值动作在待审批里堆积，前端看起来“很聪明”，但业务上仍然没有发生任何事。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="approval-stack">
            {items.map((item) => {
              const payload = payloadOf(item);
              const statusMeta = getStatusMeta(item.status);
              const priorityMeta = getPriorityMeta(payload.priority || "medium");

              return (
                <article className="approval-card" key={item.approval_id}>
                  <div className="approval-card-header">
                    <div>
                      <p className="eyebrow">Customer {item.customer_id}</p>
                      <h2 className="section-title">{payload.title || item.approval_type}</h2>
                      <p className="lead">{item.customer_name || item.customer_id}</p>
                    </div>
                    <div className="approval-meta">
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
                      <button className="button" onClick={() => review(item.approval_id, "approve")} type="button">
                        批准并创建任务
                      </button>
                      <button className="ghost-button inline" onClick={() => review(item.approval_id, "reject")} type="button">
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
    <Suspense fallback={<AppShell><LoadingCard detail="正在同步审批队列、建议 payload 与当前状态。" /></AppShell>}>
      <ApprovalsPageContent />
    </Suspense>
  );
}
