"use client";

import { useEffect, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

type Report = {
  report_id: string;
  report_type: string;
  report_date: string;
  summary: string;
  suggestions: string;
  created_at: string;
};

export default function ReportsPage() {
  const [items, setItems] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadReports() {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<Report[]>("/api/reports");
      setItems(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "经营报告加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function generateReport() {
    setMessage("");
    setError("");
    try {
      const response = await apiFetch<{ job_id: string }>("/api/reports/daily/generate", { method: "POST" });
      setMessage(`经营日报任务已提交：${response.data.job_id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "日报任务提交失败，请确认 Redis/RQ 是否启动");
    }
  }

  useEffect(() => {
    loadReports();
  }, []);

  return (
    <AppShell>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Reports</p>
          <h1>经营报告</h1>
          <p className="lead">日报会把指标、风险和建议动作组织成老板能快速读懂的摘要。</p>
        </div>
        <button className="button" onClick={generateReport} type="button">
          生成日报
        </button>
      </div>
      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} /> : null}
      {loading ? <LoadingCard /> : null}
      {!loading && !items.length && !error ? <EmptyCard text="暂无经营报告。" /> : null}
      <div className="stack">
        {items.map((item) => (
          <article className="report-card" key={item.report_id}>
            <div className="report-date">
              <span>{item.report_type}</span>
              <strong>{item.report_date}</strong>
            </div>
            <div>
              <h2>{item.summary}</h2>
              <p>{item.suggestions}</p>
            </div>
          </article>
        ))}
      </div>
    </AppShell>
  );
}
