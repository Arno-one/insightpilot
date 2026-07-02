"use client";

import { useMemo, useState } from "react";

import { EmptyCard, ErrorCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch, apiFetchBlob } from "@/lib/api";

type ImportEntity = "customer" | "deal" | "follow_up";

type ImportFailure = {
  row_no: number;
  business_key: string;
  reason: string;
  row_data: Record<string, string>;
};

type ImportResult = {
  entity: ImportEntity;
  file_name: string;
  total_count: number;
  success_count: number;
  failed_count: number;
  inserted_keys: string[];
  failures: ImportFailure[];
  failed_rows_csv: string | null;
};

type ImportConfig = {
  key: ImportEntity;
  label: string;
  eyebrow: string;
  lead: string;
  requiredFields: string[];
  validationRules: string[];
};

const importConfigs: ImportConfig[] = [
  {
    key: "customer",
    label: "客户导入",
    eyebrow: "Customer Intake",
    lead: "适合先把客户主档补齐，让客户详情页、风险快照和报告引用先有稳定主键可挂靠。",
    requiredFields: [
      "customer_id",
      "customer_name",
      "owner_user_id",
      "lifecycle_stage",
      "intent_level",
      "customer_level",
      "industry",
      "region",
      "next_follow_up_at",
      "remark"
    ],
    validationRules: [
      "customer_id 只新增不覆盖，重复主键会直接拦下。",
      "owner_user_id 必须是系统里启用中的用户。",
      "销售员账号只能导入 owner_user_id 等于自己的客户。"
    ]
  },
  {
    key: "deal",
    label: "商机导入",
    eyebrow: "Deal Intake",
    lead: "适合把成交金额、报价时间和预计关闭时间补进系统，便于风险规则和摘要看板直接聚合。",
    requiredFields: [
      "deal_id",
      "customer_id",
      "owner_user_id",
      "deal_name",
      "stage",
      "amount",
      "quote_amount",
      "quoted_at",
      "expected_close_at",
      "close_result"
    ],
    validationRules: [
      "customer_id 必须已经存在，并且当前账号对该客户有可见权限。",
      "amount 和 quote_amount 会校验为数字格式。",
      "close_result 只支持 open、won、lost。"
    ]
  },
  {
    key: "follow_up",
    label: "跟进记录导入",
    eyebrow: "Follow-up Intake",
    lead: "适合一次性回灌历史跟进记录，导入成功后会同步回写客户最近跟进时间、下次跟进时间和最新情绪。",
    requiredFields: [
      "follow_up_id",
      "customer_id",
      "deal_id",
      "owner_user_id",
      "follow_up_type",
      "content",
      "sentiment",
      "next_action",
      "next_follow_up_at",
      "occurred_at"
    ],
    validationRules: [
      "customer_id 必须已存在且当前账号可见。",
      "deal_id 如果有值，必须属于同一个 customer_id。",
      "导入成功后会把最新一条跟进同步回写到客户主表。"
    ]
  }
];

function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function ImportsPage() {
  const [selectedEntity, setSelectedEntity] = useState<ImportEntity>("customer");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);

  const currentConfig = useMemo(
    () => importConfigs.find((item) => item.key === selectedEntity) || importConfigs[0],
    [selectedEntity]
  );

  async function handleTemplateDownload() {
    setDownloadingTemplate(true);
    setError("");
    try {
      const response = await apiFetchBlob(`/api/crm/import/templates/${selectedEntity}.csv`);
      saveBlob(response.blob, response.fileName);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "模板下载失败。");
    } finally {
      setDownloadingTemplate(false);
    }
  }

  async function handleImportSubmit() {
    if (!selectedFile) {
      setError("请先选择一个 CSV 文件。");
      return;
    }

    setSubmitting(true);
    setMessage("");
    setError("");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await apiFetch<ImportResult>(`/api/crm/import/${selectedEntity}`, {
        method: "POST",
        body: formData
      });

      setResult(response.data);
      setMessage(
        `导入已执行：共 ${response.data.total_count} 行，成功 ${response.data.success_count} 行，失败 ${response.data.failed_count} 行。`
      );
    } catch (exc) {
      setResult(null);
      setError(exc instanceof Error ? exc.message : "导入失败。");
    } finally {
      setSubmitting(false);
    }
  }

  function handleFailedRowsDownload() {
    if (!result?.failed_rows_csv) {
      return;
    }
    const blob = new Blob(["\ufeff", result.failed_rows_csv], { type: "text/csv;charset=utf-8" });
    saveBlob(blob, `${result.entity}_failed_rows.csv`);
  }

  function handleEntityChange(entity: ImportEntity) {
    setSelectedEntity(entity);
    setSelectedFile(null);
    setResult(null);
    setMessage("");
    setError("");
  }

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">CRM Intake</p>
          <h1>先把轻量数据入口搭好，再让客户详情、风险和报告去消费同一份主数据。</h1>
          <p className="lead">
            这一版先聚焦三类最小必需字段集，按模板上传、按行校验、只新增不覆盖，并且沿用现有 CRM 读取权限控制入口。
          </p>
        </div>
        <div className="page-actions">
          {importConfigs.map((item) => (
            <button
              className={item.key === selectedEntity ? "button" : "button-secondary"}
              key={item.key}
              onClick={() => handleEntityChange(item.key)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} detail="请优先检查模板字段、权限范围、外键引用和时间格式是否正确。" /> : null}

      <section className="metric-grid">
        <article className="metric-card">
          <strong className="metric-value">{currentConfig.requiredFields.length}</strong>
          <span className="metric-label">必填字段数</span>
          <p className="metric-detail">先用最小字段集把入库门槛压低，后续再逐步扩充高级字段。</p>
        </article>
        <article className="metric-card">
          <strong className="metric-value">只新增</strong>
          <span className="metric-label">重复主键策略</span>
          <p className="metric-detail">当前明确采用“只新增不覆盖”，避免导入误操作把线上已校验数据冲掉。</p>
        </article>
        <article className="metric-card">
          <strong className="metric-value">CRM Read</strong>
          <span className="metric-label">复用权限</span>
          <p className="metric-detail">入口和接口都复用了现有 CRM 读取权限，不额外新增一组导入权限点。</p>
        </article>
        <article className="metric-card">
          <strong className="metric-value">{result?.success_count ?? 0}</strong>
          <span className="metric-label">最近成功行数</span>
          <p className="metric-detail">这里显示最近一次导入成功写入的行数，方便快速确认有没有真正落库。</p>
        </article>
      </section>

      <section className="workspace-grid">
        <article className="command-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">{currentConfig.eyebrow}</p>
              <h2>{currentConfig.label}</h2>
              <p className="panel-copy">{currentConfig.lead}</p>
            </div>
          </div>

          <div className="import-upload-box">
            <strong>当前模板字段</strong>
            <p className="muted-text">{currentConfig.requiredFields.join("、")}</p>
            <label className="import-file-field">
              <span>选择 CSV 文件</span>
              <input
                accept=".csv,text/csv"
                onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                type="file"
              />
            </label>
            <p className="muted-text">
              {selectedFile ? `已选择文件：${selectedFile.name}` : "还没有选择文件，建议先下载模板再补数据。"}
            </p>
          </div>

          <div className="page-actions">
            <button className="button-secondary" disabled={downloadingTemplate} onClick={handleTemplateDownload} type="button">
              {downloadingTemplate ? "模板下载中..." : "下载模板"}
            </button>
            <button className="button" disabled={!selectedFile || submitting} onClick={handleImportSubmit} type="button">
              {submitting ? "导入执行中..." : "开始导入"}
            </button>
            <button
              className="ghost-button"
              onClick={() => {
                setSelectedFile(null);
                setResult(null);
                setMessage("");
                setError("");
              }}
              type="button"
            >
              清空本次结果
            </button>
          </div>
        </article>

        <article className="command-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Validation Notes</p>
              <h2>导入前要先过哪些门槛</h2>
            </div>
          </div>
          <div className="detail-list">
            {currentConfig.validationRules.map((rule) => (
              <div className="detail-item" key={rule}>
                <strong>校验规则</strong>
                <p>{rule}</p>
              </div>
            ))}
          </div>
        </article>
      </section>

      {result ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{result.total_count}</strong>
              <span className="metric-label">总行数</span>
              <p className="metric-detail">按表头以下的有效数据行统计，空白行会自动跳过。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{result.success_count}</strong>
              <span className="metric-label">成功写入</span>
              <p className="metric-detail">这些数据已经入库，刷新现有 CRM 聚合页面后会直接可见。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{result.failed_count}</strong>
              <span className="metric-label">失败行数</span>
              <p className="metric-detail">失败不会覆盖原数据，原因会逐行返回，方便修正后重传。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{result.inserted_keys.length ? result.inserted_keys.slice(0, 3).join("、") : "无"}</strong>
              <span className="metric-label">成功主键样例</span>
              <p className="metric-detail">这里展示最近一次成功写入的前几条业务主键，便于快速核对。</p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Import Summary</p>
                  <h2>这次导入结果</h2>
                </div>
                {result.failed_rows_csv ? (
                  <button className="button-secondary" onClick={handleFailedRowsDownload} type="button">
                    下载失败行 CSV
                  </button>
                ) : null}
              </div>
              <div className="summary-list">
                <div className="summary-item">
                  <strong>来源文件</strong>
                  <p>{result.file_name}</p>
                </div>
                <div className="summary-item">
                  <strong>成功写入主键</strong>
                  <p>{result.inserted_keys.length ? result.inserted_keys.join("、") : "本次没有成功写入的数据。"}</p>
                </div>
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">After Import</p>
                  <h2>导入后你可以马上验证什么</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>客户主档</strong>
                  <p>新客户导入后，会立刻进入客户详情聚合链路，后续风险快照和报告引用都能挂到同一个 customer_id。</p>
                </div>
                <div className="detail-item">
                  <strong>经营信号</strong>
                  <p>商机和跟进一旦入库，摘要看板、客户详情和报告按客户钻取就能消费这批数据。</p>
                </div>
              </div>
            </article>
          </section>

          {result.failures.length ? (
            <section className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Failed Rows</p>
                  <h2>失败行明细</h2>
                </div>
              </div>
              <div className="summary-list">
                {result.failures.map((failure) => (
                  <div className="summary-item" key={`${failure.row_no}-${failure.business_key || "empty"}`}>
                    <strong>
                      第 {failure.row_no} 行 {failure.business_key ? `· ${failure.business_key}` : ""}
                    </strong>
                    <p>{failure.reason}</p>
                  </div>
                ))}
              </div>
            </section>
          ) : (
            <EmptyCard
              text="本次没有失败行。"
              detail="说明模板字段、外键引用和权限范围都已经通过校验，可以继续做下一批数据导入。"
            />
          )}
        </>
      ) : null}
    </AppShell>
  );
}
