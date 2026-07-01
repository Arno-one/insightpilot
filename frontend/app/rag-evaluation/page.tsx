"use client";

import { useState } from "react";

import { ErrorCard, EmptyCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

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
      setError(exc instanceof Error ? exc.message : "RAG 评估失败，请确认 Milvus 已入库并可访问");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Retrieval quality</p>
          <h1>RAG 评估</h1>
          <p className="lead">用 QA 数据集抽样评估检索质量，输出 Recall@K、MRR 和 NDCG，避免只靠主观感觉调 RAG。</p>
        </div>
      </section>

      <div className="eval-controls">
        <label>
          TopK
          <input min={1} max={20} onChange={(event) => setTopK(Number(event.target.value))} type="number" value={topK} />
        </label>
        <label>
          样本数
          <input min={1} max={100} onChange={(event) => setLimit(Number(event.target.value))} type="number" value={limit} />
        </label>
        <button className="button" disabled={loading} onClick={runEvaluation} type="button">
          {loading ? "评估中..." : "运行评估"}
        </button>
      </div>

      {error ? <ErrorCard message={error} /> : null}
      {!result && !error ? <EmptyCard text="点击运行评估后，这里会展示检索质量指标。" /> : null}
      {result ? (
        <>
          <section className="grid">
            <div className="card">
              <strong>{result.recall_at_k}</strong>
              <span>Recall@{result.top_k}</span>
            </div>
            <div className="card">
              <strong>{result.mrr}</strong>
              <span>MRR</span>
            </div>
            <div className="card">
              <strong>{result.ndcg}</strong>
              <span>NDCG</span>
            </div>
            <div className="card">
              <strong>{result.hit_count}/{result.case_count}</strong>
              <span>{result.duration_ms} ms</span>
            </div>
          </section>

          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>问题</th>
                  <th>期望来源</th>
                  <th>结果</th>
                  <th>Trace</th>
                </tr>
              </thead>
              <tbody>
                {result.details.map((item) => (
                  <tr key={item.case_id}>
                    <td>{item.case_id}</td>
                    <td>{item.question}</td>
                    <td>{item.expected_doc_id}/{item.expected_section_id}</td>
                    <td>
                      <span className={`pill ${item.hit ? "" : "pill-danger"}`}>
                        {item.hit ? `命中 #${item.rank}` : "未命中"}
                      </span>
                    </td>
                    <td>{item.trace_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}
