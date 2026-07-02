"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useDeferredValue, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch, getStoredUser, hasAnyPermission } from "@/lib/api";
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

type BatchTaskDraft = {
  result_note: string;
  sentiment: "positive" | "neutral" | "negative";
  next_follow_up_at: string;
  assignee_user_id: string;
};

type TaskFilters = {
  status: string;
  priority: string;
  assigneeKeyword: string;
  overdueOnly: boolean;
};

type AssigneeOption = {
  user_id: string;
  username: string;
  real_name: string | null;
  role_codes: string[];
  role_names: string[];
};

type TaskBatchFailureItem = {
  task_id: string;
  message: string;
};

type TaskBatchResult = {
  actionLabel: string;
  successCount: number;
  failedCount: number;
  failedItems: TaskBatchFailureItem[];
};

const EMPTY_TASK_DRAFT: TaskDraft = {
  result_note: "",
  sentiment: "neutral",
  next_follow_up_at: ""
};

const EMPTY_BATCH_DRAFT: BatchTaskDraft = {
  result_note: "",
  sentiment: "neutral",
  next_follow_up_at: "",
  assignee_user_id: ""
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
  const canManageAssignment = useMemo(
    () => hasAnyPermission(currentUser, ["task:read:team", "task:read:all"]),
    [currentUser]
  );
  const [items, setItems] = useState<Task[]>([]);
  const [assignees, setAssignees] = useState<AssigneeOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingAssignees, setLoadingAssignees] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingTaskId, setSavingTaskId] = useState("");
  const [batchAction, setBatchAction] = useState<"" | "in_progress" | "completed" | "cancelled" | "assignee">("");
  const [batchResult, setBatchResult] = useState<TaskBatchResult | null>(null);
  const [drafts, setDrafts] = useState<Record<string, TaskDraft>>({});
  const [batchDraft, setBatchDraft] = useState<BatchTaskDraft>(EMPTY_BATCH_DRAFT);
  const [assigneeKeyword, setAssigneeKeyword] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [filters, setFilters] = useState<TaskFilters>(EMPTY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<TaskFilters>(EMPTY_FILTERS);
  const [quickView, setQuickView] = useState<"all" | "pending" | "overdue" | "highPriorityOpen" | "mine">("all");
  const deferredAssigneeKeyword = useDeferredValue(assigneeKeyword);

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

  async function loadAssignees() {
    if (!canManageAssignment) {
      setAssignees([]);
      return;
    }
    setLoadingAssignees(true);
    try {
      const query = new URLSearchParams();
      if (deferredAssigneeKeyword.trim()) {
        query.set("keyword", deferredAssigneeKeyword.trim());
      }
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const response = await apiFetch<AssigneeOption[]>(`/api/tasks/assignees${suffix}`);
      setAssignees(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "负责人列表加载失败。");
    } finally {
      setLoadingAssignees(false);
    }
  }

  async function updateTask(taskId: string, status: "in_progress" | "completed" | "cancelled") {
    const draft = drafts[taskId] || EMPTY_TASK_DRAFT;
    setSavingTaskId(taskId);
    setError("");
    setMessage("");
    setBatchResult(null);
    try {
      const response = await apiFetch(`/api/tasks/${taskId}/status`, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          result_note:
            draft.result_note ||
            (status === "cancelled"
              ? "前端手动取消该任务"
              : status === "completed"
                ? "前端标记该任务完成"
                : "任务已开始推进"),
          sentiment: draft.sentiment,
          next_follow_up_at: draft.next_follow_up_at || null
        })
      });
      setMessage(response.msg);
      await loadTasks();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "任务状态更新失败。");
    } finally {
      setSavingTaskId("");
    }
  }

  async function batchUpdateTasks(status: "in_progress" | "completed" | "cancelled") {
    if (!selectedIds.length) {
      return;
    }
    setBatchAction(status);
    setError("");
    setMessage("");
    setBatchResult(null);
    try {
      const response = await apiFetch<{
        items: Array<{ task_id: string; status: string; unchanged: boolean }>;
        failed_items: TaskBatchFailureItem[];
        success_count: number;
        failed_count: number;
      }>("/api/tasks/batch/status", {
        method: "PATCH",
        body: JSON.stringify({
          task_ids: selectedIds,
          status,
          result_note:
            batchDraft.result_note ||
            (status === "cancelled"
              ? "前端批量取消任务"
              : status === "completed"
                ? "前端批量标记任务完成"
                : "前端批量开始推进任务"),
          sentiment: batchDraft.sentiment,
          next_follow_up_at: batchDraft.next_follow_up_at || null
        })
      });
      setMessage(response.msg);
      setBatchResult({
        actionLabel:
          status === "in_progress" ? "批量开始执行" : status === "completed" ? "批量标记完成" : "批量取消任务",
        successCount: response.data.success_count,
        failedCount: response.data.failed_count,
        failedItems: response.data.failed_items
      });
      setSelectedIds([]);
      await loadTasks();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "批量更新任务状态失败。");
    } finally {
      setBatchAction("");
    }
  }

  async function batchAssignTasks() {
    if (!selectedIds.length || !batchDraft.assignee_user_id) {
      return;
    }
    setBatchAction("assignee");
    setError("");
    setMessage("");
    setBatchResult(null);
    try {
      const response = await apiFetch<{
        items: Array<{ task_id: string; assignee_user_id: string; unchanged: boolean }>;
        failed_items: TaskBatchFailureItem[];
        success_count: number;
        failed_count: number;
      }>("/api/tasks/batch/assignee", {
        method: "PATCH",
        body: JSON.stringify({
          task_ids: selectedIds,
          assignee_user_id: batchDraft.assignee_user_id
        })
      });
      setMessage(response.msg);
      setBatchResult({
        actionLabel: "批量分配负责人",
        successCount: response.data.success_count,
        failedCount: response.data.failed_count,
        failedItems: response.data.failed_items
      });
      setSelectedIds([]);
      setBatchDraft((current) => ({ ...current, assignee_user_id: "" }));
      await loadTasks();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "批量分配负责人失败。");
    } finally {
      setBatchAction("");
    }
  }

  useEffect(() => {
    loadTasks();
  }, [customerFilter, filters]);

  useEffect(() => {
    loadAssignees();
  }, [canManageAssignment, deferredAssigneeKeyword]);

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
    // 中文注释：先按截止时间排，让“快到期”和“已逾期”的任务自然浮到前面。
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

  const selectableIds = useMemo(
    () => sortedItems.filter(isActiveTask).map((item) => item.task_id),
    [sortedItems]
  );

  useEffect(() => {
    const selectableIdSet = new Set(selectableIds);
    setSelectedIds((current) => {
      const next = current.filter((id) => selectableIdSet.has(id));
      return next.length === current.length ? current : next;
    });
  }, [selectableIds]);

  const allSelectableChecked = selectableIds.length > 0 && selectableIds.every((taskId) => selectedIds.includes(taskId));
  const activeCount = sortedItems.filter(isActiveTask).length;
  const inProgressCount = sortedItems.filter((item) => item.status === "in_progress").length;
  const completedCount = sortedItems.filter((item) => item.status === "completed").length;
  const overdueCount = sortedItems.filter(isOverdueTask).length;

  function toggleSelected(taskId: string) {
    setSelectedIds((current) => (current.includes(taskId) ? current.filter((id) => id !== taskId) : [...current, taskId]));
  }

  function toggleAllSelectable() {
    setSelectedIds(allSelectableChecked ? [] : selectableIds);
  }

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
      {error ? <ErrorCard message={error} detail="请确认任务接口、权限与后端服务是否运行正常。" /> : null}
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
              <button className={quickView === "pending" ? "button" : "button-secondary"} onClick={() => setQuickView("pending")} type="button">
                待跟进
              </button>
              <button className={quickView === "overdue" ? "button" : "button-secondary"} onClick={() => setQuickView("overdue")} type="button">
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
                我负责的
              </button>
            </div>
          </section>

          {selectableIds.length ? (
            <section className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Batch Action</p>
                  <h2>批量推进工具条</h2>
                </div>
                <span className="meta-chip">当前选中 {selectedIds.length} / {selectableIds.length}</span>
              </div>
              <div className="summary-list">
                <div className="summary-item">
                  <strong>批量执行备注</strong>
                  <textarea
                    className="input-like textarea-like"
                    placeholder="批量完成时会自动把备注回写到跟进记录；开始执行或取消时则会写入任务留痕。"
                    rows={3}
                    value={batchDraft.result_note}
                    onChange={(event) => setBatchDraft((current) => ({ ...current, result_note: event.target.value }))}
                  />
                </div>
              </div>
              <div className="meta-row">
                <label className="meta-chip">
                  情绪
                  <select
                    className="input-like compact-input"
                    value={batchDraft.sentiment}
                    onChange={(event) =>
                      setBatchDraft((current) => ({
                        ...current,
                        sentiment: event.target.value as BatchTaskDraft["sentiment"]
                      }))
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
                    value={batchDraft.next_follow_up_at}
                    onChange={(event) =>
                      setBatchDraft((current) => ({ ...current, next_follow_up_at: event.target.value }))
                    }
                  />
                </label>
              </div>
              <div className="page-actions">
                <button className="button-secondary" onClick={toggleAllSelectable} type="button">
                  {allSelectableChecked ? "清空当前页选择" : "全选当前页可操作任务"}
                </button>
                <button className="button-secondary" onClick={() => setSelectedIds([])} type="button" disabled={!selectedIds.length}>
                  清空选择
                </button>
                <button
                  className="button"
                  onClick={() => batchUpdateTasks("in_progress")}
                  type="button"
                  disabled={!selectedIds.length || Boolean(batchAction)}
                >
                  {batchAction === "in_progress" ? "批量开始中..." : "批量开始执行"}
                </button>
                <button
                  className="button"
                  onClick={() => batchUpdateTasks("completed")}
                  type="button"
                  disabled={!selectedIds.length || Boolean(batchAction)}
                >
                  {batchAction === "completed" ? "批量完成中..." : "批量标记完成"}
                </button>
                <button
                  className="ghost-button inline"
                  onClick={() => batchUpdateTasks("cancelled")}
                  type="button"
                  disabled={!selectedIds.length || Boolean(batchAction)}
                >
                  {batchAction === "cancelled" ? "批量取消中..." : "批量取消任务"}
                </button>
              </div>
              {canManageAssignment ? (
                <div className="summary-list">
                  <div className="summary-item">
                    <strong>负责人筛选</strong>
                    <p>当前版本先按在职且具备 `owner / manager / salesperson` 角色的用户作为可分配负责人候选。</p>
                  </div>
                  <div className="summary-item">
                    <input
                      className="input-like"
                      placeholder="按负责人姓名、用户名或用户 ID 筛选"
                      value={assigneeKeyword}
                      onChange={(event) => setAssigneeKeyword(event.target.value)}
                    />
                  </div>
                </div>
              ) : (
                <p className="lead">当前账号仅具备个人任务视图权限，所以这里不展示批量分配负责人能力。</p>
              )}
              {canManageAssignment ? (
                <div className="page-actions">
                  <select
                    className="input-like compact-input"
                    value={batchDraft.assignee_user_id}
                    onChange={(event) =>
                      setBatchDraft((current) => ({ ...current, assignee_user_id: event.target.value }))
                    }
                    disabled={loadingAssignees || Boolean(batchAction)}
                  >
                    <option value="">{loadingAssignees ? "正在加载负责人..." : "选择新的负责人"}</option>
                    {assignees.map((assignee) => (
                      <option key={assignee.user_id} value={assignee.user_id}>
                        {(assignee.real_name || assignee.username) +
                          ` (${assignee.user_id})` +
                          (assignee.role_names.length ? ` - ${assignee.role_names.join(" / ")}` : "")}
                      </option>
                    ))}
                  </select>
                  <button
                    className="button-secondary"
                    onClick={batchAssignTasks}
                    type="button"
                    disabled={!selectedIds.length || !batchDraft.assignee_user_id || Boolean(batchAction)}
                  >
                    {batchAction === "assignee" ? "分配中..." : "批量分配负责人"}
                  </button>
                </div>
              ) : null}
              {canManageAssignment && !loadingAssignees && !assignees.length ? (
                <p className="lead">当前筛选条件下没有可分配负责人，请调整关键词后重试。</p>
              ) : null}
            </section>
          ) : null}

          {batchResult ? (
            <section className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Batch Result</p>
                  <h2>上次批量任务操作结果</h2>
                </div>
                <span className="meta-chip">
                  {batchResult.actionLabel}：成功 {batchResult.successCount} 条，失败 {batchResult.failedCount} 条
                </span>
              </div>
              {batchResult.failedItems.length ? (
                <div className="detail-list">
                  {batchResult.failedItems.map((item) => (
                    <div className="detail-item" key={`${item.task_id}-${item.message}`}>
                      <strong>任务 {item.task_id}</strong>
                      <p>{item.message}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="lead">本次批量任务操作没有失败项，可以继续推进下一批任务。</p>
              )}
            </section>
          ) : null}

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
              const checked = selectedIds.includes(item.task_id);

              return (
                <article className="task-card" key={item.task_id}>
                  <div className="task-card-header">
                    <div>
                      <p className="eyebrow">{item.task_type}</p>
                      <h2 className="section-title">{item.title}</h2>
                      <p className="lead">{item.customer_name || item.customer_id}</p>
                    </div>
                    <div className="task-meta">
                      {isActiveTask(item) ? (
                        <label className="meta-chip">
                          <input type="checkbox" checked={checked} onChange={() => toggleSelected(item.task_id)} />
                          批量选择
                        </label>
                      ) : null}
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
                            disabled={savingTaskId === item.task_id || Boolean(batchAction)}
                          >
                            {savingTaskId === item.task_id ? "处理中..." : "开始执行"}
                          </button>
                        ) : null}
                        <button
                          className="button"
                          onClick={() => updateTask(item.task_id, "completed")}
                          type="button"
                          disabled={savingTaskId === item.task_id || Boolean(batchAction)}
                        >
                          {savingTaskId === item.task_id ? "处理中..." : "标记完成"}
                        </button>
                        <button
                          className="ghost-button inline"
                          onClick={() => updateTask(item.task_id, "cancelled")}
                          type="button"
                          disabled={savingTaskId === item.task_id || Boolean(batchAction)}
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
