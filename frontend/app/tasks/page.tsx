"use client";

import { useEffect, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

type Task = {
  task_id: string;
  customer_id: string;
  assignee_user_id: string;
  task_type: string;
  title: string;
  priority: string;
  status: string;
  due_at: string | null;
  created_at: string;
};

export default function TasksPage() {
  const [items, setItems] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadTasks() {
      try {
        const response = await apiFetch<Task[]>("/api/tasks");
        setItems(response.data);
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "任务列表加载失败");
      } finally {
        setLoading(false);
      }
    }
    loadTasks();
  }, []);

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Execution</p>
          <h1>销售任务</h1>
          <p className="lead">销售员在这里处理由主管确认后的跟进任务，确保 AI 建议真正进入执行闭环。</p>
        </div>
      </section>
      {error ? <ErrorCard message={error} /> : null}
      {loading ? <LoadingCard /> : null}
      {!loading && !items.length && !error ? <EmptyCard text="暂无销售任务。" /> : null}
      {items.length ? (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>客户</th>
                <th>负责人</th>
                <th>优先级</th>
                <th>状态</th>
                <th>截止时间</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.task_id}>
                  <td>{item.title}</td>
                  <td>{item.customer_id}</td>
                  <td>{item.assignee_user_id}</td>
                  <td>{item.priority}</td>
                  <td>
                    <span className="pill">{item.status}</span>
                  </td>
                  <td>{item.due_at ? new Date(item.due_at).toLocaleString("zh-CN") : "未设置"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </AppShell>
  );
}
