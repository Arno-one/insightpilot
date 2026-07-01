"use client";

import { useEffect, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

type RiskSnapshot = {
  risk_snapshot_id: string;
  customer_id: string;
  owner_user_id: string;
  risk_score: number;
  risk_level: string;
  llm_reason: string;
  llm_suggestion: string;
  status: string;
  created_at: string;
};

export default function RisksPage() {
  const [items, setItems] = useState<RiskSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadRisks() {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<RiskSnapshot[]>("/api/risk/snapshots");
      setItems(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "风险列表加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function triggerScan() {
    setMessage("");
    setError("");
    try {
      const response = await apiFetch<{ job_id: string }>("/api/risk/scan", { method: "POST" });
      setMessage(`风险扫描任务已提交：${response.data.job_id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "风险扫描提交失败，请确认 Redis/RQ 是否启动");
    }
  }

  useEffect(() => {
    loadRisks();
  }, []);

  return (
    <AppShell>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Risk center</p>
          <h1>客户风险中心</h1>
          <p className="lead">展示规则引擎识别出的风险分、AI 解释建议和待审批状态。</p>
        </div>
        <button className="button" onClick={triggerScan} type="button">
          触发风险扫描
        </button>
      </div>
      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} /> : null}
      {loading ? <LoadingCard /> : null}
      {!loading && !items.length && !error ? <EmptyCard text="暂无风险快照，请先触发风险扫描。" /> : null}
      {items.length ? (
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>客户</th>
                <th>风险</th>
                <th>状态</th>
                <th>原因</th>
                <th>建议</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.risk_snapshot_id}>
                  <td>{item.customer_id}</td>
                  <td>
                    <span className={`pill ${item.risk_level === "high" ? "pill-danger" : ""}`}>
                      {item.risk_level} · {item.risk_score}
                    </span>
                  </td>
                  <td>{item.status}</td>
                  <td>{item.llm_reason}</td>
                  <td>{item.llm_suggestion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </AppShell>
  );
}
