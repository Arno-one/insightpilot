"use client";

import { useEffect, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

type AgentRun = {
  run_id: string;
  user_id: string;
  run_type: string;
  graph_name: string;
  status: string;
  total_duration_ms: number;
  started_at: string | null;
  finished_at: string | null;
};

export default function AgentTracePage() {
  const [items, setItems] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadRuns() {
      try {
        const response = await apiFetch<AgentRun[]>("/api/agent/runs");
        setItems(response.data);
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Agent 执行记录加载失败");
      } finally {
        setLoading(false);
      }
    }
    loadRuns();
  }, []);

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Trace</p>
          <h1>Agent 执行追踪</h1>
          <p className="lead">这里展示 Agent Run、图名称、执行状态和耗时；节点级 Step 详情将在下一版接入。</p>
        </div>
      </section>
      {error ? <ErrorCard message={error} /> : null}
      {loading ? <LoadingCard /> : null}
      {!loading && !items.length && !error ? <EmptyCard text="暂无 Agent 执行记录。" /> : null}
      {items.length ? (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>类型</th>
                <th>图</th>
                <th>状态</th>
                <th>耗时</th>
                <th>触发人</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.run_id}>
                  <td>{item.run_id}</td>
                  <td>{item.run_type}</td>
                  <td>{item.graph_name}</td>
                  <td>
                    <span className="pill">{item.status}</span>
                  </td>
                  <td>{item.total_duration_ms} ms</td>
                  <td>{item.user_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </AppShell>
  );
}
