"use client";

import { useEffect, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

type Approval = {
  approval_id: string;
  approval_type: string;
  risk_snapshot_id: string | null;
  customer_id: string;
  proposed_payload_json: Record<string, string> | string;
  status: string;
  requested_by_user_id: string;
  reviewer_user_id: string | null;
  created_at: string;
};

function payloadOf(item: Approval) {
  if (typeof item.proposed_payload_json === "string") {
    try {
      return JSON.parse(item.proposed_payload_json) as Record<string, string>;
    } catch {
      return {};
    }
  }
  return item.proposed_payload_json || {};
}

export default function ApprovalsPage() {
  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadApprovals() {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<Approval[]>("/api/approvals");
      setItems(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "审批列表加载失败");
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
        body: action === "reject" ? JSON.stringify({ review_comment: "前端演示驳回" }) : undefined
      });
      setMessage(action === "approve" ? "审批通过，已创建正式销售任务。" : "审批已驳回。");
      await loadApprovals();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "审批操作失败");
    }
  }

  useEffect(() => {
    loadApprovals();
  }, []);

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Human in the loop</p>
          <h1>AI 任务审批台</h1>
          <p className="lead">AI 只能生成任务草稿，主管确认后才会创建正式销售任务。</p>
        </div>
      </section>
      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} /> : null}
      {loading ? <LoadingCard /> : null}
      {!loading && !items.length && !error ? <EmptyCard text="暂无审批记录。" /> : null}
      <div className="stack">
        {items.map((item) => {
          const payload = payloadOf(item);
          return (
            <article className="approval-card" key={item.approval_id}>
              <div>
                <p className="eyebrow">{item.customer_id}</p>
                <h2>{payload.title || item.approval_type}</h2>
                <p>{payload.description || "等待主管确认是否转为正式销售任务。"}</p>
                {payload.recommended_script ? <blockquote>{payload.recommended_script}</blockquote> : null}
              </div>
              <div className="approval-meta">
                <span className="pill">{item.status}</span>
                <span>{payload.priority || "medium"}</span>
                {item.status === "pending" ? (
                  <div className="action-row">
                    <button className="button" onClick={() => review(item.approval_id, "approve")} type="button">
                      批准
                    </button>
                    <button className="ghost-button inline" onClick={() => review(item.approval_id, "reject")} type="button">
                      驳回
                    </button>
                  </div>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </AppShell>
  );
}
