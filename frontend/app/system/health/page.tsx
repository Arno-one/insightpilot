"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

type StatusCounts = Record<string, number>;

type HardeningControl = {
  control_id: string;
  version: string;
  category: string;
  status: "ready" | "warn" | "blocked";
  evidence: Record<string, unknown>;
  source: string;
  next_step: string;
};

type EnterpriseHardeningReport = {
  hardening_version: string;
  phase_range: string;
  overall_status: string;
  control_count: number;
  status_counts: StatusCounts;
  controls: HardeningControl[];
  stage_gate: {
    can_enter_enterprise_pilot: boolean;
    must_fix_before_production: string[];
    should_fix_before_production: string[];
  };
  execution_boundary: {
    report_only: boolean;
    external_write_enabled: boolean;
    auto_remediation_enabled: boolean;
    description: string;
  };
};

type ReadinessCheck = {
  check_id: string;
  component: string;
  status: "pass" | "warn" | "fail";
  message: string;
  recommendation: string;
};

type DeploymentReadiness = {
  readiness_version: string;
  overall_status: string;
  check_counts: StatusCounts;
  blocking_count: number;
  warning_count: number;
  checks: ReadinessCheck[];
};

type BackupDomain = {
  domain_id: string;
  name: string;
  tables: string[];
  backup_mode: string;
  restore_order: number;
  rpo_minutes: number;
  rto_minutes: number;
  retention_days: number;
  tenant_scoped: boolean;
  verification_points: string[];
};

type BackupRecovery = {
  plan_version: string;
  overall_status: string;
  domain_count: number;
  table_count: number;
  check_counts: StatusCounts;
  checks: Array<{
    check_id: string;
    status: "pass" | "warn" | "fail";
    message: string;
    recommendation: string;
  }>;
  manifest: {
    domains: BackupDomain[];
  };
  guardrails: Array<{
    guardrail_id: string;
    stage: string;
    required: boolean;
    description: string;
  }>;
  execution_boundary: {
    auto_backup_enabled: boolean;
    auto_restore_enabled: boolean;
    external_write_enabled: boolean;
    description: string;
  };
};

type ReleaseGateItem = {
  item_id: string;
  category: string;
  severity: "pass" | "warning" | "blocker";
  title: string;
  evidence: Record<string, unknown>;
  required_action: string;
  source: string;
};

type ReleaseGateChecklist = {
  gate_version: string;
  release_decision: string;
  can_release_to_pilot: boolean;
  can_release_to_production: boolean;
  item_count: number;
  severity_counts: StatusCounts;
  items: ReleaseGateItem[];
  manual_confirmation_required: string[];
  execution_boundary: {
    checklist_only: boolean;
    external_write_enabled: boolean;
    auto_release_enabled: boolean;
    description: string;
  };
};

type HealthConsoleData = {
  hardening: EnterpriseHardeningReport;
  readiness: DeploymentReadiness;
  backup: BackupRecovery;
  releaseGate: ReleaseGateChecklist;
};

const statusText: Record<string, string> = {
  ready: "就绪",
  ready_with_warnings: "有待处理建议",
  warn: "提醒",
  blocked: "阻断",
  pass: "通过",
  fail: "失败"
};

function statusTone(status: string) {
  if (status === "blocked" || status === "fail") {
    return "tone-danger";
  }
  if (status === "warn" || status === "ready_with_warnings") {
    return "tone-warning";
  }
  return "tone-success";
}

function formatStatus(status: string) {
  return statusText[status] || status;
}

function stringifyEvidence(value: unknown) {
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (Array.isArray(value)) {
    return value.join(" / ");
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value ?? "-");
}

export default function SystemHealthPage() {
  const [data, setData] = useState<HealthConsoleData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"hardening" | "deployment" | "backup" | "release">("hardening");

  async function loadHealthConsole() {
    setLoading(true);
    setError("");
    try {
      const [hardening, readiness, backup, releaseGate] = await Promise.all([
        apiFetch<EnterpriseHardeningReport>("/api/system/enterprise-hardening"),
        apiFetch<DeploymentReadiness>("/api/system/deployment-readiness"),
        apiFetch<BackupRecovery>("/api/system/backup-recovery"),
        apiFetch<ReleaseGateChecklist>("/api/system/release-gate")
      ]);
      setData({
        hardening: hardening.data,
        readiness: readiness.data,
        backup: backup.data,
        releaseGate: releaseGate.data
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "系统健康数据加载失败。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHealthConsole();
  }, []);

  const hardeningWarnings = useMemo(() => {
    if (!data) {
      return [];
    }
    return data.hardening.controls.filter((control) => control.status !== "ready");
  }, [data]);

  return (
    <AppShell>
      <section className="command-panel health-hero-panel">
        <div>
          <p className="eyebrow">Enterprise Health Console</p>
          <h1>系统健康总览</h1>
          <p className="lead">把企业级硬化、部署风险和备份恢复边界收在同一张控制台里，只读展示，不执行自动修复或外部动作。</p>
        </div>
        <button className="button-secondary" onClick={loadHealthConsole} type="button">
          刷新状态
        </button>
      </section>

      {error ? <ErrorCard message={error} detail="请确认当前账号具备 system:rbac:manage 权限，并检查后端系统管理接口状态。" /> : null}
      {loading ? <LoadingCard detail="正在同步企业级硬化、部署就绪和备份恢复报告。" /> : null}
      {!loading && !data && !error ? <EmptyCard text="暂无系统健康数据。" detail="请先完成后端硬化报告初始化。" /> : null}

      {data ? (
        <>
          <section className="metric-grid">
            <article className={`metric-card health-status-card ${statusTone(data.hardening.overall_status)}`}>
              <strong className="metric-value">{formatStatus(data.hardening.overall_status)}</strong>
              <span className="metric-label">阶段状态</span>
              <p className="metric-detail">{data.hardening.phase_range}，{data.hardening.control_count} 个控制项。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{data.releaseGate.can_release_to_pilot ? "允许" : "阻断"}</strong>
              <span className="metric-label">企业试点准入</span>
              <p className="metric-detail">发布门禁结论：{data.releaseGate.release_decision}。</p>
            </article>
            <article className={`metric-card ${data.readiness.blocking_count ? "tone-danger" : "tone-warning"}`}>
              <strong className="metric-value">{data.readiness.blocking_count}/{data.readiness.warning_count}</strong>
              <span className="metric-label">部署阻断 / 提醒</span>
              <p className="metric-detail">生产发布前应把阻断项清零，并收敛默认密钥、账号、Redis 等提醒。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{data.backup.domain_count}</strong>
              <span className="metric-label">备份恢复域</span>
              <p className="metric-detail">覆盖 {data.backup.table_count} 张关键表，真实对象存储仍需部署侧确认。</p>
            </article>
          </section>

          <section className="command-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Stage Gate</p>
                <h2>企业试点准入</h2>
              </div>
              <span className={`meta-chip ${data.hardening.stage_gate.can_enter_enterprise_pilot ? "tone-success" : "tone-danger"}`}>
                {data.hardening.stage_gate.can_enter_enterprise_pilot ? "允许企业试点" : "存在阻断"}
              </span>
            </div>
            <div className="health-gate-grid">
              <div className="summary-item">
                <strong>生产前必须修复</strong>
                <p>{data.hardening.stage_gate.must_fix_before_production.length ? data.hardening.stage_gate.must_fix_before_production.join(" / ") : "当前没有阻断项。"}</p>
              </div>
              <div className="summary-item">
                <strong>生产前建议修复</strong>
                <p>{data.hardening.stage_gate.should_fix_before_production.length ? data.hardening.stage_gate.should_fix_before_production.join(" / ") : "当前没有 warning。"}</p>
              </div>
              <div className="summary-item">
                <strong>执行边界</strong>
                <p>{data.hardening.execution_boundary.description}</p>
              </div>
            </div>
          </section>

          <section className="command-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Console Sections</p>
                <h2>查看维度</h2>
              </div>
              <div className="workspace-tabs" role="tablist" aria-label="系统健康维度">
                {[
                  ["hardening", "硬化报告"],
                  ["deployment", "部署就绪"],
                  ["backup", "备份恢复"],
                  ["release", "发布门禁"]
                ].map(([key, label]) => (
                  <button
                    className={`workspace-tab ${activeTab === key ? "workspace-tab-active" : ""}`}
                    key={key}
                    onClick={() => setActiveTab(key as "hardening" | "deployment" | "backup" | "release")}
                    type="button"
                  >
                    <span className="workspace-tab-dot" />
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {activeTab === "hardening" ? (
              <div className="health-control-grid">
                {data.hardening.controls.map((control) => (
                  <article className="health-control-card" key={control.control_id}>
                    <div className="health-control-header">
                      <div>
                        <p className="eyebrow">{control.source} / {control.category}</p>
                        <h3>{control.control_id}</h3>
                      </div>
                      <span className={`meta-chip ${statusTone(control.status)}`}>{formatStatus(control.status)}</span>
                    </div>
                    <div className="health-evidence-grid">
                      {Object.entries(control.evidence).slice(0, 4).map(([key, value]) => (
                        <div className="health-evidence-item" key={`${control.control_id}-${key}`}>
                          <span>{key}</span>
                          <strong>{stringifyEvidence(value)}</strong>
                        </div>
                      ))}
                    </div>
                    <p className="panel-copy">{control.next_step}</p>
                  </article>
                ))}
              </div>
            ) : null}

            {activeTab === "deployment" ? (
              <div className="card-stack">
                {data.readiness.checks.map((check) => (
                  <article className="health-check-row" key={check.check_id}>
                    <span className={`meta-chip ${statusTone(check.status)}`}>{formatStatus(check.status)}</span>
                    <div>
                      <p className="eyebrow">{check.component}</p>
                      <h3>{check.message}</h3>
                      <p>{check.recommendation}</p>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}

            {activeTab === "backup" ? (
              <div className="health-backup-layout">
                <div className="table-card">
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>恢复顺序</th>
                          <th>备份域</th>
                          <th>RPO / RTO</th>
                          <th>关键表</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.backup.manifest.domains.map((domain) => (
                          <tr key={domain.domain_id}>
                            <td>{domain.restore_order}</td>
                            <td>
                              <strong>{domain.name}</strong>
                              <p className="table-note">{domain.backup_mode} / {domain.tenant_scoped ? "租户级" : "全局基线"}</p>
                            </td>
                            <td>{domain.rpo_minutes}m / {domain.rto_minutes}m</td>
                            <td>{domain.tables.join("、")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="card-stack">
                  {data.backup.guardrails.map((guardrail) => (
                    <article className="summary-item" key={guardrail.guardrail_id}>
                      <strong>{guardrail.guardrail_id}</strong>
                      <p>{guardrail.stage} / {guardrail.required ? "必须执行" : "建议执行"}</p>
                      <p>{guardrail.description}</p>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}

            {activeTab === "release" ? (
              <div className="health-release-layout">
                <article className="summary-item">
                  <strong>试点准入</strong>
                  <p>{data.releaseGate.can_release_to_pilot ? "当前允许进入企业试点。" : "当前存在阻断项，不能进入企业试点。"}</p>
                </article>
                <article className="summary-item">
                  <strong>生产发布</strong>
                  <p>{data.releaseGate.can_release_to_production ? "当前满足生产候选门槛。" : "当前仍需处理 blocker 或 warning 后再进入生产发布。"}</p>
                </article>
                <article className="summary-item">
                  <strong>人工确认项</strong>
                  <p>{data.releaseGate.manual_confirmation_required.join(" / ") || "暂无人工确认项。"}</p>
                </article>
                <div className="card-stack">
                  {data.releaseGate.items.map((item) => (
                    <article className="health-check-row" key={item.item_id}>
                      <span className={`meta-chip ${statusTone(item.severity === "blocker" ? "blocked" : item.severity === "warning" ? "warn" : "ready")}`}>
                        {item.severity === "blocker" ? "阻断" : item.severity === "warning" ? "提醒" : "通过"}
                      </span>
                      <div>
                        <p className="eyebrow">{item.category} / {item.source}</p>
                        <h3>{item.title}</h3>
                        <p>{item.required_action}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          {hardeningWarnings.length ? (
            <section className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Before Production</p>
                  <h2>上线前建议处理</h2>
                </div>
              </div>
              <div className="card-stack">
                {hardeningWarnings.map((control) => (
                  <article className="summary-item" key={`warning-${control.control_id}`}>
                    <strong>{control.control_id}</strong>
                    <p>{control.next_step}</p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </AppShell>
  );
}
