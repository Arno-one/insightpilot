"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDate, formatDateTime, getReportTypeLabel } from "@/lib/presentation";

type Report = {
  report_id: string;
  report_type: string;
  report_date: string;
  summary: string;
  suggestions: string;
  created_by_user_id: string;
  created_by_user_name: string | null;
  created_at: string;
};

function ReportsPageContent() {
  const searchParams = useSearchParams();
  const customerFilter = searchParams.get("customerId");

  const [items, setItems] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadReports() {
    setLoading(true);
    setError("");
    try {
      const query = customerFilter ? `?customer_id=${encodeURIComponent(customerFilter)}` : "";
      const response = await apiFetch<Report[]>(`/api/reports${query}`);
      setItems(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "经营报告加载失败。");
    } finally {
      setLoading(false);
    }
  }

  async function generateReport() {
    setMessage("");
    setError("");
    try {
      const response = await apiFetch<{ job_id: string }>("/api/reports/daily/generate", { method: "POST" });
      setMessage(`经营日报任务已提交，任务号：${response.data.job_id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "日报任务提交失败，请确认 Redis/RQ 是否已启动。");
    }
  }

  useEffect(() => {
    loadReports();
  }, [customerFilter]);

  // 中文注释：默认把最新报告抬到最上面，先满足老板和主管“今天发生了什么”的阅读路径。
  const latestReport = useMemo(() => items[0], [items]);

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Executive Brief</p>
          <h1>把风险、审批和执行压缩成一份老板能在几分钟内读完的简报。</h1>
          <p className="lead">
            日报不是流水账，它应该帮助管理层快速看到风险重心、执行节奏与下一步经营动作。
            {customerFilter ? ` 当前已聚焦客户 ${customerFilter}。` : ""}
          </p>
        </div>
        <div className="page-actions">
          {customerFilter ? (
            <>
              <Link className="button-secondary" href={`/customers/${customerFilter}`}>
                返回客户详情
              </Link>
              <Link className="ghost-button inline" href="/reports">
                查看全部报告
              </Link>
            </>
          ) : null}
          <button className="button" onClick={generateReport} type="button">
            生成最新日报
          </button>
          <button className="button-secondary" onClick={loadReports} type="button">
            刷新报告列表
          </button>
        </div>
      </section>

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} detail="如果生成失败，请优先检查 Worker、Redis 与经营日报任务链路。" /> : null}
      {loading ? <LoadingCard detail="正在拉取历史日报与经营摘要。" /> : null}
      {!loading && !items.length && !error ? (
        <EmptyCard
          text={customerFilter ? "当前客户还没有被经营报告引用。" : "当前还没有经营报告。"}
          detail={customerFilter ? "这通常说明该客户还没进入最近几期的重点风险客户名单。" : "建议先完成一轮风险扫描，再生成日报，内容会更完整。"}
        />
      ) : null}

      {items.length ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{items.length}</strong>
              <span className="metric-label">{customerFilter ? "关联报告" : "累计报告"}</span>
              <p className="metric-detail">{customerFilter ? "当前客户最近被哪些经营报告提及，一眼就能看出来。" : "可以快速展示系统已经具备持续输出经营简报的能力。"}</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{formatDate(latestReport?.report_date)}</strong>
              <span className="metric-label">最近报告日期</span>
              <p className="metric-detail">默认按最新时间优先展示，方便老板快速切入今天的情况。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{getReportTypeLabel(latestReport?.report_type || "daily")}</strong>
              <span className="metric-label">最新报告类型</span>
              <p className="metric-detail">当前版本以日报为主，后续可以扩到周报和趋势报表。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{latestReport ? "已同步" : "待生成"}</strong>
              <span className="metric-label">今日态势</span>
              <p className="metric-detail">{customerFilter ? "可以快速确认这个客户是否持续出现在管理层视角里。" : "生成成功后，建议同时去 Trace 页面核验执行链路。"}</p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Latest Summary</p>
                  <h2>{customerFilter ? "这位客户最近一次被报告提到的内容" : "最新一份报告最值得看的内容"}</h2>
                </div>
              </div>
              <div className="summary-item">
                <strong>{latestReport?.summary}</strong>
                <p>{latestReport?.suggestions}</p>
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Report Standard</p>
                  <h2>一份好日报应该做到什么</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>不只是汇总指标</strong>
                  <p>日报的价值在于把指标变化转成“为什么会这样”和“今天该做什么”。</p>
                </div>
                <div className="detail-item">
                  <strong>必须能承接前面的风险与任务</strong>
                  <p>如果前面看不到风险来源、后面看不到任务去向，日报就只剩排版价值，没有经营价值。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="report-feed">
            {items.map((item) => (
              <article className="report-card" key={item.report_id}>
                <div className="report-card-header">
                  <div>
                    <p className="eyebrow">{getReportTypeLabel(item.report_type)}</p>
                    <h2 className="report-title">{formatDate(item.report_date)}</h2>
                  </div>
                  <div className="report-meta">
                    <span className="meta-chip">报告编号 {item.report_id}</span>
                    <span className="meta-chip">归属人 {item.created_by_user_name || item.created_by_user_id}</span>
                    <span className="meta-chip">生成时间 {formatDateTime(item.created_at)}</span>
                  </div>
                </div>

                <div className="summary-list">
                  <div className="summary-item">
                    <strong>经营摘要</strong>
                    <p>{item.summary}</p>
                  </div>
                  <div className="summary-item">
                    <strong>行动建议</strong>
                    <p>{item.suggestions}</p>
                  </div>
                </div>
              </article>
            ))}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}

export default function ReportsPage() {
  return (
    <Suspense fallback={<AppShell><LoadingCard detail="正在拉取历史日报与经营摘要。" /></AppShell>}>
      <ReportsPageContent />
    </Suspense>
  );
}
