// 中文注释：统一前端展示层的标签、时间与状态样式映射，避免各页面各写一套。
type Tone = "neutral" | "danger" | "success" | "warning" | "info";

type Meta = {
  label: string;
  tone: Tone;
};

const STATUS_META: Record<string, Meta> = {
  pending: { label: "待处理", tone: "warning" },
  pending_review: { label: "待审批", tone: "warning" },
  approved: { label: "已批准", tone: "success" },
  rejected: { label: "已驳回", tone: "danger" },
  converted: { label: "已转任务", tone: "info" },
  ignored: { label: "已忽略", tone: "neutral" },
  in_progress: { label: "执行中", tone: "info" },
  completed: { label: "已完成", tone: "success" },
  failed: { label: "失败", tone: "danger" },
  success: { label: "成功", tone: "success" },
  running: { label: "运行中", tone: "info" },
  cancelled: { label: "已取消", tone: "neutral" }
};

const RISK_META: Record<string, Meta> = {
  high: { label: "高风险", tone: "danger" },
  medium: { label: "中风险", tone: "warning" },
  low: { label: "低风险", tone: "success" }
};

const PRIORITY_META: Record<string, Meta> = {
  high: { label: "高优先级", tone: "danger" },
  medium: { label: "中优先级", tone: "warning" },
  low: { label: "低优先级", tone: "neutral" }
};

const RUN_TYPE_LABELS: Record<string, string> = {
  agent_chat_runtime: "统一对话",
  risk_analysis: "风险扫描",
  risk_scan: "风险扫描",
  business_report: "经营日报"
};

const REPORT_TYPE_LABELS: Record<string, string> = {
  daily: "日报",
  weekly: "周报",
  monthly: "月报"
};

function toToneClass(tone: Tone) {
  return `tone-${tone}`;
}

export function getStatusMeta(status: string): Meta & { toneClass: string } {
  const meta = STATUS_META[status] || { label: status || "未知状态", tone: "neutral" as Tone };
  return { ...meta, toneClass: toToneClass(meta.tone) };
}

export function getRiskMeta(level: string): Meta & { toneClass: string } {
  const meta = RISK_META[level] || { label: level || "未知风险", tone: "neutral" as Tone };
  return { ...meta, toneClass: toToneClass(meta.tone) };
}

export function getPriorityMeta(priority: string): Meta & { toneClass: string } {
  const meta = PRIORITY_META[priority] || { label: priority || "未设置", tone: "neutral" as Tone };
  return { ...meta, toneClass: toToneClass(meta.tone) };
}

export function getRunTypeLabel(runType: string) {
  return RUN_TYPE_LABELS[runType] || runType || "未知流程";
}

export function getReportTypeLabel(reportType: string) {
  return REPORT_TYPE_LABELS[reportType] || reportType || "报告";
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "未记录";
  }

  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function formatDate(value: string | null | undefined) {
  if (!value) {
    return "未记录";
  }

  return new Date(value).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  });
}

export function formatDuration(durationMs: number | null | undefined) {
  if (!durationMs) {
    return "0 ms";
  }

  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(2)} s`;
  }

  return `${durationMs} ms`;
}

export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}
