"use client";

import { useMemo, useState } from "react";

import { ErrorCard, EmptyCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";
import { formatPercent } from "@/lib/presentation";

type EvalCase = {
  case_id: string;
  question: string;
  expected_doc_id: string;
  expected_section_id: string;
  hit: boolean;
  rank: number | null;
  trace_id: string;
};

type EvalResult = {
  top_k: number;
  case_count: number;
  hit_count: number;
  recall_at_k: number;
  mrr: number;
  ndcg: number;
  duration_ms: number;
  details: EvalCase[];
};

function qualityText(result: EvalResult | null) {
  if (!result) {
    return "等待评估";
  }
  if (result.recall_at_k >= 0.8) {
    return "检索质量较强";
  }
  if (result.recall_at_k >= 0.6) {
    return "检索质量可用";
  }
  return "需要继续调优";
}

export default function RagEvaluationPage() {
  const [result, setResult] = useState<EvalResult | null>(null);
  const [limit, setLimit] = useState(10);
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runEvaluation() {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<EvalResult>("/api/rag/evaluate", {
        method: "POST",
        body: JSON.stringify({ top_k: topK, limit, enable_rerank: true })
      });
      setResult(response.data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "RAG 评估失败，请确认 Milvus 已完成入库并且服务可访问。");
    } finally {
      setLoading(false);
    }
  }

  // 中文注释：命中率是给非算法角色看的“直觉指标”，方便演示时快速解释当前检索质量。
  const hitRate = useMemo(() => (result ? result.hit_count / result.case_count : 0), [result]);

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Retrieval Quality</p>
          <h1>RAG 不是“感觉命中了”就算好，要用指标把检索质量讲明白。</h1>
          <p className="lead">这一页用 QA 样本集跑 Recall@K、MRR 和 NDCG，避免知识库只在主观体验上看起来可用。</p>
        </div>
      </section>

      <section className="eval-control-bar">
        <label htmlFor="topK">
          Top K
          <input id="topK" max={20} min={1} onChange={(event) => setTopK(Number(event.target.value))} type="number" value={topK} />
        </label>
        <label htmlFor="limit">
          样本数量
          <input id="limit" max={100} min={1} onChange={(event) => setLimit(Number(event.target.value))} type="number" value={limit} />
        </label>
        <button className="button" disabled={loading} onClick={runEvaluation} type="button">
          {loading ? "评估运行中..." : "运行 RAG 评估"}
        </button>
      </section>

      {error ? <ErrorCard message={error} detail="如果这是第一次跑，请确认向量库已连接、文档已入库、评估数据可读。" /> : null}
      {loading ? <LoadingCard detail="正在对样本问题做检索评估并计算指标。" /> : null}
      {!loading && !result && !error ? (
        <EmptyCard
          text="点击上方按钮后，这里会生成当前知识库的检索质量结果。"
          detail="建议先保持默认参数跑一轮，再根据结果逐步调 TopK、重排和知识库内容。"
        />
      ) : null}

      {result ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{formatPercent(result.recall_at_k)}</strong>
              <span className="metric-label">Recall@{result.top_k}</span>
              <p className="metric-detail">目标文档在前 {result.top_k} 条结果内被召回的比例。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{result.mrr.toFixed(3)}</strong>
              <span className="metric-label">MRR</span>
              <p className="metric-detail">正确答案越靠前，MRR 越高，代表用户越容易第一眼命中需要的内容。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{result.ndcg.toFixed(3)}</strong>
              <span className="metric-label">NDCG</span>
              <p className="metric-detail">不只看是否命中，还看命中的排序质量是否合理。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{result.duration_ms} ms</strong>
              <span className="metric-label">评估耗时</span>
              <p className="metric-detail">
                命中 {result.hit_count}/{result.case_count} 条样本，整体命中率 {formatPercent(hitRate)}。
              </p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel eval-scoreband">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Quality Reading</p>
                  <h2>{qualityText(result)}</h2>
                </div>
              </div>
              <p className="panel-copy">
                当前 Recall@{result.top_k} 为 {formatPercent(result.recall_at_k)}。如果想继续提升，优先回看文档切片质量、查询重写策略和重排效果。
              </p>
              <div className="scorebar" aria-hidden="true">
                <div className="scorebar-fill" style={{ width: `${Math.min(result.recall_at_k * 100, 100)}%` }} />
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Interpretation Guide</p>
                  <h2>如何读这三个指标</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>Recall@K 看有没有找到</strong>
                  <p>如果 Recall 太低，优先怀疑文档切片、召回范围或向量入库本身有问题。</p>
                </div>
                <div className="detail-item">
                  <strong>MRR 看找得够不够靠前</strong>
                  <p>如果 Recall 不低但 MRR 不高，说明目标文档虽然能被找出来，但排序还不够理想。</p>
                </div>
                <div className="detail-item">
                  <strong>NDCG 看整体排序质量</strong>
                  <p>它更适合拿来比较不同检索策略或重排策略之间的优劣。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="eval-case-list">
            {result.details.map((item) => (
              <article className="eval-case-card" key={item.case_id}>
                <div className="report-card-header">
                  <div>
                    <p className="eyebrow">Case {item.case_id}</p>
                    <h2 className="section-title">{item.question}</h2>
                  </div>
                  <div className="case-meta">
                    <span className={`pill ${item.hit ? "tone-success" : "tone-danger"}`}>
                      {item.hit ? `命中 #${item.rank}` : "未命中"}
                    </span>
                  </div>
                </div>

                <div className="meta-row">
                  <span className="meta-chip">
                    期望来源 {item.expected_doc_id}/{item.expected_section_id}
                  </span>
                  <span className="meta-chip">Trace {item.trace_id}</span>
                </div>
              </article>
            ))}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
