"use client";

import { ChangeEvent, useMemo, useState } from "react";

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
  fieldGuides: Array<{
    key: string;
    formatExample?: string;
    enumOptions?: string[];
    note?: string;
    aliases?: string[];
  }>;
  validationRules: string[];
};

type RetryRow = {
  id: string;
  originalRowNo: number;
  originalReason: string;
  rowData: Record<string, string>;
};

type FilePrecheck = {
  sourceHeaders: string[];
  mappedHeaders: Record<string, string>;
  missingRequiredFields: string[];
  unmappedSourceHeaders: string[];
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
    fieldGuides: [
      { key: "customer_id", formatExample: "cust_001", note: "建议使用稳定业务主键，避免后续重复导入时难以识别。", aliases: ["客户ID", "客户编号", "customer_no"] },
      { key: "customer_name", formatExample: "上海云帆科技", aliases: ["客户名称", "客户名", "name"] },
      { key: "owner_user_id", formatExample: "u_sales_001", note: "必须是系统内已启用用户。", aliases: ["负责人", "负责人ID", "销售ID", "owner_id"] },
      { key: "lifecycle_stage", enumOptions: ["new_lead", "communicated", "solution", "quotation", "won", "lost"], aliases: ["客户阶段", "生命周期", "stage"] },
      { key: "intent_level", enumOptions: ["low", "medium", "high"], aliases: ["意向等级", "意向级别", "intent"] },
      { key: "customer_level", enumOptions: ["A", "B", "C"], aliases: ["客户等级", "客户分级", "level"] },
      { key: "industry", formatExample: "软件服务", aliases: ["行业"] },
      { key: "region", formatExample: "上海", aliases: ["地区", "区域", "城市"] },
      { key: "next_follow_up_at", formatExample: "2026-07-20 10:00:00", note: "时间格式使用 YYYY-MM-DD HH:MM:SS。", aliases: ["下次跟进时间", "下次联系时间", "next_follow_time"] },
      { key: "remark", formatExample: "客户已进入报价阶段，等待下周复盘。", aliases: ["备注", "说明", "comment"] }
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
    fieldGuides: [
      { key: "deal_id", formatExample: "deal_001", aliases: ["商机ID", "商机编号", "opportunity_id"] },
      { key: "customer_id", formatExample: "cust_001", aliases: ["客户ID", "客户编号", "customer_no"] },
      { key: "owner_user_id", formatExample: "u_sales_001", aliases: ["负责人", "销售ID", "owner_id"] },
      { key: "deal_name", formatExample: "华东区试点项目", aliases: ["商机名称", "项目名称", "opportunity_name"] },
      { key: "stage", enumOptions: ["communicated", "solution", "quotation", "won", "lost"], aliases: ["商机阶段", "阶段"] },
      { key: "amount", formatExample: "88000", note: "金额字段使用纯数字，不要带千分位逗号或货币符号。", aliases: ["金额", "预计金额", "deal_amount"] },
      { key: "quote_amount", formatExample: "92000", aliases: ["报价金额", "最新报价", "quote"] },
      { key: "quoted_at", formatExample: "2026-07-02 09:30:00", note: "时间格式使用 YYYY-MM-DD HH:MM:SS。", aliases: ["报价时间", "quoted_time"] },
      { key: "expected_close_at", formatExample: "2026-07-31", note: "日期格式使用 YYYY-MM-DD。", aliases: ["预计关闭日期", "预计成交日期", "expected_close_date"] },
      { key: "close_result", enumOptions: ["open", "won", "lost"], aliases: ["关闭结果", "成交结果", "status_result"] }
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
    fieldGuides: [
      { key: "follow_up_id", formatExample: "fu_001", aliases: ["跟进ID", "记录ID", "followup_id"] },
      { key: "customer_id", formatExample: "cust_001", aliases: ["客户ID", "客户编号", "customer_no"] },
      { key: "deal_id", formatExample: "deal_001", note: "允许为空，但如果有值，必须属于同一个客户。", aliases: ["商机ID", "项目ID", "opportunity_id"] },
      { key: "owner_user_id", formatExample: "u_sales_001", aliases: ["负责人", "销售ID", "owner_id"] },
      { key: "follow_up_type", enumOptions: ["phone", "wechat", "meeting", "email"], aliases: ["跟进方式", "联系渠道", "contact_type"] },
      { key: "content", formatExample: "客户确认下周继续推进试点范围。", aliases: ["跟进内容", "沟通内容", "record_content"] },
      { key: "sentiment", enumOptions: ["positive", "neutral", "negative"], aliases: ["客户情绪", "情绪判断", "emotion"] },
      { key: "next_action", formatExample: "整理试点清单并确认参会人", aliases: ["下一步动作", "待办动作", "action"] },
      { key: "next_follow_up_at", formatExample: "2026-07-12 15:00:00", note: "时间格式使用 YYYY-MM-DD HH:MM:SS。", aliases: ["下次跟进时间", "下次联系时间", "next_follow_time"] },
      { key: "occurred_at", formatExample: "2026-07-02 11:00:00", note: "时间格式使用 YYYY-MM-DD HH:MM:SS。", aliases: ["发生时间", "跟进时间", "occurred_time"] }
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

function buildCsvContent(headers: string[], rows: Record<string, string>[]) {
  // 中文注释：二次导入仍然走现有 CSV 接口，所以这里把页面里的修正值重新拼回标准 CSV 文本。
  const escapeCsvCell = (value: string) => {
    if (value.includes(",") || value.includes("\"") || value.includes("\n")) {
      return `"${value.replaceAll("\"", "\"\"")}"`;
    }
    return value;
  };

  const lines = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => escapeCsvCell(row[header] || "")).join(","))
  ];
  return lines.join("\n");
}

function normalizeHeader(value: string) {
  return value
    .replace(/^\ufeff/, "")
    .trim()
    .toLowerCase()
    .replace(/[\s\-（）()\/\\]/g, "")
    .replace(/_/g, "");
}

function parseCsvContent(content: string) {
  const rows: string[][] = [];
  let currentCell = "";
  let currentRow: string[] = [];
  let inQuotes = false;

  for (let index = 0; index < content.length; index += 1) {
    const char = content[index];
    const nextChar = content[index + 1];

    if (char === "\"") {
      if (inQuotes && nextChar === "\"") {
        currentCell += "\"";
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      currentRow.push(currentCell);
      currentCell = "";
      continue;
    }

    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && nextChar === "\n") {
        index += 1;
      }
      currentRow.push(currentCell);
      currentCell = "";
      if (currentRow.some((cell) => cell.length > 0)) {
        rows.push(currentRow);
      }
      currentRow = [];
      continue;
    }

    currentCell += char;
  }

  if (currentCell.length > 0 || currentRow.length > 0) {
    currentRow.push(currentCell);
    if (currentRow.some((cell) => cell.length > 0)) {
      rows.push(currentRow);
    }
  }

  if (!rows.length) {
    return { headers: [], rows: [] as Record<string, string>[] };
  }

  const headers = rows[0].map((cell) => cell.replace(/^\ufeff/, "").trim());
  const dataRows = rows.slice(1)
    .map((row) =>
      Object.fromEntries(
        headers.map((header, index) => [header, (row[index] || "").trim()])
      )
    )
    .filter((row) => Object.values(row).some((value) => value !== ""));

  return {
    headers,
    rows: dataRows
  };
}

function buildHeaderMapping(config: ImportConfig, sourceHeaders: string[]) {
  const aliasDictionary = new Map<string, string>();
  for (const field of config.fieldGuides) {
    aliasDictionary.set(normalizeHeader(field.key), field.key);
    for (const alias of field.aliases || []) {
      aliasDictionary.set(normalizeHeader(alias), field.key);
    }
  }

  const usedTargets = new Set<string>();
  const mappedHeaders: Record<string, string> = {};

  for (const header of sourceHeaders) {
    const target = aliasDictionary.get(normalizeHeader(header));
    if (target && !usedTargets.has(target)) {
      mappedHeaders[header] = target;
      usedTargets.add(target);
    }
  }

  return mappedHeaders;
}

function finalizeFilePrecheck(config: ImportConfig, sourceHeaders: string[], mappedHeaders: Record<string, string>): FilePrecheck {
  const resolvedFields = new Set(Object.values(mappedHeaders));
  return {
    sourceHeaders,
    mappedHeaders,
    missingRequiredFields: config.requiredFields.filter((field) => !resolvedFields.has(field)),
    unmappedSourceHeaders: sourceHeaders.filter((header) => !mappedHeaders[header])
  };
}

async function buildNormalizedCsvFile(file: File, config: ImportConfig, mappedHeaders: Record<string, string>) {
  const parsed = parseCsvContent(await file.text());
  const normalizedRows = parsed.rows.map((row) =>
    Object.fromEntries(
      config.requiredFields.map((targetField) => {
        const sourceHeader = Object.entries(mappedHeaders).find(([, mappedField]) => mappedField === targetField)?.[0];
        return [targetField, sourceHeader ? row[sourceHeader] || "" : ""];
      })
    )
  );

  const csvContent = buildCsvContent(config.requiredFields, normalizedRows);
  return new File([`\ufeff${csvContent}`], `${config.key}_normalized.csv`, {
    type: "text/csv;charset=utf-8"
  });
}

function createRetryRows(failures: ImportFailure[]) {
  return failures.map((failure, index) => ({
    id: `${failure.row_no}-${failure.business_key || "empty"}-${index}`,
    originalRowNo: failure.row_no,
    originalReason: failure.reason,
    rowData: { ...failure.row_data }
  }));
}

export default function ImportsPage() {
  const [selectedEntity, setSelectedEntity] = useState<ImportEntity>("customer");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [filePrecheck, setFilePrecheck] = useState<FilePrecheck | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [retryRows, setRetryRows] = useState<RetryRow[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const [retrySubmitting, setRetrySubmitting] = useState(false);

  const currentConfig = useMemo(
    () => importConfigs.find((item) => item.key === selectedEntity) || importConfigs[0],
    [selectedEntity]
  );

  const retryHeaders = currentConfig.requiredFields;
  const mappingOptions = useMemo(
    () => currentConfig.fieldGuides.map((field) => ({ value: field.key, label: field.key })),
    [currentConfig]
  );

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setResult(null);
    setRetryRows([]);
    setMessage("");

    if (!file) {
      setFilePrecheck(null);
      return;
    }

    try {
      // 中文注释：预检只看表头，不占用后端接口，目的是让用户在点击导入前先看到缺什么、格式该怎么填。
      const parsed = parseCsvContent(await file.text());
      const mappedHeaders = buildHeaderMapping(currentConfig, parsed.headers);
      setFilePrecheck(finalizeFilePrecheck(currentConfig, parsed.headers, mappedHeaders));
      setError("");
    } catch {
      setFilePrecheck(null);
      setError("文件预检失败，请确认 CSV 编码和内容是否正常。");
    }
  }

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
    if (filePrecheck?.missingRequiredFields.length) {
      setError(`仍缺少必填字段映射：${filePrecheck.missingRequiredFields.join("、")}`);
      return;
    }

    setSubmitting(true);
    setMessage("");
    setError("");

    try {
      const normalizedFile = filePrecheck
        ? await buildNormalizedCsvFile(selectedFile, currentConfig, filePrecheck.mappedHeaders)
        : selectedFile;
      const formData = new FormData();
      formData.append("file", normalizedFile);

      const response = await apiFetch<ImportResult>(`/api/crm/import/${selectedEntity}`, {
        method: "POST",
        body: formData
      });

      setResult(response.data);
      setRetryRows(createRetryRows(response.data.failures));
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

  function handleRetryRowsDownload() {
    if (!retryRows.length) {
      return;
    }
    const csvContent = buildCsvContent(
      retryHeaders,
      retryRows.map((item) => item.rowData)
    );
    const blob = new Blob(["\ufeff", csvContent], { type: "text/csv;charset=utf-8" });
    saveBlob(blob, `${selectedEntity}_retry_rows.csv`);
  }

  function handleRetryFieldChange(rowId: string, field: string, event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    const value = event.target.value;
    setRetryRows((currentRows) =>
      currentRows.map((row) => (row.id === rowId ? { ...row, rowData: { ...row.rowData, [field]: value } } : row))
    );
  }

  function handleRemoveRetryRow(rowId: string) {
    setRetryRows((currentRows) => currentRows.filter((row) => row.id !== rowId));
  }

  async function handleRetryImportSubmit() {
    if (!retryRows.length) {
      setError("当前没有可重新导入的失败行。");
      return;
    }

    setRetrySubmitting(true);
    setMessage("");
    setError("");

    try {
      const csvContent = buildCsvContent(
        retryHeaders,
        retryRows.map((item) => item.rowData)
      );
      // 中文注释：这里不额外发明“重试接口”，而是前端生成一个临时 CSV 文件，再复用现有导入链路。
      const retryFile = new File([`\ufeff${csvContent}`], `${selectedEntity}_retry.csv`, {
        type: "text/csv;charset=utf-8"
      });
      const formData = new FormData();
      formData.append("file", retryFile);

      const response = await apiFetch<ImportResult>(`/api/crm/import/${selectedEntity}`, {
        method: "POST",
        body: formData
      });

      setResult(response.data);
      setRetryRows(createRetryRows(response.data.failures));
      setMessage(
        `失败行二次导入已执行：共 ${response.data.total_count} 行，成功 ${response.data.success_count} 行，失败 ${response.data.failed_count} 行。`
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "失败行二次导入失败。");
    } finally {
      setRetrySubmitting(false);
    }
  }

  function handleEntityChange(entity: ImportEntity) {
    setSelectedEntity(entity);
    setSelectedFile(null);
    setFilePrecheck(null);
    setResult(null);
    setRetryRows([]);
    setMessage("");
    setError("");
  }

  function handleHeaderMappingChange(sourceHeader: string, targetField: string) {
    if (!filePrecheck) {
      return;
    }

    const nextMappings = Object.fromEntries(
      Object.entries(filePrecheck.mappedHeaders).filter(([header]) => header !== sourceHeader)
    );

    if (targetField) {
      for (const [header, mappedField] of Object.entries(nextMappings)) {
        if (mappedField === targetField) {
          delete nextMappings[header];
        }
      }
      nextMappings[sourceHeader] = targetField;
    }

    setFilePrecheck(finalizeFilePrecheck(currentConfig, filePrecheck.sourceHeaders, nextMappings));
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
                onChange={handleFileChange}
                type="file"
              />
            </label>
            <p className="muted-text">
              {selectedFile ? `已选择文件：${selectedFile.name}` : "还没有选择文件，建议先下载模板再补数据。"}
            </p>
            {filePrecheck ? (
              <div className="import-precheck-box">
                <strong>上传前预检</strong>
                <div className="detail-list">
                  <div className="detail-item">
                    <strong>识别到的表头</strong>
                    <p>{filePrecheck.sourceHeaders.length ? filePrecheck.sourceHeaders.join("、") : "当前没有识别到有效表头。"}</p>
                  </div>
                  <div className="detail-item">
                    <strong>缺失标准字段</strong>
                    <p>{filePrecheck.missingRequiredFields.length ? filePrecheck.missingRequiredFields.join("、") : "没有缺失字段映射，可以直接继续导入。"}</p>
                  </div>
                  <div className="detail-item">
                    <strong>未映射原始表头</strong>
                    <p>{filePrecheck.unmappedSourceHeaders.length ? filePrecheck.unmappedSourceHeaders.join("、") : "所有识别到的表头都已完成映射。"}</p>
                  </div>
                </div>
                <div className="mapping-grid">
                  {filePrecheck.sourceHeaders.map((header) => (
                    <label className="mapping-field" key={`mapping-${header}`}>
                      <span>{header}</span>
                      <select
                        className="input-like mapping-select"
                        onChange={(event) => handleHeaderMappingChange(header, event.target.value)}
                        value={filePrecheck.mappedHeaders[header] || ""}
                      >
                        <option value="">忽略该列</option>
                        {mappingOptions.map((option) => (
                          <option key={`${header}-${option.value}`} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
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
                setFilePrecheck(null);
                setResult(null);
                setRetryRows([]);
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

      <section className="workspace-grid">
        <article className="command-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Format Examples</p>
              <h2>字段格式示例</h2>
            </div>
          </div>
          <div className="detail-list">
            {currentConfig.fieldGuides.map((field) => (
              <div className="detail-item" key={`format-${field.key}`}>
                <strong>{field.key}</strong>
                <p>{field.formatExample ? `示例：${field.formatExample}` : "当前字段没有固定格式示例。"}</p>
                {field.note ? <p>{field.note}</p> : null}
              </div>
            ))}
          </div>
        </article>

        <article className="command-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Enum Options</p>
              <h2>枚举可选值提示</h2>
            </div>
          </div>
          <div className="detail-list">
            {currentConfig.fieldGuides
              .filter((field) => field.enumOptions?.length)
              .map((field) => (
                <div className="detail-item" key={`enum-${field.key}`}>
                  <strong>{field.key}</strong>
                  <p>{field.enumOptions?.join("、")}</p>
                </div>
              ))}
            {!currentConfig.fieldGuides.some((field) => field.enumOptions?.length) ? (
              <div className="detail-item">
                <strong>当前没有枚举字段</strong>
                <p>这一类导入目前不需要固定枚举值。</p>
              </div>
            ) : null}
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
            <>
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

              <section className="command-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Retry Import</p>
                    <h2>修正失败行后再次导入</h2>
                    <p className="panel-copy">
                      这里直接复用本次失败行作为草稿，改完后会重新生成一份 CSV，并继续走现有导入接口。
                    </p>
                  </div>
                  <div className="page-actions">
                    <button className="button-secondary" onClick={handleRetryRowsDownload} type="button" disabled={!retryRows.length}>
                      下载当前修正版
                    </button>
                    <button className="button" onClick={handleRetryImportSubmit} type="button" disabled={!retryRows.length || retrySubmitting}>
                      {retrySubmitting ? "二次导入中..." : "重新导入失败行"}
                    </button>
                  </div>
                </div>

                <div className="retry-stack">
                  {retryRows.map((row, index) => (
                    <article className="retry-row-card" key={row.id}>
                      <div className="panel-header">
                        <div>
                          <strong>修正草稿 {index + 1}</strong>
                          <p className="panel-copy">原始失败行：第 {row.originalRowNo} 行；失败原因：{row.originalReason}</p>
                        </div>
                        <button className="ghost-button" onClick={() => handleRemoveRetryRow(row.id)} type="button">
                          移除这一行
                        </button>
                      </div>

                      <div className="retry-field-grid">
                        {retryHeaders.map((field) => {
                          const value = row.rowData[field] || "";
                          const useTextarea = field === "content" || field === "remark";
                          return (
                            <label className="retry-field" key={`${row.id}-${field}`}>
                              <span>{field}</span>
                              {useTextarea ? (
                                <textarea
                                  className="input-like textarea-like retry-textarea"
                                  onChange={(event) => handleRetryFieldChange(row.id, field, event)}
                                  value={value}
                                />
                              ) : (
                                <input
                                  className="input-like retry-input"
                                  onChange={(event) => handleRetryFieldChange(row.id, field, event)}
                                  value={value}
                                />
                              )}
                            </label>
                          );
                        })}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            </>
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
