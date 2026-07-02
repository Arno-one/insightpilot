"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatDate, formatDateTime, getReportTypeLabel, getRiskMeta } from "@/lib/presentation";

type ReportType = "daily" | "weekly" | "monthly";

type TrendMetric = {
  current: number;
  previous: number;
  delta: number;
  direction: "up" | "down" | "flat" | string;
};

type OwnerSummaryItem = {
  owner_user_id: string;
  owner_user_name: string;
  total_customers: number;
  active_customers: number;
  high_risk_customers: number;
  active_tasks: number;
  overdue_tasks: number;
  open_deal_amount: number;
  won_current: number;
};

type RiskTopItem = {
  risk_snapshot_id: string;
  customer_id: string;
  customer_name: string | null;
  owner_user_id: string;
  owner_user_name: string | null;
  risk_score: number;
  risk_level: string;
  llm_reason: string | null;
  llm_suggestion: string | null;
  created_at: string;
};

type ReportMetrics = {
  report_type?: string;
  period_label?: string;
  period_start?: string;
  period_end?: string;
  previous_period_start?: string;
  previous_period_end?: string;
  totals?: {
    total_customers?: number;
    active_customers?: number;
    quotation_customers?: number;
    competitor_customers?: number;
    open_deals?: number;
    open_deal_amount?: number;
    quotation_deals?: number;
    high_risk_customers?: number;
    medium_risk_customers?: number;
    pending_approvals?: number;
    active_tasks?: number;
    overdue_tasks?: number;
  };
  trend_metrics?: {
    followups?: TrendMetric;
    won_deals?: TrendMetric;
    approved_approvals?: TrendMetric;
    completed_tasks?: TrendMetric;
  };
  owner_summary?: OwnerSummaryItem[];
  headline_numbers?: {
    followups_current?: number;
    won_current?: number;
    approved_current?: number;
    completed_current?: number;
  };
};

type Report = {
  report_id: string;
  report_type: string;
  report_date: string;
  summary: string;
  suggestions: string;
  created_by_user_id: string;
  created_by_user_name: string | null;
  created_at: string;
  metrics_json: ReportMetrics;
  risk_top_json: RiskTopItem[];
};

type ReportFilters = {
  reportType: "" | ReportType;
  dateFrom: string;
  dateTo: string;
};

const EMPTY_FILTERS: ReportFilters = {
  reportType: "",
  dateFrom: "",
  dateTo: "",
};

const GENERATE_TYPES: ReportType[] = ["daily", "weekly", "monthly"];

function buildQuery(customerId: string | null, filters: ReportFilters) {
  const params = new URLSearchParams();
  if (customerId) {
    params.set("customer_id", customerId);
  }
  if (filters.reportType) {
    params.set("report_type", filters.reportType);
  }
  if (filters.dateFrom) {
    params.set("date_from", filters.dateFrom);
  }
  if (filters.dateTo) {
    params.set("date_to", filters.dateTo);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function formatCurrency(value: number | null | undefined) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function formatSignedNumber(value: number | null | undefined) {
  const safeValue = value || 0;
  if (safeValue === 0) {
    return "持平";
  }
  return `${safeValue > 0 ? "+" : ""}${safeValue}`;
}

function periodText(metrics: ReportMetrics | undefined, reportDate: string) {
  if (metrics?.period_label) {
    return metrics.period_label;
  }
  return formatDate(reportDate);
}

function trendLabel(key: keyof NonNullable<ReportMetrics["trend_metrics"]>) {
  if (key === "followups") {
    return "跟进次数";
  }
  if (key === "won_deals") {
    return "赢单数量";
  }
  if (key === "approved_approvals") {
    return "审批通过数";
  }
  return "完成任务数";
}

function trendDirectionText(metric: TrendMetric | undefined) {
  if (!metric || metric.direction === "flat") {
    return "与上一周期持平";
  }
  return metric.direction === "up" ? "较上一周期上升" : "较上一周期回落";
}

function trendTone(metric: TrendMetric | undefined) {
  if (!metric || metric.direction === "flat") {
    return "tone-neutral";
  }
  return metric.direction === "up" ? "tone-success" : "tone-warning";
}

function reportCountLabel(customerFilter: string | null) {
  return customerFilter ? "关联报告" : "历史报告";
}

function ReportsPageContent() {
  const searchParams = useSearchParams();
  const customerFilter = searchParams.get("customerId");

  const [items, setItems] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submittingType, setSubmittingType] = useState<ReportType | "">("");
  const [draftFilters, setDraftFilters] = useState<ReportFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<ReportFilters>(EMPTY_FILTERS);

  useEffect(() => {
    let cancelled = false;

    async function loadReports() {
      setLoading(true);
      setError("");
      try {
        const response = await apiFetch<Report[]>(`/api/reports${buildQuery(customerFilter, filters)}`);
        if (!cancelled) {
          setItems(response.data);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "经营报告加载失败。");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadReports();
    return () => {
      cancelled = true;
    };
  }, [customerFilter, filters]);

  async function generateReport(reportType: ReportType) {
    setSubmittingType(reportType);
    setMessage("");
    setError("");
    try {
      const response = await apiFetch<{ job_id: string; report_type: string }>("/api/reports/generate", {
        method: "POST",
        body: JSON.stringify({ report_type: reportType }),
      });
      setMessage(`${getReportTypeLabel(reportType)}任务已提交，任务号：${response.data.job_id}。任务完成后可刷新列表查看结果。`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "报告任务提交失败，请确认 Redis/RQ 是否已启动。");
    } finally {
      setSubmittingType("");
    }
  }

  // 中文注释：摘要看板默认始终盯住当前筛选结果里的最新一份报告，保证管理层第一眼看到的是最新经营状态。
  const latestReport = useMemo(() => items[0], [items]);
  const latestMetrics = latestReport?.metrics_json;
  const latestTotals = latestMetrics?.totals;
  const latestHeadline = latestMetrics?.headline_numbers;
  const latestTrends = latestMetrics?.trend_metrics;
  const latestOwners = latestMetrics?.owner_summary || [];
  const latestRiskTop = latestReport?.risk_top_json || [];

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Executive Brief Upgrade</p>
          <h1>把周报、月报、趋势指标和归属人视角压缩成一块能直接读懂经营节奏的摘要看板。</h1>
          <p className="lead">
            当前版本先聚焦“轻操作、强聚合”的 V1：上层看摘要和趋势，下层再看风险上下文与历史报告流。
            {customerFilter ? ` 当前已按客户 ${customerFilter} 做钻取。` : ""}
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
          {GENERATE_TYPES.map((reportType) => (
            <button
              className={submittingType === reportType ? "button-secondary" : "button"}
              disabled={Boolean(submittingType)}
              key={reportType}
              onClick={() => generateReport(reportType)}
              type="button"
            >
              {submittingType === reportType ? `提交${getReportTypeLabel(reportType)}中...` : `生成${getReportTypeLabel(reportType)}`}
            </button>
          ))}
          <button className="button-secondary" onClick={() => setFilters({ ...filters })} type="button">
            刷新当前结果
          </button>
        </div>
      </section>

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard detail="如果生成失败，请优先检查 Worker、Redis 与经营报告任务链路。" message={error} /> : null}
      {loading ? <LoadingCard detail="正在拉取周报、月报、趋势指标与归属人摘要。" /> : null}

      <section className="command-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Report Filters</p>
            <h2>报告筛选与查看范围</h2>
            <p className="panel-copy">先用类型和时间范围锁定管理视角，再下钻看最新摘要、趋势变化和责任人状态。</p>
          </div>
        </div>
        <div className="eval-control-bar">
          <label>
            报告类型
            <select
              className="input-like compact-input"
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, reportType: event.target.value as ReportFilters["reportType"] }))
              }
              value={draftFilters.reportType}
            >
              <option value="">全部类型</option>
              <option value="daily">日报</option>
              <option value="weekly">周报</option>
              <option value="monthly">月报</option>
            </select>
          </label>
          <label>
            开始日期
            <input
              onChange={(event) => setDraftFilters((current) => ({ ...current, dateFrom: event.target.value }))}
              type="date"
              value={draftFilters.dateFrom}
            />
          </label>
          <label>
            结束日期
            <input
              onChange={(event) => setDraftFilters((current) => ({ ...current, dateTo: event.target.value }))}
              type="date"
              value={draftFilters.dateTo}
            />
          </label>
          <label>
            当前聚焦
            <div className="input-like compact-input" style={{ display: "flex", alignItems: "center" }}>
              {customerFilter ? `客户 ${customerFilter}` : "全局经营视角"}
            </div>
          </label>
        </div>
        <div className="page-actions">
          <button className="button" onClick={() => setFilters({ ...draftFilters })} type="button">
            应用筛选
          </button>
          <button
            className="button-secondary"
            onClick={() => {
              setDraftFilters(EMPTY_FILTERS);
              setFilters(EMPTY_FILTERS);
            }}
            type="button"
          >
            重置筛选
          </button>
        </div>
      </section>

      {!loading && !items.length && !error ? (
        <EmptyCard
          detail={customerFilter ? "当前客户还没有进入已生成经营报告的引用范围。" : "建议先生成一轮周报或月报，再回来查看趋势与归属人摘要。"}
          text={customerFilter ? "当前客户还没有匹配到经营报告。" : "当前还没有经营报告。"}
        />
      ) : null}

      {items.length ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{items.length}</strong>
              <span className="metric-label">{reportCountLabel(customerFilter)}</span>
              <p className="metric-detail">当前筛选结果里一共命中了多少份报告，方便快速判断经营复盘的时间覆盖度。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{getReportTypeLabel(latestReport?.report_type || "daily")}</strong>
              <span className="metric-label">最新报告类型</span>
              <p className="metric-detail">当前摘要看板默认读取最新一份报告，周报、月报和日报会走同一套聚合口径。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{periodText(latestMetrics, latestReport?.report_date || "")}</strong>
              <span className="metric-label">当前观察周期</span>
              <p className="metric-detail">同一张卡里统一展示周期标签，避免老板在日报、周报和月报间切换时重新理解时间口径。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{formatCurrency(latestTotals?.open_deal_amount)}</strong>
              <span className="metric-label">开放商机金额</span>
              <p className="metric-detail">用一张卡先看盘子大小，判断当前经营机会池是否足够支撑后续成交节奏。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{latestTotals?.high_risk_customers || 0}</strong>
              <span className="metric-label">高风险客户</span>
              <p className="metric-detail">风险客户数量直接影响管理层的关注重心，也是后续审批和任务压力的前置指标。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{latestTotals?.pending_approvals || 0}</strong>
              <span className="metric-label">待审批事项</span>
              <p className="metric-detail">审批积压过多会拖慢执行闭环，所以这张卡帮助主管判断是否需要优先清队列。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{latestTotals?.overdue_tasks || 0}</strong>
              <span className="metric-label">逾期任务</span>
              <p className="metric-detail">如果逾期任务抬头，就说明风险和建议没有顺利落地到执行动作，需要马上追踪责任人。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{latestOwners.length}</strong>
              <span className="metric-label">归属人样本</span>
              <p className="metric-detail">当前版本先展示最需要管理层关注的前几位负责人，让问题聚焦到可行动的人和客户盘子上。</p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Latest Brief</p>
                  <h2>{customerFilter ? "该客户相关报告里的最新摘要" : "最新一份报告的管理层摘要"}</h2>
                </div>
                <div className="report-meta">
                  <span className="meta-chip">{getReportTypeLabel(latestReport.report_type)}</span>
                  <span className="meta-chip">周期 {periodText(latestMetrics, latestReport.report_date)}</span>
                  <span className="meta-chip">生成于 {formatDateTime(latestReport.created_at)}</span>
                </div>
              </div>
              <div className="summary-list">
                <div className="summary-item">
                  <strong>经营摘要</strong>
                  <p>{latestReport.summary}</p>
                </div>
                <div className="summary-item">
                  <strong>行动建议</strong>
                  <p>{latestReport.suggestions}</p>
                </div>
              </div>
              <div className="highlight-strip">
                <div className="highlight-card">
                  <strong>{latestHeadline?.followups_current || 0}</strong>
                  <span>本周期跟进次数</span>
                </div>
                <div className="highlight-card">
                  <strong>{latestHeadline?.won_current || 0}</strong>
                  <span>本周期赢单数</span>
                </div>
                <div className="highlight-card">
                  <strong>{latestHeadline?.completed_current || 0}</strong>
                  <span>本周期完成任务数</span>
                </div>
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Risk Context</p>
                  <h2>风险快照上下文</h2>
                  <p className="panel-copy">经营报告不是孤立文本，它要能回到具体客户和负责人，帮助团队决定先盯谁、先处理什么。</p>
                </div>
              </div>
              <div className="summary-list">
                {latestRiskTop.length ? (
                  latestRiskTop.map((item) => {
                    const riskMeta = getRiskMeta(item.risk_level);
                    return (
                      <div className="summary-item" key={item.risk_snapshot_id}>
                        <strong>{item.customer_name || item.customer_id}</strong>
                        <div className="report-meta">
                          <span className={`meta-chip ${riskMeta.toneClass}`}>{riskMeta.label}</span>
                          <span className="meta-chip">风险分 {item.risk_score}</span>
                          <span className="meta-chip">负责人 {item.owner_user_name || item.owner_user_id}</span>
                          <span className="meta-chip">快照时间 {formatDateTime(item.created_at)}</span>
                        </div>
                        <p>{item.llm_reason || "当前没有补充风险原因。"}</p>
                        <p>{item.llm_suggestion || "当前没有补充动作建议。"}</p>
                        <div className="page-actions">
                          <Link className="button-secondary" href={`/customers/${item.customer_id}`}>
                            查看客户详情
                          </Link>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="summary-item">
                    <strong>当前没有重点风险客户</strong>
                    <p>说明最新一份报告暂时没有拉起高优先级风险上下文，可以把注意力更多放在趋势和责任人分布上。</p>
                  </div>
                )}
              </div>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Trend Metrics</p>
                  <h2>当前周期相对上一周期的变化</h2>
                </div>
              </div>
              <div className="highlight-strip">
                {([
                  "followups",
                  "won_deals",
                  "approved_approvals",
                  "completed_tasks",
                ] as Array<keyof NonNullable<ReportMetrics["trend_metrics"]>>).map((key) => {
                  const metric = latestTrends?.[key];
                  return (
                    <div className="highlight-card" key={key}>
                      <strong>{metric?.current || 0}</strong>
                      <span>{trendLabel(key)}</span>
                      <span className={trendTone(metric)}>
                        {trendDirectionText(metric)}，变化 {formatSignedNumber(metric?.delta || 0)}
                      </span>
                      <span>上一周期 {metric?.previous || 0}</span>
                    </div>
                  );
                })}
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Reading Guide</p>
                  <h2>这块摘要看板要回答什么问题</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>先看盘子，再看节奏</strong>
                  <p>顶部卡片告诉我们当前客户盘子、机会金额和风险压力，趋势区再补充本周期是否在往更好的方向走。</p>
                </div>
                <div className="detail-item">
                  <strong>先看责任人，再看客户列表</strong>
                  <p>如果问题已经明显集中到某位负责人，就优先用归属人视角推进，而不是直接淹没在长列表里。</p>
                </div>
                <div className="detail-item">
                  <strong>先看摘要，再看上下文</strong>
                  <p>先用一段摘要和建议快速形成判断，再去风险快照和历史报告里核对证据，管理阅读路径会更顺。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="system-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Owner View</p>
                  <h2>归属人视角</h2>
                  <p className="panel-copy">先展示需要被重点关注的负责人，把客户盘子、风险客户和任务执行压力放到一个维度里看。</p>
                </div>
              </div>
              <div className="summary-list">
                {latestOwners.length ? (
                  latestOwners.map((owner) => (
                    <div className="summary-item" key={owner.owner_user_id}>
                      <strong>{owner.owner_user_name}</strong>
                      <div className="report-meta">
                        <span className="meta-chip">客户总数 {owner.total_customers}</span>
                        <span className="meta-chip">活跃客户 {owner.active_customers}</span>
                        <span className={`meta-chip ${owner.high_risk_customers ? "tone-danger" : ""}`}>
                          高风险客户 {owner.high_risk_customers}
                        </span>
                        <span className={`meta-chip ${owner.overdue_tasks ? "tone-warning" : ""}`}>
                          逾期任务 {owner.overdue_tasks}
                        </span>
                      </div>
                      <div className="highlight-strip">
                        <div className="highlight-card">
                          <strong>{owner.active_tasks}</strong>
                          <span>当前执行中的任务</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{formatCurrency(owner.open_deal_amount)}</strong>
                          <span>开放商机金额</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{owner.won_current}</strong>
                          <span>本周期赢单数</span>
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="summary-item">
                    <strong>当前没有归属人聚合结果</strong>
                    <p>通常说明当前租户还没有足够的客户、任务或商机数据，建议先补充样本再看管理视角。</p>
                  </div>
                )}
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Period Scope</p>
                  <h2>本期与上期口径</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>当前周期</strong>
                  <p>
                    {latestMetrics?.period_start ? formatDate(latestMetrics.period_start) : "未记录"} 到{" "}
                    {latestMetrics?.period_end ? formatDate(latestMetrics.period_end) : "未记录"}
                  </p>
                </div>
                <div className="detail-item">
                  <strong>上一周期</strong>
                  <p>
                    {latestMetrics?.previous_period_start ? formatDate(latestMetrics.previous_period_start) : "未记录"} 到{" "}
                    {latestMetrics?.previous_period_end ? formatDate(latestMetrics.previous_period_end) : "未记录"}
                  </p>
                </div>
                <div className="detail-item">
                  <strong>看板解释</strong>
                  <p>日报按天对比昨天，周报按自然周对比上周，月报按自然月对比上月，先把比较口径讲清楚，趋势判断才不会跑偏。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="report-feed">
            {items.map((item) => {
              const metrics = item.metrics_json || {};
              const totals = metrics.totals || {};
              const headline = metrics.headline_numbers || {};
              return (
                <article className="report-card" key={item.report_id}>
                  <div className="report-card-header">
                    <div>
                      <p className="eyebrow">{getReportTypeLabel(item.report_type)}</p>
                      <h2 className="report-title">{periodText(metrics, item.report_date)}</h2>
                    </div>
                    <div className="report-meta">
                      <span className="meta-chip">报告编号 {item.report_id}</span>
                      <span className="meta-chip">归属人 {item.created_by_user_name || item.created_by_user_id}</span>
                      <span className="meta-chip">报告日期 {formatDate(item.report_date)}</span>
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

                  <div className="highlight-strip">
                    <div className="highlight-card">
                      <strong>{headline.followups_current || 0}</strong>
                      <span>本周期跟进次数</span>
                    </div>
                    <div className="highlight-card">
                      <strong>{headline.won_current || 0}</strong>
                      <span>本周期赢单数</span>
                    </div>
                    <div className="highlight-card">
                      <strong>{totals.high_risk_customers || 0}</strong>
                      <span>高风险客户数</span>
                    </div>
                  </div>

                  <div className="report-meta">
                    <span className="meta-chip">开放商机金额 {formatCurrency(totals.open_deal_amount)}</span>
                    <span className="meta-chip">待审批 {totals.pending_approvals || 0}</span>
                    <span className="meta-chip">活跃任务 {totals.active_tasks || 0}</span>
                    <span className="meta-chip">逾期任务 {totals.overdue_tasks || 0}</span>
                    <span className="meta-chip">重点风险客户 {item.risk_top_json?.length || 0}</span>
                  </div>
                </article>
              );
            })}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}

export default function ReportsPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <LoadingCard detail="正在拉取经营报告看板。" />
        </AppShell>
      }
    >
      <ReportsPageContent />
    </Suspense>
  );
}
