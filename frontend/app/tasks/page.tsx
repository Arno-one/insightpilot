"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch, getStoredUser } from "@/lib/api";
import { formatDateTime, getPriorityMeta, getStatusMeta } from "@/lib/presentation";

type Task = {
  task_id: string;
  approval_id: string | null;
  customer_id: string;
  customer_name: string | null;
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
};

type TaskDraft = {
  result_note: string;
  sentiment: "positive" | "neutral" | "negative";
  next_follow_up_at: string;
};

type TaskFilters = {
  status: string;
  priority: string;
  assigneeKeyword: string;
  overdueOnly: boolean;
};

const EMPTY_TASK_DRAFT: TaskDraft = {
  result_note: "",
  sentiment: "neutral",
  next_follow_up_at: ""
};

const EMPTY_FILTERS: TaskFilters = {
  status: "",
  priority: "",
  assigneeKeyword: "",
  overdueOnly: false
};

function isActiveTask(task: Task) {
  return ["pending", "in_progress"].includes(task.status);
}

function isOverdueTask(task: Task) {
  return Boolean(task.due_at && isActiveTask(task) && new Date(task.due_at) < new Date());
}

function TasksPageContent() {
  const searchParams = useSearchParams();
  const customerFilter = searchParams.get("customerId");
  const currentUser = useMemo(() => getStoredUser(), []);
  const [items, setItems] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingTaskId, setSavingTaskId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, TaskDraft>>({});
  const [filters, setFilters] = useState<TaskFilters>(EMPTY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<TaskFilters>(EMPTY_FILTERS);
  const [quickView, setQuickView] = useState<"all" | "pending" | "overdue" | "highPriorityOpen" | "mine">("all");

  function patchDraft(taskId: string, patch: Partial<TaskDraft>) {
    setDrafts((current) => ({
      ...current,
      [taskId]: {
        ...EMPTY_TASK_DRAFT,
        ...current[taskId],
        ...patch
      }
    }));
  }

  async function loadTasks() {
    setLoading(true);
    setError("");
    try {
      // 中文注释：查询参数由后端正式承接，前端只负责把用户筛选条件清晰地拼出来。
      const query = new URLSearchParams();
      if (customerFilter) {
        query.set("customer_id", customerFilter);
      }
      if (filters.status) {
        query.set("status", filters.status);
      }
      if (filters.priority) {
        query.set("priority", filters.priority);
      }
      if (filters.assigneeKeyword) {
        query.set("assignee_keyword", filters.assigneeKeyword);
      }
      if (filters.overdueOnly) {
        query.set("overdue_only", "true");
      }
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const response = await apiFetch<Task[]>(`/api/tasks${suffix}`);
      setItems(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "任务列表加载失败。");
    } finally {
      setLoading(false);
    }
  }

  async function updateTask(taskId: string, status: "in_progress" | "completed" | "cancelled") {
    const draft = drafts[taskId] || EMPTY_TASK_DRAFT;
    setSavingTaskId(taskId);
    setError("");
    setMessage("");
    try {
      await apiFetch(`/api/tasks/${taskId}/status`, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          result_note:
            draft.result_note ||
            (status === "cancelled"
              ? "演示环境前端触发取消"
              : status === "completed"
                ? "演示环境前端标记完成"
                : "任务已开始推进"),
          sentiment: draft.sentiment,
          next_follow_up_at: draft.next_follow_up_at || null
        })
      });
      setMessage(
        status === "in_progress"
          ? "任务已开始执行。"
          : status === "completed"
            ? "任务已完成，并已自动回写一条跟进记录。"
            : "任务已取消。"
      );
      await loadTasks();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "任务状态更新失败。");
    } finally {
      setSavingTaskId("");
    }
  }

  useEffect(() => {
    loadTasks();
  }, [customerFilter, filters]);

  const quickFilteredItems = useMemo(() => {
    if (quickView === "pending") {
      return items.filter(isActiveTask);
    }
    if (quickView === "overdue") {
      return items.filter(isOverdueTask);
    }
    if (quickView === "highPriorityOpen") {
      return items.filter((item) => item.priority === "high" && isActiveTask(item));
    }
    if (quickView === "mine" && currentUser) {
      return items.filter((item) => item.assignee_user_id === currentUser.user_id);
    }
    return items;
  }, [currentUser, items, quickView]);

  const sortedItems = useMemo(() => {
    // 中文注释：先按截止时间排，能让“快逾期”和“已逾期”的任务自然浮到前面。
    return [...quickFilteredItems].sort((a, b) => {
      if (!a.due_at && !b.due_at) {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      if (!a.due_at) {
        return 1;
      }
      if (!b.due_at) {
        return -1;
      }
      return new Date(a.due_at).getTime() - new Date(b.due_at).getTime();
    });
  }, [quickFilteredItems]);

  const activeCount = sortedItems.filter(isActiveTask).length;
  const inProgressCount = sortedItems.filter((item) => item.status === "in_progress").length;
  const completedCount = sortedItems.filter((item) => item.status === "completed").length;
  const overdueCount = sortedItems.filter(isOverdueTask).length;

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Execution Queue</p>
          <h1>任务创建只是开始，真正有价值的是它有没有被持续推进。</h1>
          <p className="lead">
            这里承接审批通过后的执行现场，重点看负责人、优先级、截止时间和实际推进状态。
            {customerFilter ? ` 当前已聚焦客户 ${customerFilter}。` : ""}
          </p>
        </div>
        {customerFilter ? (
          <div className="page-actions">
            <Link className="button-secondary" href={`/customers/${customerFilter}`}>
              返回客户详情
            </Link>
            <Link className="ghost-button inline" href="/tasks">
              查看全部任务
            </Link>
          </div>
        ) : null}
      </section>

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} detail="请确认任务接口、登录权限与后端服务是否正常。" /> : null}
      {loading ? <LoadingCard detail="正在同步销售任务、负责人和截止时间。" /> : null}
      {!loading && !sortedItems.length && !error ? (
        <EmptyCard text="当前还没有销售任务。" detail="可以先从审批台通过一条 AI 建议，再回到这里查看任务落地情况。" />
      ) : null}

      {sortedItems.length ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{activeCount}</strong>
              <span className="metric-label">待跟进任务</span>
              <p className="metric-detail">还处于待处理或执行中的任务总量。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{inProgressCount}</strong>
              <span className="metric-label">正在推进</span>
              <p className="metric-detail">销售已经接手，但仍需要继续推进的任务数量。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{overdueCount}</strong>
              <span className="metric-label">已逾期</span>
              <p className="metric-detail">建议主管优先回看逾期原因，避免高价值动作拖延。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{completedCount}</strong>
              <span className="metric-label">已完成</span>
              <p className="metric-detail">完成量越高，说明 AI 建议越有机会形成业务正反馈。</p>
            </article>
          </section>

          <section className="command-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Queue Filters</p>
                <h2>任务筛选与快捷视图</h2>
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
                  <option value="pending">待处理</option>
                  <option value="in_progress">执行中</option>
                  <option value="completed">已完成</option>
                  <option value="cancelled">已取消</option>
                </select>
              </label>
              <label>
                优先级
                <select
                  className="input-like compact-input"
                  value={draftFilters.priority}
                  onChange={(event) => setDraftFilters((current) => ({ ...current, priority: event.target.value }))}
                >
                  <option value="">全部优先级</option>
                  <option value="high">高</option>
                  <option value="medium">中</option>
                  <option value="low">低</option>
                </select>
              </label>
              <label>
                负责人
                <input
                  placeholder="输入负责人姓名或 ID"
                  value={draftFilters.assigneeKeyword}
                  onChange={(event) =>
                    setDraftFilters((current) => ({ ...current, assigneeKeyword: event.target.value }))
                  }
                />
              </label>
              <label className="meta-chip">
                <input
                  type="checkbox"
                  checked={draftFilters.overdueOnly}
                  onChange={(event) =>
                    setDraftFilters((current) => ({ ...current, overdueOnly: event.target.checked }))
                  }
                />
                仅看逾期
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
                全部任务
              </button>
              <button
                className={quickView === "pending" ? "button" : "button-secondary"}
                onClick={() => setQuickView("pending")}
                type="button"
              >
                待跟进
              </button>
              <button
                className={quickView === "overdue" ? "button" : "button-secondary"}
                onClick={() => setQuickView("overdue")}
                type="button"
              >
                逾期任务
              </button>
              <button
                className={quickView === "highPriorityOpen" ? "button" : "button-secondary"}
                onClick={() => setQuickView("highPriorityOpen")}
                type="button"
              >
                高优先级未完成
              </button>
              <button className={quickView === "mine" ? "button" : "button-secondary"} onClick={() => setQuickView("mine")} type="button">
                我负责
              </button>
            </div>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Execution Principle</p>
                  <h2>任务页应该回答的三个问题</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>谁来做</strong>
                  <p>每条任务都必须能快速看出负责人，避免“大家都知道但没人接”的隐形失速。</p>
                </div>
                <div className="detail-item">
                  <strong>何时做完</strong>
                  <p>截止时间越清晰，主管越容易判断资源是否该重新分配。</p>
                </div>
                <div className="detail-item">
                  <strong>是否还值得做</strong>
                  <p>当任务已经逾期或客户风险变化时，应该回看动作是否需要重排优先级。</p>
                </div>
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Queue Health</p>
                  <h2>当前执行队列状态</h2>
                </div>
              </div>
              <div className="summary-list">
                <div className="summary-item">
                  <strong>高优先级动作需要短链路</strong>
                  <p>如果高优先级任务在队列里停留太久，风险预警就只剩展示价值，没有真正转成结果。</p>
                </div>
                <div className="summary-item">
                  <strong>逾期任务需要主管回看</strong>
                  <p>逾期不一定意味着执行差，也可能说明客户状态、商机阶段或跟进策略需要调整。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="task-board">
            {sortedItems.map((item) => {
              const statusMeta = getStatusMeta(item.status);
              const priorityMeta = getPriorityMeta(item.priority);
              const overdue = isOverdueTask(item);

              return (
                <article className="task-card" key={item.task_id}>
                  <div className="task-card-header">
                    <div>
                      <p className="eyebrow">{item.task_type}</p>
                      <h2 className="section-title">{item.title}</h2>
                      <p className="lead">{item.customer_name || item.customer_id}</p>
                    </div>
                    <div className="task-meta">
                      <span className={`pill ${priorityMeta.toneClass}`}>{priorityMeta.label}</span>
                      <span className={`pill ${statusMeta.toneClass}`}>{statusMeta.label}</span>
                    </div>
                  </div>

                  <div className="meta-row">
                    <span className="meta-chip">客户 {item.customer_name || item.customer_id}</span>
                    <span className="meta-chip">负责人 {item.assignee_user_name || item.assignee_user_id}</span>
                    <span className={`meta-chip ${overdue ? "tone-danger" : ""}`}>
                      截止 {item.due_at ? formatDateTime(item.due_at) : "未设置"}
                    </span>
                    <span className="meta-chip">创建时间 {formatDateTime(item.created_at)}</span>
                    <span className="meta-chip">完成时间 {item.completed_at ? formatDateTime(item.completed_at) : "未完成"}</span>
                  </div>

                  {item.description || item.recommended_script || item.result_note ? (
                    <div className="summary-list">
                      {item.description ? (
                        <div className="summary-item">
                          <strong>任务说明</strong>
                          <p>{item.description}</p>
                        </div>
                      ) : null}
                      {item.recommended_script ? (
                        <div className="summary-item">
                          <strong>推荐话术</strong>
                          <blockquote>{item.recommended_script}</blockquote>
                        </div>
                      ) : null}
                      {item.result_note ? (
                        <div className="summary-item">
                          <strong>执行结果</strong>
                          <p>{item.result_note}</p>
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {isActiveTask(item) ? (
                    <div className="summary-list">
                      <div className="summary-item">
                        <strong>执行记录</strong>
                        <textarea
                          className="input-like textarea-like"
                          placeholder="补一条本次执行结果，任务完成时会自动回写为跟进记录。"
                          rows={3}
                          value={drafts[item.task_id]?.result_note || ""}
                          onChange={(event) => patchDraft(item.task_id, { result_note: event.target.value })}
                        />
                      </div>
                      <div className="meta-row">
                        <label className="meta-chip">
                          情绪
                          <select
                            className="input-like compact-input"
                            value={drafts[item.task_id]?.sentiment || "neutral"}
                            onChange={(event) =>
                              patchDraft(item.task_id, {
                                sentiment: event.target.value as TaskDraft["sentiment"]
                              })
                            }
                          >
                            <option value="positive">正向</option>
                            <option value="neutral">中性</option>
                            <option value="negative">负向</option>
                          </select>
                        </label>
                        <label className="meta-chip">
                          下次跟进
                          <input
                            className="input-like compact-input"
                            type="datetime-local"
                            value={drafts[item.task_id]?.next_follow_up_at || ""}
                            onChange={(event) => patchDraft(item.task_id, { next_follow_up_at: event.target.value })}
                          />
                        </label>
                      </div>

                      <div className="action-row">
                        {item.status === "pending" ? (
                          <button
                            className="button"
                            onClick={() => updateTask(item.task_id, "in_progress")}
                            type="button"
                            disabled={savingTaskId === item.task_id}
                          >
                            开始执行
                          </button>
                        ) : null}
                        <button
                          className="button"
                          onClick={() => updateTask(item.task_id, "completed")}
                          type="button"
                          disabled={savingTaskId === item.task_id}
                        >
                          标记完成
                        </button>
                        <button
                          className="ghost-button inline"
                          onClick={() => updateTask(item.task_id, "cancelled")}
                          type="button"
                          disabled={savingTaskId === item.task_id}
                        >
                          取消任务
                        </button>
                      </div>
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

export default function TasksPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <LoadingCard detail="正在同步销售任务、负责人和截止时间。" />
        </AppShell>
      }
    >
      <TasksPageContent />
    </Suspense>
  );
}
