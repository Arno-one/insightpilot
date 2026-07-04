"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { ThemedSelect } from "@/components/ui/ThemedSelect";
import { CurrentUser, apiFetch, getStoredUser } from "@/lib/api";
import { formatDate, formatDateTime, getReportTypeLabel, getRiskMeta } from "@/lib/presentation";

type ReportType = "daily" | "weekly" | "monthly";
type OwnerViewMode = "team" | "mine" | "owner";
type ReportWorkspaceView = "brief" | "trend" | "risk" | "owner" | "history";

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

type OwnerCandidate = {
  owner_user_id: string;
  owner_user_name: string;
};

type OwnerDeltaCard = {
  key: string;
  label: string;
  current: number;
  previous: number;
  delta: number;
  isCurrency?: boolean;
};

type ReportOverviewCard = {
  key: string;
  label: string;
  value: string;
  toneClass?: string;
};

const EMPTY_FILTERS: ReportFilters = {
  reportType: "",
  dateFrom: "",
  dateTo: "",
};

const GENERATE_TYPES: ReportType[] = ["daily", "weekly", "monthly"];
const WORKSPACE_OPTIONS: Array<{ value: ReportWorkspaceView; label: string }> = [
  { value: "brief", label: "摘要看板" },
  { value: "trend", label: "周期变化" },
  { value: "risk", label: "风险上下文" },
  { value: "owner", label: "负责人视图" },
  { value: "history", label: "历史报告" },
];

function getOwnerDisplayName(ownerUserName: string | null | undefined, ownerUserId: string) {
  const normalizedName = ownerUserName?.trim();
  if (normalizedName) {
    return normalizedName;
  }
  const normalizedId = ownerUserId.trim();
  return normalizedId || "未命名负责人";
}

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

function reportCountLabel(customerFilter: string | null, drilledOwnerUserId: string) {
  if (customerFilter) {
    return drilledOwnerUserId ? "负责人关联报告" : "关联报告";
  }
  return drilledOwnerUserId ? "负责人历史报告" : "历史报告";
}

function getOwnerCandidates(items: Report[]) {
  const map = new Map<string, string>();
  for (const item of items) {
    for (const owner of item.metrics_json.owner_summary || []) {
      const ownerUserId = owner.owner_user_id?.trim();
      if (ownerUserId && !map.has(ownerUserId)) {
        // 中文注释：报告聚合里负责人姓名可能为空，这里统一兜底，避免排序和下钻文案直接报错。
        map.set(ownerUserId, getOwnerDisplayName(owner.owner_user_name, ownerUserId));
      }
    }
    for (const risk of item.risk_top_json || []) {
      const ownerUserId = risk.owner_user_id?.trim();
      if (ownerUserId && !map.has(ownerUserId)) {
        map.set(ownerUserId, getOwnerDisplayName(risk.owner_user_name, ownerUserId));
      }
    }
  }
  return [...map.entries()]
    .map(([owner_user_id, owner_user_name]) => ({ owner_user_id, owner_user_name }))
    .sort((left, right) =>
      getOwnerDisplayName(left.owner_user_name, left.owner_user_id).localeCompare(
        getOwnerDisplayName(right.owner_user_name, right.owner_user_id),
        "zh-CN"
      )
    );
}

function findOwnerSnapshot(report: Report | undefined, ownerUserId: string) {
  if (!report) {
    return null;
  }
  return (report.metrics_json.owner_summary || []).find((item) => item.owner_user_id === ownerUserId) || null;
}

function reportIncludesOwner(report: Report, ownerUserId: string) {
  return Boolean(
    (report.metrics_json.owner_summary || []).some((item) => item.owner_user_id === ownerUserId) ||
      (report.risk_top_json || []).some((item) => item.owner_user_id === ownerUserId)
  );
}

function buildOwnerSnapshotText(snapshot: OwnerSummaryItem | null, ownerName: string) {
  if (!snapshot) {
    return `${ownerName} 暂时还没有可用于经营分析的负责人快照。`;
  }
  return `${ownerName} 当前名下共有 ${snapshot.total_customers} 个客户，其中 ${snapshot.active_customers} 个仍在推进，` +
    `${snapshot.high_risk_customers} 个已经进入高风险名单，当前仍有 ${snapshot.active_tasks} 个执行中任务，` +
    `开放商机金额为 ${formatCurrency(snapshot.open_deal_amount)}。`;
}

function buildOwnerDeltaCards(current: OwnerSummaryItem | null, previous: OwnerSummaryItem | null): OwnerDeltaCard[] {
  return [
    {
      key: "active_customers",
      label: "活跃客户",
      current: current?.active_customers || 0,
      previous: previous?.active_customers || 0,
      delta: (current?.active_customers || 0) - (previous?.active_customers || 0),
    },
    {
      key: "high_risk_customers",
      label: "高风险客户",
      current: current?.high_risk_customers || 0,
      previous: previous?.high_risk_customers || 0,
      delta: (current?.high_risk_customers || 0) - (previous?.high_risk_customers || 0),
    },
    {
      key: "active_tasks",
      label: "执行中任务",
      current: current?.active_tasks || 0,
      previous: previous?.active_tasks || 0,
      delta: (current?.active_tasks || 0) - (previous?.active_tasks || 0),
    },
    {
      key: "open_deal_amount",
      label: "开放商机金额",
      current: current?.open_deal_amount || 0,
      previous: previous?.open_deal_amount || 0,
      delta: (current?.open_deal_amount || 0) - (previous?.open_deal_amount || 0),
      isCurrency: true,
    },
  ];
}

function deltaTone(delta: number) {
  if (delta === 0) {
    return "tone-neutral";
  }
  return delta > 0 ? "tone-success" : "tone-warning";
}

function formatDeltaValue(card: OwnerDeltaCard) {
  if (card.isCurrency) {
    const absolute = Math.abs(card.delta);
    return card.delta === 0 ? "持平" : `${card.delta > 0 ? "+" : "-"}${formatCurrency(absolute)}`;
  }
  return formatSignedNumber(card.delta);
}

function formatCardValue(card: OwnerDeltaCard) {
  return card.isCurrency ? formatCurrency(card.current) : `${card.current}`;
}

function truncateText(text: string | null | undefined, maxLength = 92) {
  const safeText = text?.trim();
  if (!safeText) {
    return "暂无补充内容。";
  }
  return safeText.length > maxLength ? `${safeText.slice(0, maxLength)}...` : safeText;
}

function currentOwnerName(
  ownerCandidates: OwnerCandidate[],
  drilledOwnerUserId: string,
  currentUser: CurrentUser | null,
  latestOwnerSnapshot: OwnerSummaryItem | null
) {
  if (!drilledOwnerUserId) {
    return "";
  }
  return (
    latestOwnerSnapshot?.owner_user_name ||
    ownerCandidates.find((item) => item.owner_user_id === drilledOwnerUserId)?.owner_user_name ||
    (currentUser?.user_id === drilledOwnerUserId ? currentUser.real_name : drilledOwnerUserId)
  );
}

function buildOwnerDrilldownHref(
  pathname: "/tasks" | "/risks" | "/approvals",
  options: {
    customerId?: string | null;
    ownerUserId: string;
    ownerUserName: string;
  }
) {
  const params = new URLSearchParams();
  if (options.customerId) {
    params.set("customerId", options.customerId);
  }
  if (pathname === "/tasks") {
    params.set("assigneeUserId", options.ownerUserId);
    params.set("assigneeUserName", options.ownerUserName);
  }
  if (pathname === "/risks") {
    params.set("ownerUserId", options.ownerUserId);
    params.set("ownerUserName", options.ownerUserName);
  }
  if (pathname === "/approvals") {
    params.set("relatedUserId", options.ownerUserId);
    params.set("relatedUserName", options.ownerUserName);
  }
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function ReportsPageContent() {
  const searchParams = useSearchParams();
  const customerFilter = searchParams.get("customerId");
  const ownerUserIdFromQuery = searchParams.get("ownerUserId");
  const ownerViewFromQuery = searchParams.get("ownerView");

  const [items, setItems] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submittingType, setSubmittingType] = useState<ReportType | "">("");
  const [draftFilters, setDraftFilters] = useState<ReportFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<ReportFilters>(EMPTY_FILTERS);
  const [ownerViewMode, setOwnerViewMode] = useState<OwnerViewMode>("team");
  const [selectedOwnerUserId, setSelectedOwnerUserId] = useState("");
  const [workspaceView, setWorkspaceView] = useState<ReportWorkspaceView>("brief");
  const [selectedRiskSnapshotId, setSelectedRiskSnapshotId] = useState("");

  const currentUser = useMemo(() => getStoredUser(), []);

  useEffect(() => {
    if (ownerViewFromQuery === "mine" && currentUser?.user_id) {
      setOwnerViewMode("mine");
      setSelectedOwnerUserId(currentUser.user_id);
      return;
    }
    if (ownerUserIdFromQuery) {
      setOwnerViewMode("owner");
      setSelectedOwnerUserId(ownerUserIdFromQuery);
      return;
    }
    setOwnerViewMode("team");
    setSelectedOwnerUserId("");
  }, [currentUser?.user_id, ownerUserIdFromQuery, ownerViewFromQuery]);

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

  const ownerCandidates = useMemo(() => getOwnerCandidates(items), [items]);

  useEffect(() => {
    if (ownerViewMode === "mine" && currentUser?.user_id) {
      setSelectedOwnerUserId(currentUser.user_id);
      return;
    }
    if (ownerViewMode === "owner" && selectedOwnerUserId && !ownerCandidates.some((item) => item.owner_user_id === selectedOwnerUserId)) {
      setOwnerViewMode("team");
      setSelectedOwnerUserId("");
    }
  }, [currentUser?.user_id, ownerCandidates, ownerViewMode, selectedOwnerUserId]);

  const drilledOwnerUserId =
    ownerViewMode === "team" ? "" : ownerViewMode === "mine" ? currentUser?.user_id || selectedOwnerUserId : selectedOwnerUserId;
  const isOwnerDrilldown = Boolean(drilledOwnerUserId);

  const visibleItems = useMemo(
    () => (drilledOwnerUserId ? items.filter((item) => reportIncludesOwner(item, drilledOwnerUserId)) : items),
    [drilledOwnerUserId, items]
  );

  // 中文注释：摘要看板默认仍然围绕当前筛选结果里的最新报告展开，只是在负责人下钻时再叠加负责人级过滤。
  const latestReport = useMemo(() => visibleItems[0], [visibleItems]);
  const latestMetrics = latestReport?.metrics_json;
  const latestTotals = latestMetrics?.totals;
  const latestHeadline = latestMetrics?.headline_numbers;
  const latestTeamOwners = latestMetrics?.owner_summary || [];
  const latestOwnerSnapshot = isOwnerDrilldown ? findOwnerSnapshot(latestReport, drilledOwnerUserId) : null;
  const previousOwnerSnapshot = isOwnerDrilldown ? findOwnerSnapshot(visibleItems[1], drilledOwnerUserId) : null;
  const displayedOwners = isOwnerDrilldown && latestOwnerSnapshot ? [latestOwnerSnapshot] : latestTeamOwners;
  const displayedRiskTop = isOwnerDrilldown
    ? (latestReport?.risk_top_json || []).filter((item) => item.owner_user_id === drilledOwnerUserId)
    : latestReport?.risk_top_json || [];
  const ownerDeltaCards = useMemo(
    () => buildOwnerDeltaCards(latestOwnerSnapshot, previousOwnerSnapshot),
    [latestOwnerSnapshot, previousOwnerSnapshot]
  );
  const activeOwnerName = currentOwnerName(ownerCandidates, drilledOwnerUserId, currentUser, latestOwnerSnapshot);
  const taskDrilldownHref = isOwnerDrilldown
    ? buildOwnerDrilldownHref("/tasks", {
        customerId: customerFilter,
        ownerUserId: drilledOwnerUserId,
        ownerUserName: activeOwnerName || drilledOwnerUserId,
      })
    : "";
  const riskDrilldownHref = isOwnerDrilldown
    ? buildOwnerDrilldownHref("/risks", {
        customerId: customerFilter,
        ownerUserId: drilledOwnerUserId,
        ownerUserName: activeOwnerName || drilledOwnerUserId,
      })
    : "";
  const approvalDrilldownHref = isOwnerDrilldown
    ? buildOwnerDrilldownHref("/approvals", {
        customerId: customerFilter,
        ownerUserId: drilledOwnerUserId,
        ownerUserName: activeOwnerName || drilledOwnerUserId,
      })
    : "";

  const emptyDetail = isOwnerDrilldown
    ? `当前负责人视角还没有命中报告。${ownerViewMode === "mine" ? "如果你刚接手客户，可以先生成一轮周报或月报再回来查看。" : "可以切回团队视角，先判断当前经营问题集中在哪位负责人。"}`
    : customerFilter
      ? "当前客户还没有进入已生成经营报告的引用范围。"
      : "建议先生成一轮周报或月报，再回来查看趋势与归属人摘要。";

  useEffect(() => {
    if (!displayedRiskTop.length) {
      setSelectedRiskSnapshotId("");
      return;
    }
    if (!displayedRiskTop.some((item) => item.risk_snapshot_id === selectedRiskSnapshotId)) {
      setSelectedRiskSnapshotId(displayedRiskTop[0].risk_snapshot_id);
    }
  }, [displayedRiskTop, selectedRiskSnapshotId]);

  const focusedRiskItem =
    displayedRiskTop.find((item) => item.risk_snapshot_id === selectedRiskSnapshotId) || displayedRiskTop[0] || null;

  const overviewCards = useMemo<ReportOverviewCard[]>(() => {
    if (isOwnerDrilldown && latestOwnerSnapshot) {
      return [
        { key: "reports", label: reportCountLabel(customerFilter, drilledOwnerUserId), value: `${visibleItems.length}` },
        { key: "active_customers", label: "活跃客户", value: `${latestOwnerSnapshot.active_customers}` },
        {
          key: "high_risk",
          label: "高风险客户",
          value: `${latestOwnerSnapshot.high_risk_customers}`,
          toneClass: latestOwnerSnapshot.high_risk_customers ? "tone-danger" : "",
        },
        {
          key: "active_tasks",
          label: "执行中任务",
          value: `${latestOwnerSnapshot.active_tasks}`,
          toneClass: latestOwnerSnapshot.overdue_tasks ? "tone-warning" : "",
        },
        { key: "deal_amount", label: "开放商机金额", value: formatCurrency(latestOwnerSnapshot.open_deal_amount) },
        { key: "won", label: "本周期赢单数", value: `${latestOwnerSnapshot.won_current}` },
      ];
    }
    return [
      { key: "reports", label: reportCountLabel(customerFilter, drilledOwnerUserId), value: `${visibleItems.length}` },
      { key: "report_type", label: "最新报告类型", value: getReportTypeLabel(latestReport?.report_type || "daily") },
      { key: "period", label: "当前观察周期", value: periodText(latestMetrics, latestReport?.report_date || "") },
      { key: "deal_amount", label: "开放商机金额", value: formatCurrency(latestTotals?.open_deal_amount) },
      {
        key: "risk",
        label: "高风险客户",
        value: `${latestTotals?.high_risk_customers || 0}`,
        toneClass: (latestTotals?.high_risk_customers || 0) > 0 ? "tone-danger" : "",
      },
      {
        key: "approvals",
        label: "待审批事项",
        value: `${latestTotals?.pending_approvals || 0}`,
        toneClass: (latestTotals?.pending_approvals || 0) > 0 ? "tone-warning" : "",
      },
    ];
  }, [
    customerFilter,
    drilledOwnerUserId,
    isOwnerDrilldown,
    latestMetrics,
    latestOwnerSnapshot,
    latestReport?.report_date,
    latestReport?.report_type,
    latestTotals?.high_risk_customers,
    latestTotals?.open_deal_amount,
    latestTotals?.pending_approvals,
    visibleItems.length,
  ]);

  const trendPreviewCards = useMemo(() => {
    if (isOwnerDrilldown) {
      return ownerDeltaCards.map((card) => ({
        key: card.key,
        label: card.label,
        current: formatCardValue(card),
        delta: `变化 ${formatDeltaValue(card)}`,
        previous: `上一份 ${card.isCurrency ? formatCurrency(card.previous) : card.previous}`,
        toneClass: deltaTone(card.delta),
      }));
    }
    return (["followups", "won_deals", "approved_approvals", "completed_tasks"] as Array<
      keyof NonNullable<ReportMetrics["trend_metrics"]>
    >).map((key) => {
      const metric = latestMetrics?.trend_metrics?.[key];
      return {
        key,
        label: trendLabel(key),
        current: `${metric?.current || 0}`,
        delta: `${trendDirectionText(metric)}，变化 ${formatSignedNumber(metric?.delta || 0)}`,
        previous: `上一周期 ${metric?.previous || 0}`,
        toneClass: trendTone(metric),
      };
    });
  }, [isOwnerDrilldown, latestMetrics, ownerDeltaCards]);

  const focusedRiskMeta = focusedRiskItem ? getRiskMeta(focusedRiskItem.risk_level) : null;
  const workspaceLabel = WORKSPACE_OPTIONS.find((item) => item.value === workspaceView)?.label || "摘要看板";
  const ownerPanelItems = isOwnerDrilldown ? displayedOwners : displayedOwners.slice(0, 6);
  const riskQueueItems = displayedRiskTop.slice(0, 6);
  const historyItems = visibleItems.slice(0, 6);

  // 中文注释：新版先走单工作台结构，把摘要、趋势、风险和历史收拢到一个主窗口里。
  return (
    <AppShell>
      <section className="command-panel report-command-bar">
        <div className="report-command-copy">
          <div>
            <p className="eyebrow">Reports</p>
            <h1 className="report-command-title">经营报告</h1>
          </div>
          <div className="report-meta">
            <span className="meta-chip">{customerFilter ? `客户 ${customerFilter}` : "全局经营视角"}</span>
            <span className="meta-chip">{isOwnerDrilldown ? `负责人 ${activeOwnerName || drilledOwnerUserId}` : "团队聚合视角"}</span>
            {latestReport ? <span className="meta-chip">最新报告 {formatDateTime(latestReport.created_at)}</span> : null}
          </div>
        </div>
        <div className="page-actions report-command-actions">
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

      <section className="command-panel report-context-bar">
        <div className="report-context-grid">
          <label className="report-inline-field">
            <span>报告类型</span>
            <ThemedSelect
              onChange={(value) =>
                setDraftFilters((current) => ({ ...current, reportType: value as ReportFilters["reportType"] }))
              }
              options={[
                { value: "", label: "全部类型" },
                { value: "daily", label: "日报" },
                { value: "weekly", label: "周报" },
                { value: "monthly", label: "月报" },
              ]}
              value={draftFilters.reportType}
            />
          </label>
          <label className="report-inline-field">
            <span>开始日期</span>
            <input
              className="input-like compact-input"
              onChange={(event) => setDraftFilters((current) => ({ ...current, dateFrom: event.target.value }))}
              type="date"
              value={draftFilters.dateFrom}
            />
          </label>
          <label className="report-inline-field">
            <span>结束日期</span>
            <input
              className="input-like compact-input"
              onChange={(event) => setDraftFilters((current) => ({ ...current, dateTo: event.target.value }))}
              type="date"
              value={draftFilters.dateTo}
            />
          </label>
          <div className="report-inline-field">
            <span>当前聚焦</span>
            <div className="input-like compact-input readonly-field">{customerFilter ? `客户 ${customerFilter}` : "全局经营视角"}</div>
          </div>
          <div className="report-inline-field report-owner-controls">
            <span>负责人视角</span>
            <div className="report-segmented">
              <button
                className={ownerViewMode === "team" ? "button" : "button-secondary"}
                onClick={() => {
                  setOwnerViewMode("team");
                  setSelectedOwnerUserId("");
                }}
                type="button"
              >
                团队
              </button>
              <button
                className={ownerViewMode === "mine" ? "button" : "button-secondary"}
                disabled={!currentUser}
                onClick={() => {
                  if (!currentUser) {
                    return;
                  }
                  setOwnerViewMode("mine");
                  setSelectedOwnerUserId(currentUser.user_id);
                }}
                type="button"
              >
                我的
              </button>
            </div>
          </div>
          <label className="report-inline-field">
            <span>指定负责人</span>
            <ThemedSelect
              onChange={(value) => {
                setSelectedOwnerUserId(value);
                setOwnerViewMode(value ? "owner" : "team");
              }}
              options={[
                { value: "", label: "未指定" },
                ...ownerCandidates.map((owner) => ({
                  value: owner.owner_user_id,
                  label: owner.owner_user_name,
                })),
              ]}
              value={ownerViewMode === "owner" ? selectedOwnerUserId : ""}
            />
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
        <div className="report-meta">
          <span className={`meta-chip ${ownerViewMode === "team" ? "tone-info" : ""}`}>团队聚合</span>
          <span className={`meta-chip ${ownerViewMode === "mine" ? "tone-info" : ""}`}>我的视角</span>
          <span className={`meta-chip ${ownerViewMode === "owner" ? "tone-info" : ""}`}>
            {ownerViewMode === "owner" ? `负责人 ${activeOwnerName || selectedOwnerUserId}` : "未指定负责人"}
          </span>
          {latestReport ? <span className="meta-chip">最新周期 {periodText(latestMetrics, latestReport.report_date)}</span> : null}
        </div>
        {isOwnerDrilldown ? (
          <div className="report-quick-links">
            <Link className="button" href={taskDrilldownHref}>
              任务明细
            </Link>
            <Link className="button-secondary" href={riskDrilldownHref}>
              风险明细
            </Link>
            <Link className="button-secondary" href={approvalDrilldownHref}>
              审批明细
            </Link>
          </div>
        ) : null}
      </section>

      {!loading && !visibleItems.length && !error ? (
        <EmptyCard detail={emptyDetail} text={isOwnerDrilldown ? "当前负责人视角还没有匹配到经营报告。" : "当前还没有经营报告。"} />
      ) : null}

      {visibleItems.length ? (
        <>
          <section className="report-overview-grid">
            {overviewCards.map((card) => (
              <article className={`report-compact-metric ${card.toneClass || ""}`} key={card.key}>
                <span>{card.label}</span>
                <strong>{card.value}</strong>
              </article>
            ))}
          </section>

          <section className="command-panel report-workspace-panel">
            <div className="report-workspace-header">
              <div>
                <p className="eyebrow">Workspace</p>
                <h2>{workspaceLabel}</h2>
              </div>
              <div className="report-workspace-controls">
                <label className="report-inline-field report-inline-field-compact">
                  <span>模块切换</span>
                  <ThemedSelect
                    onChange={(value) => setWorkspaceView(value as ReportWorkspaceView)}
                    options={WORKSPACE_OPTIONS}
                    value={workspaceView}
                  />
                </label>
                {workspaceView === "risk" && riskQueueItems.length ? (
                  <label className="report-inline-field report-inline-field-compact">
                    <span>重点客户</span>
                    <ThemedSelect
                      onChange={(value) => setSelectedRiskSnapshotId(value)}
                      options={riskQueueItems.map((item) => ({
                        value: item.risk_snapshot_id,
                        label: item.customer_name || item.customer_id,
                      }))}
                      value={selectedRiskSnapshotId}
                    />
                  </label>
                ) : null}
              </div>
            </div>
            <div className="report-meta">
              <span className="meta-chip">{getReportTypeLabel(latestReport.report_type)}</span>
              <span className="meta-chip">周期 {periodText(latestMetrics, latestReport.report_date)}</span>
              <span className="meta-chip">生成于 {formatDateTime(latestReport.created_at)}</span>
            </div>

            {workspaceView === "brief" ? (
              <div className="report-workspace-grid">
                <article className="report-surface">
                  <div className="summary-list report-summary-grid">
                    {isOwnerDrilldown ? (
                      <>
                        <div className="summary-item">
                          <strong>负责人快照</strong>
                          <p>{buildOwnerSnapshotText(latestOwnerSnapshot, activeOwnerName || drilledOwnerUserId)}</p>
                        </div>
                        <div className="summary-item">
                          <strong>团队摘要参考</strong>
                          <p>{latestReport.summary}</p>
                        </div>
                        <div className="summary-item">
                          <strong>动作建议参考</strong>
                          <p>{latestReport.suggestions}</p>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="summary-item">
                          <strong>经营摘要</strong>
                          <p>{latestReport.summary}</p>
                        </div>
                        <div className="summary-item">
                          <strong>行动建议</strong>
                          <p>{latestReport.suggestions}</p>
                        </div>
                      </>
                    )}
                  </div>
                  <div className="highlight-strip report-highlight-strip">
                    {isOwnerDrilldown && latestOwnerSnapshot ? (
                      <>
                        <div className="highlight-card">
                          <strong>{latestOwnerSnapshot.active_customers}</strong>
                          <span>活跃客户</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{latestOwnerSnapshot.active_tasks}</strong>
                          <span>执行中任务</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{latestOwnerSnapshot.won_current}</strong>
                          <span>本周期赢单</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="highlight-card">
                          <strong>{latestHeadline?.followups_current || 0}</strong>
                          <span>本周期跟进</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{latestHeadline?.won_current || 0}</strong>
                          <span>本周期赢单</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{latestHeadline?.completed_current || 0}</strong>
                          <span>本周期完成任务</span>
                        </div>
                      </>
                    )}
                  </div>
                </article>
                <aside className="report-side-panel">
                  <article className="report-side-card">
                    <div className="report-side-card-header">
                      <strong>{isOwnerDrilldown ? "负责人变化速览" : "当前周期变化"}</strong>
                      <span>{trendPreviewCards.length} 项</span>
                    </div>
                    <div className="report-trend-grid report-trend-grid-compact">
                      {trendPreviewCards.map((card) => (
                        <div className={`report-trend-card ${card.toneClass || ""}`} key={card.key}>
                          <strong>{card.current}</strong>
                          <span>{card.label}</span>
                          <small>{card.delta}</small>
                        </div>
                      ))}
                    </div>
                  </article>
                  <article className="report-side-card">
                    <div className="report-side-card-header">
                      <strong>{focusedRiskItem ? "风险焦点" : "风险状态"}</strong>
                      {focusedRiskMeta ? <span className={`meta-chip ${focusedRiskMeta.toneClass}`}>{focusedRiskMeta.label}</span> : null}
                    </div>
                    {focusedRiskItem ? (
                      <>
                        <div className="report-meta">
                          <span className="meta-chip">{focusedRiskItem.customer_name || focusedRiskItem.customer_id}</span>
                          <span className="meta-chip">负责人 {focusedRiskItem.owner_user_name || focusedRiskItem.owner_user_id}</span>
                        </div>
                        <p>{truncateText(focusedRiskItem.llm_reason, 72)}</p>
                        <p>{truncateText(focusedRiskItem.llm_suggestion, 72)}</p>
                        <div className="page-actions">
                          <Link className="button-secondary" href={`/customers/${focusedRiskItem.customer_id}`}>
                            查看客户详情
                          </Link>
                        </div>
                      </>
                    ) : (
                      <p>当前没有需要优先处理的重点风险客户。</p>
                    )}
                  </article>
                </aside>
              </div>
            ) : null}

            {workspaceView === "trend" ? (
              <div className="report-main-stack">
                <div className="report-meta">
                  <span className="meta-chip">
                    当前周期 {latestMetrics?.period_start ? formatDate(latestMetrics.period_start) : "未记录"} 到{" "}
                    {latestMetrics?.period_end ? formatDate(latestMetrics.period_end) : "未记录"}
                  </span>
                  <span className="meta-chip">
                    {isOwnerDrilldown
                      ? visibleItems[1]
                        ? `上一份报告 ${getReportTypeLabel(visibleItems[1].report_type)} / ${formatDate(visibleItems[1].report_date)}`
                        : "当前没有更早的负责人报告可对比"
                      : `上一周期 ${latestMetrics?.previous_period_start ? formatDate(latestMetrics.previous_period_start) : "未记录"} 到 ${
                          latestMetrics?.previous_period_end ? formatDate(latestMetrics.previous_period_end) : "未记录"
                        }`}
                  </span>
                </div>
                <div className="report-trend-grid">
                  {trendPreviewCards.map((card) => (
                    <article className={`report-trend-card report-trend-card-detail ${card.toneClass || ""}`} key={card.key}>
                      <strong>{card.current}</strong>
                      <span>{card.label}</span>
                      <small>{card.delta}</small>
                      <p>{card.previous}</p>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}

            {workspaceView === "risk" ? (
              <div className="report-risk-layout">
                <article className="report-risk-focus">
                  {focusedRiskItem ? (
                    <>
                      <div className="report-risk-header">
                        <div>
                          <p className="eyebrow">Risk Focus</p>
                          <h3>{focusedRiskItem.customer_name || focusedRiskItem.customer_id}</h3>
                        </div>
                        <div className="report-meta">
                          {focusedRiskMeta ? <span className={`meta-chip ${focusedRiskMeta.toneClass}`}>{focusedRiskMeta.label}</span> : null}
                          <span className="meta-chip">风险分 {focusedRiskItem.risk_score}</span>
                          <span className="meta-chip">负责人 {focusedRiskItem.owner_user_name || focusedRiskItem.owner_user_id}</span>
                        </div>
                      </div>
                      <div className="report-risk-summary">
                        <div className="summary-item">
                          <strong>风险原因</strong>
                          <p>{focusedRiskItem.llm_reason || "当前没有补充风险原因。"}</p>
                        </div>
                        <div className="summary-item">
                          <strong>建议动作</strong>
                          <p>{focusedRiskItem.llm_suggestion || "当前没有补充动作建议。"}</p>
                        </div>
                      </div>
                      <div className="page-actions">
                        <Link className="button" href={`/customers/${focusedRiskItem.customer_id}`}>
                          查看客户详情
                        </Link>
                        <Link className="button-secondary" href={riskDrilldownHref || "/risks"}>
                          查看风险明细
                        </Link>
                      </div>
                    </>
                  ) : (
                    <div className="summary-item">
                      <strong>{isOwnerDrilldown ? "当前负责人暂无重点风险客户" : "当前没有重点风险客户"}</strong>
                      <p>{isOwnerDrilldown ? "这位负责人当前更需要盯执行节奏和任务积压。" : "当前可以先把注意力放在趋势变化与负责人分布上。"}</p>
                    </div>
                  )}
                </article>
                <aside className="report-side-panel">
                  <article className="report-side-card">
                    <div className="report-side-card-header">
                      <strong>风险队列</strong>
                      <span>{riskQueueItems.length} 个重点客户</span>
                    </div>
                    <div className="report-risk-list">
                      {riskQueueItems.length ? (
                        riskQueueItems.map((item) => {
                          const riskMeta = getRiskMeta(item.risk_level);
                          const isActive = item.risk_snapshot_id === focusedRiskItem?.risk_snapshot_id;
                          return (
                            <button
                              className={`report-risk-queue-item ${isActive ? "is-active" : ""}`}
                              key={item.risk_snapshot_id}
                              onClick={() => setSelectedRiskSnapshotId(item.risk_snapshot_id)}
                              type="button"
                            >
                              <strong>{item.customer_name || item.customer_id}</strong>
                              <span>{riskMeta.label}</span>
                              <small>负责人 {item.owner_user_name || item.owner_user_id}</small>
                            </button>
                          );
                        })
                      ) : (
                        <p className="muted-text">当前没有可切换的风险客户。</p>
                      )}
                    </div>
                  </article>
                </aside>
              </div>
            ) : null}

            {workspaceView === "owner" ? (
              <div className="report-owner-list">
                {ownerPanelItems.length ? (
                  ownerPanelItems.map((owner) => {
                    const selected = owner.owner_user_id === drilledOwnerUserId;
                    return (
                      <article className="report-owner-card" key={owner.owner_user_id}>
                        <div className="report-owner-card-header">
                          <div>
                            <strong>{owner.owner_user_name}</strong>
                            <div className="report-meta">
                              <span className="meta-chip">客户总数 {owner.total_customers}</span>
                              <span className={`meta-chip ${owner.high_risk_customers ? "tone-danger" : ""}`}>高风险 {owner.high_risk_customers}</span>
                              <span className={`meta-chip ${owner.overdue_tasks ? "tone-warning" : ""}`}>逾期任务 {owner.overdue_tasks}</span>
                              {selected ? <span className="meta-chip tone-info">当前下钻对象</span> : null}
                            </div>
                          </div>
                          {!isOwnerDrilldown ? (
                            <button
                              className="button-secondary"
                              onClick={() => {
                                setOwnerViewMode("owner");
                                setSelectedOwnerUserId(owner.owner_user_id);
                              }}
                              type="button"
                            >
                              继续下钻
                            </button>
                          ) : null}
                        </div>
                        <div className="report-owner-stats">
                          <div className="report-owner-stat">
                            <span>活跃客户</span>
                            <strong>{owner.active_customers}</strong>
                          </div>
                          <div className="report-owner-stat">
                            <span>执行中任务</span>
                            <strong>{owner.active_tasks}</strong>
                          </div>
                          <div className="report-owner-stat">
                            <span>开放商机金额</span>
                            <strong>{formatCurrency(owner.open_deal_amount)}</strong>
                          </div>
                          <div className="report-owner-stat">
                            <span>本周期赢单</span>
                            <strong>{owner.won_current}</strong>
                          </div>
                        </div>
                      </article>
                    );
                  })
                ) : (
                  <div className="summary-item">
                    <strong>{isOwnerDrilldown ? "当前负责人没有聚合快照" : "当前没有归属人聚合结果"}</strong>
                    <p>{isOwnerDrilldown ? "说明这位负责人当前还没有足够的负责人级聚合数据。" : "建议先补充客户、任务或商机样本后再看归属人视图。"}</p>
                  </div>
                )}
              </div>
            ) : null}

            {workspaceView === "history" ? (
              <div className="report-history-list">
                {historyItems.map((item) => {
                  const metrics = item.metrics_json || {};
                  const totals = metrics.totals || {};
                  const headline = metrics.headline_numbers || {};
                  const ownerSnapshot = isOwnerDrilldown ? findOwnerSnapshot(item, drilledOwnerUserId) : null;
                  return (
                    <article className="report-history-card" key={item.report_id}>
                      <div className="report-history-card-header">
                        <div>
                          <p className="eyebrow">{getReportTypeLabel(item.report_type)}</p>
                          <h3>{periodText(metrics, item.report_date)}</h3>
                        </div>
                        <div className="report-meta">
                          <span className="meta-chip">报告编号 {item.report_id}</span>
                          <span className="meta-chip">生成于 {formatDateTime(item.created_at)}</span>
                        </div>
                      </div>
                      <div className="summary-list report-summary-grid">
                        {ownerSnapshot ? (
                          <div className="summary-item">
                            <strong>负责人快照</strong>
                            <p>{buildOwnerSnapshotText(ownerSnapshot, ownerSnapshot.owner_user_name)}</p>
                          </div>
                        ) : null}
                        <div className="summary-item">
                          <strong>经营摘要</strong>
                          <p>{truncateText(item.summary, 120)}</p>
                        </div>
                        <div className="summary-item">
                          <strong>行动建议</strong>
                          <p>{truncateText(item.suggestions, 120)}</p>
                        </div>
                      </div>
                      <div className="highlight-strip">
                        <div className="highlight-card">
                          <strong>{ownerSnapshot ? ownerSnapshot.high_risk_customers : totals.high_risk_customers || 0}</strong>
                          <span>高风险客户</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{ownerSnapshot ? ownerSnapshot.active_tasks : totals.active_tasks || 0}</strong>
                          <span>执行中任务</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{ownerSnapshot ? formatCurrency(ownerSnapshot.open_deal_amount) : formatCurrency(totals.open_deal_amount)}</strong>
                          <span>开放商机金额</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{ownerSnapshot ? ownerSnapshot.won_current : headline.won_current || 0}</strong>
                          <span>本周期赢单</span>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </AppShell>
  );

  /*
  return (
    <AppShell>
      <section className="page-hero report-hero">
        <div className="report-hero-copy">
          <p className="eyebrow">Executive Brief Upgrade</p>
          <h1>把周报、月报、趋势指标和归属人视角压缩成一块能直接读懂经营节奏的摘要看板。</h1>
          <p className="lead">
            当前版本先聚焦"轻操作、强聚合"的 V1：上层看摘要和趋势，下层再看风险上下文与历史报告流。
            {customerFilter ? ` 当前已按客户 ${customerFilter} 做钻取。` : ""}
            {isOwnerDrilldown ? ` 现在正在按负责人 ${activeOwnerName || drilledOwnerUserId} 继续下钻。` : ""}
          </p>
        </div>
        <div className="page-actions report-hero-actions">
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

      <section className="command-panel report-filter-panel">
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
            <div className="input-like compact-input readonly-field">
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

      <section className="command-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Owner Drilldown</p>
            <h2>按归属人继续下钻</h2>
            <p className="panel-copy">
              当前"团队视角"先按报告里的负责人聚合结果承接，不代表真实组织架构团队；真实团队模型已记入下个版本需求。
            </p>
          </div>
        </div>
        <div className="page-actions">
          <button
            className={ownerViewMode === "team" ? "button" : "button-secondary"}
            onClick={() => {
              setOwnerViewMode("team");
              setSelectedOwnerUserId("");
            }}
            type="button"
          >
            全部团队
          </button>
          <button
            className={ownerViewMode === "mine" ? "button" : "button-secondary"}
            disabled={!currentUser}
            onClick={() => {
              if (!currentUser) {
                return;
              }
              setOwnerViewMode("mine");
              setSelectedOwnerUserId(currentUser.user_id);
            }}
            type="button"
          >
            我的视角
          </button>
          <select
            className="input-like compact-input"
            onChange={(event) => {
              const nextOwnerUserId = event.target.value;
              setSelectedOwnerUserId(nextOwnerUserId);
              setOwnerViewMode(nextOwnerUserId ? "owner" : "team");
            }}
            value={ownerViewMode === "owner" ? selectedOwnerUserId : ""}
          >
            <option value="">指定负责人下钻</option>
            {ownerCandidates.map((owner) => (
              <option key={owner.owner_user_id} value={owner.owner_user_id}>
                {owner.owner_user_name}
              </option>
            ))}
          </select>
        </div>
        <div className="report-meta">
          <span className={`meta-chip ${ownerViewMode === "team" ? "tone-info" : ""}`}>团队视角</span>
          <span className={`meta-chip ${ownerViewMode === "mine" ? "tone-info" : ""}`}>我的视角</span>
          <span className={`meta-chip ${ownerViewMode === "owner" ? "tone-info" : ""}`}>
            {ownerViewMode === "owner" ? `当前负责人 ${activeOwnerName || selectedOwnerUserId}` : "未指定负责人"}
          </span>
        </div>
      </section>

      {isOwnerDrilldown ? (
        <section className="command-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Action Links</p>
              <h2>继续下钻到执行与审批明细</h2>
              <p className="panel-copy">
                这里把负责人视角下最常继续看的三类明细直接串起来，避免在报告、任务、风险和审批之间反复手动重新筛选。
              </p>
            </div>
          </div>
          <div className="page-actions">
            <Link className="button" href={taskDrilldownHref}>
              查看任务明细
            </Link>
            <Link className="button-secondary" href={riskDrilldownHref}>
              查看风险明细
            </Link>
            <Link className="button-secondary" href={approvalDrilldownHref}>
              查看审批明细
            </Link>
          </div>
        </section>
      ) : null}

      {!loading && !visibleItems.length && !error ? (
        <EmptyCard detail={emptyDetail} text={isOwnerDrilldown ? "当前负责人视角还没有匹配到经营报告。" : "当前还没有经营报告。"} />
      ) : null}

      {visibleItems.length ? (
        <>
          {isOwnerDrilldown && latestOwnerSnapshot ? (
            <section className="metric-grid">
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{visibleItems.length}</strong>
                <span className="metric-label">{reportCountLabel(customerFilter, drilledOwnerUserId)}</span>
                <p className="metric-detail">当前负责人最近出现在哪些经营报告里，可以快速判断这位同学是否持续处在管理层关注范围内。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestOwnerSnapshot.total_customers}</strong>
                <span className="metric-label">名下客户总数</span>
                <p className="metric-detail">这是负责人当前盘子大小，也是后续风险、任务和商机金额判断的底座。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestOwnerSnapshot.active_customers}</strong>
                <span className="metric-label">活跃客户</span>
                <p className="metric-detail">活跃客户越多，说明这位负责人当前推进中的经营任务越重，也更值得持续观察节奏变化。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestOwnerSnapshot.high_risk_customers}</strong>
                <span className="metric-label">高风险客户</span>
                <p className="metric-detail">如果高风险客户持续堆积，就需要优先判断是客户问题、任务执行问题还是负责人带宽问题。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestOwnerSnapshot.active_tasks}</strong>
                <span className="metric-label">执行中任务</span>
                <p className="metric-detail">这张卡用来判断这位负责人手上正在推进多少动作，防止建议已经生成但没人真正执行。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestOwnerSnapshot.overdue_tasks}</strong>
                <span className="metric-label">逾期任务</span>
                <p className="metric-detail">逾期任务越多，越说明这位负责人当前执行负荷或优先级管理出了问题，需要尽快介入。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{formatCurrency(latestOwnerSnapshot.open_deal_amount)}</strong>
                <span className="metric-label">开放商机金额</span>
                <p className="metric-detail">这位负责人手上的机会盘子值多少钱，决定了这条下钻线索是否值得管理层优先跟进。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestOwnerSnapshot.won_current}</strong>
                <span className="metric-label">本周期赢单数</span>
                <p className="metric-detail">用最直白的结果指标判断这位负责人最近是否已经把前面的跟进和任务转成了业务结果。</p>
              </article>
            </section>
          ) : (
            <section className="metric-grid">
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{visibleItems.length}</strong>
                <span className="metric-label">{reportCountLabel(customerFilter, drilledOwnerUserId)}</span>
                <p className="metric-detail">当前筛选结果里一共命中了多少份报告，方便快速判断经营复盘的时间覆盖度。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{getReportTypeLabel(latestReport?.report_type || "daily")}</strong>
                <span className="metric-label">最新报告类型</span>
                <p className="metric-detail">当前摘要看板默认读取最新一份报告，周报、月报和日报会走同一套聚合口径。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{periodText(latestMetrics, latestReport?.report_date || "")}</strong>
                <span className="metric-label">当前观察周期</span>
                <p className="metric-detail">同一张卡里统一展示周期标签，避免老板在日报、周报和月报间切换时重新理解时间口径。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{formatCurrency(latestTotals?.open_deal_amount)}</strong>
                <span className="metric-label">开放商机金额</span>
                <p className="metric-detail">用一张卡先看盘子大小，判断当前经营机会池是否足够支撑后续成交节奏。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestTotals?.high_risk_customers || 0}</strong>
                <span className="metric-label">高风险客户</span>
                <p className="metric-detail">风险客户数量直接影响管理层的关注重心，也是后续审批和任务压力的前置指标。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestTotals?.pending_approvals || 0}</strong>
                <span className="metric-label">待审批事项</span>
                <p className="metric-detail">审批积压过多会拖慢执行闭环，所以这张卡帮助主管判断是否需要优先清队列。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestTotals?.overdue_tasks || 0}</strong>
                <span className="metric-label">逾期任务</span>
                <p className="metric-detail">如果逾期任务抬头，就说明风险和建议没有顺利落地到执行动作，需要马上追踪责任人。</p>
              </article>
              <article className="metric-card report-metric-card">
                <strong className="metric-value">{latestTeamOwners.length}</strong>
                <span className="metric-label">归属人样本</span>
                <p className="metric-detail">当前版本先展示最需要管理层关注的前几位负责人，让问题聚焦到可行动的人和客户盘子上。</p>
              </article>
            </section>
          )}

          <section className="workspace-grid">
            <article className="command-panel report-brief-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Latest Brief</p>
                  <h2>{isOwnerDrilldown ? `${activeOwnerName || drilledOwnerUserId} 的负责人视角摘要` : customerFilter ? "该客户相关报告里的最新摘要" : "最新一份报告的管理层摘要"}</h2>
                </div>
                <div className="report-meta">
                  <span className="meta-chip">{getReportTypeLabel(latestReport.report_type)}</span>
                  <span className="meta-chip">周期 {periodText(latestMetrics, latestReport.report_date)}</span>
                  <span className="meta-chip">生成于 {formatDateTime(latestReport.created_at)}</span>
                </div>
              </div>
              <div className="summary-list report-summary-grid">
                {isOwnerDrilldown ? (
                  <>
                    <div className="summary-item">
                      <strong>负责人快照</strong>
                      <p>{buildOwnerSnapshotText(latestOwnerSnapshot, activeOwnerName || drilledOwnerUserId)}</p>
                    </div>
                    <div className="summary-item">
                      <strong>团队摘要参考</strong>
                      <p>{latestReport.summary}</p>
                    </div>
                    <div className="summary-item">
                      <strong>团队行动建议参考</strong>
                      <p>{latestReport.suggestions}</p>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="summary-item">
                      <strong>经营摘要</strong>
                      <p>{latestReport.summary}</p>
                    </div>
                    <div className="summary-item">
                      <strong>行动建议</strong>
                      <p>{latestReport.suggestions}</p>
                    </div>
                  </>
                )}
              </div>
              <div className="highlight-strip report-highlight-strip">
                {isOwnerDrilldown && latestOwnerSnapshot ? (
                  <>
                    <div className="highlight-card">
                      <strong>{latestOwnerSnapshot.active_customers}</strong>
                      <span>当前活跃客户</span>
                    </div>
                    <div className="highlight-card">
                      <strong>{latestOwnerSnapshot.active_tasks}</strong>
                      <span>当前执行中任务</span>
                    </div>
                    <div className="highlight-card">
                      <strong>{latestOwnerSnapshot.won_current}</strong>
                      <span>本周期赢单数</span>
                    </div>
                  </>
                ) : (
                  <>
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
                  </>
                )}
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Risk Context</p>
                  <h2>{isOwnerDrilldown ? "负责人相关风险上下文" : "风险快照上下文"}</h2>
                  <p className="panel-copy">
                    {isOwnerDrilldown
                      ? "现在只看这位负责人名下的重点风险客户，帮助主管判断问题究竟是单点失速还是整队节奏异常。"
                      : "经营报告不是孤立文本，它要能回到具体客户和负责人，帮助团队决定先盯谁、先处理什么。"}
                  </p>
                </div>
              </div>
              <div className="summary-list">
                {displayedRiskTop.length ? (
                  displayedRiskTop.map((item) => {
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
                    <strong>{isOwnerDrilldown ? "当前负责人暂无重点风险客户" : "当前没有重点风险客户"}</strong>
                    <p>
                      {isOwnerDrilldown
                        ? "这通常说明这位负责人当前更多压力在执行和推进节奏，而不是明显的高风险客户堆积。"
                        : "说明最新一份报告暂时没有拉起高优先级风险上下文，可以把注意力更多放在趋势和责任人分布上。"}
                    </p>
                  </div>
                )}
              </div>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">{isOwnerDrilldown ? "Owner Snapshot Change" : "Trend Metrics"}</p>
                  <h2>{isOwnerDrilldown ? "相对上一份同负责人报告的变化" : "当前周期相对上一周期的变化"}</h2>
                </div>
              </div>
              <div className="highlight-strip">
                {isOwnerDrilldown
                  ? ownerDeltaCards.map((card) => (
                      <div className="highlight-card" key={card.key}>
                        <strong>{formatCardValue(card)}</strong>
                        <span>{card.label}</span>
                        <span className={deltaTone(card.delta)}>变化 {formatDeltaValue(card)}</span>
                        <span>上一份报告 {card.isCurrency ? formatCurrency(card.previous) : card.previous}</span>
                      </div>
                    ))
                  : ([
                      "followups",
                      "won_deals",
                      "approved_approvals",
                      "completed_tasks",
                    ] as Array<keyof NonNullable<ReportMetrics["trend_metrics"]>>).map((key) => {
                      const metric = latestMetrics?.trend_metrics?.[key];
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
                  <h2>{isOwnerDrilldown ? "负责人下钻时先回答什么问题" : "这块摘要看板要回答什么问题"}</h2>
                </div>
              </div>
              <div className="detail-list">
                {isOwnerDrilldown ? (
                  <>
                    <div className="detail-item">
                      <strong>这位负责人手上的盘子是不是在失速</strong>
                      <p>先看活跃客户、高风险客户、执行中任务和商机金额，再判断是客户质量问题还是负责人精力分配问题。</p>
                    </div>
                    <div className="detail-item">
                      <strong>问题是在加重还是在收敛</strong>
                      <p>负责人下钻先对比最近两份同负责人报告，判断高风险和执行积压是正在扩散，还是已经开始收敛。</p>
                    </div>
                    <div className="detail-item">
                      <strong>有没有具体客户需要马上处理</strong>
                      <p>如果风险上下文已经指向具体客户，就优先回到客户详情页，把审批、任务和跟进链路串起来处理。</p>
                    </div>
                  </>
                ) : (
                  <>
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
                  </>
                )}
              </div>
            </article>
          </section>

          <section className="system-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Owner View</p>
                  <h2>{isOwnerDrilldown ? "当前负责人快照" : "归属人视角"}</h2>
                  <p className="panel-copy">
                    {isOwnerDrilldown
                      ? "现在只保留当前负责人的快照，方便把问题锁到可行动的人上。"
                      : "先展示需要被重点关注的负责人，把客户盘子、风险客户和任务执行压力放到一个维度里看。"}
                  </p>
                </div>
              </div>
              <div className="summary-list">
                {displayedOwners.length ? (
                  displayedOwners.map((owner) => {
                    const selected = owner.owner_user_id === drilledOwnerUserId;
                    return (
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
                          {selected ? <span className="meta-chip tone-info">当前下钻对象</span> : null}
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
                        {!isOwnerDrilldown ? (
                          <div className="page-actions">
                            <button
                              className="button-secondary"
                              onClick={() => {
                                setOwnerViewMode("owner");
                                setSelectedOwnerUserId(owner.owner_user_id);
                              }}
                              type="button"
                            >
                              继续下钻这位负责人
                            </button>
                          </div>
                        ) : null}
                      </div>
                    );
                  })
                ) : (
                  <div className="summary-item">
                    <strong>{isOwnerDrilldown ? "当前负责人没有聚合快照" : "当前没有归属人聚合结果"}</strong>
                    <p>
                      {isOwnerDrilldown
                        ? "说明这位负责人虽然被报告提及，但当前还没有足够的负责人级聚合数据。"
                        : "通常说明当前租户还没有足够的客户、任务或商机数据，建议先补充样本再看管理视角。"}
                    </p>
                  </div>
                )}
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Period Scope</p>
                  <h2>{isOwnerDrilldown ? "当前负责人可对比范围" : "本期与上期口径"}</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>当前报告周期</strong>
                  <p>
                    {latestMetrics?.period_start ? formatDate(latestMetrics.period_start) : "未记录"} 到{" "}
                    {latestMetrics?.period_end ? formatDate(latestMetrics.period_end) : "未记录"}
                  </p>
                </div>
                <div className="detail-item">
                  <strong>{isOwnerDrilldown ? "上一份同负责人报告日期" : "上一周期"}</strong>
                  <p>
                    {isOwnerDrilldown
                      ? visibleItems[1]
                        ? `${getReportTypeLabel(visibleItems[1].report_type)} / ${formatDate(visibleItems[1].report_date)}`
                        : "当前还没有更早的同负责人报告可对比"
                      : `${latestMetrics?.previous_period_start ? formatDate(latestMetrics.previous_period_start) : "未记录"} 到 ${
                          latestMetrics?.previous_period_end ? formatDate(latestMetrics.previous_period_end) : "未记录"
                        }`}
                  </p>
                </div>
                <div className="detail-item">
                  <strong>看板解释</strong>
                  <p>
                    {isOwnerDrilldown
                      ? "当前负责人下钻先用"最新一份命中报告 vs 上一份命中报告"来比较负责人快照，等真实组织和负责人级趋势模型补齐后再升级成更精确口径。"
                      : "日报按天对比昨天，周报按自然周对比上周，月报按自然月对比上月，先把比较口径讲清楚，趋势判断才不会跑偏。"}
                  </p>
                </div>
              </div>
            </article>
          </section>

          <section className="report-feed">
            {visibleItems.map((item) => {
              const metrics = item.metrics_json || {};
              const totals = metrics.totals || {};
              const headline = metrics.headline_numbers || {};
              const ownerSnapshot = isOwnerDrilldown ? findOwnerSnapshot(item, drilledOwnerUserId) : null;
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
                    {ownerSnapshot ? (
                      <div className="summary-item">
                        <strong>负责人快照</strong>
                        <p>{buildOwnerSnapshotText(ownerSnapshot, ownerSnapshot.owner_user_name)}</p>
                      </div>
                    ) : null}
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
                    {ownerSnapshot ? (
                      <>
                        <div className="highlight-card">
                          <strong>{ownerSnapshot.high_risk_customers}</strong>
                          <span>高风险客户</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{ownerSnapshot.active_tasks}</strong>
                          <span>执行中任务</span>
                        </div>
                        <div className="highlight-card">
                          <strong>{formatCurrency(ownerSnapshot.open_deal_amount)}</strong>
                          <span>开放商机金额</span>
                        </div>
                      </>
                    ) : (
                      <>
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
                      </>
                    )}
                  </div>

                  <div className="report-meta">
                    <span className="meta-chip">开放商机金额 {formatCurrency(totals.open_deal_amount)}</span>
                    <span className="meta-chip">待审批 {totals.pending_approvals || 0}</span>
                    <span className="meta-chip">活跃任务 {totals.active_tasks || 0}</span>
                    <span className="meta-chip">逾期任务 {totals.overdue_tasks || 0}</span>
                    <span className="meta-chip">重点风险客户 {(item.risk_top_json || []).length}</span>
                  </div>
                </article>
              );
            })}
          </section>
        </>
      ) : null}
    </AppShell>
  );
  */
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
