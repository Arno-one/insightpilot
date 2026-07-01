"use client";

import { useEffect, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

type AgentRun = {
  run_id: string;
  user_id: string;
  run_type: string;
  graph_name: string;
  status: string;
  total_duration_ms: number;
  started_at: string | null;
  finished_at: string | null;
};

type AgentStep = {
  step_id: string;
  node_name: string;
  tool_name: string | null;
  input_json: unknown;
  output_json: unknown;
  status: string;
  error_message: string | null;
  duration_ms: number;
  started_at: string | null;
  finished_at: string | null;
};

type RagHit = {
  hit_id: string;
  source_type: string;
  doc_id: string;
  section_id: string | null;
  rank_no: number;
  rrf_score: number | null;
  text_preview: string | null;
};

type RagTrace = {
  trace_id: string;
  original_query: string;
  rewritten_query: string | null;
  strategy: string;
  total_ms: number;
  hit_count: number;
  hits: RagHit[];
};

type RunDetail = {
  run: AgentRun & {
    input_json: unknown;
    output_json: unknown;
    error_message: string | null;
  };
  steps: AgentStep[];
  rag_traces: RagTrace[];
};

function prettyJson(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "{}";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

export default function AgentTracePage() {
  const [items, setItems] = useState<AgentRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadRuns() {
      try {
        const response = await apiFetch<AgentRun[]>("/api/agent/runs");
        setItems(response.data);
        if (response.data[0]) {
          setSelectedRunId(response.data[0].run_id);
        }
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Agent 执行记录加载失败");
      } finally {
        setLoading(false);
      }
    }
    loadRuns();
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    async function loadDetail() {
      setDetailLoading(true);
      setError("");
      try {
        const response = await apiFetch<RunDetail>(`/api/agent/runs/${selectedRunId}`);
        setDetail(response.data);
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Agent 详情加载失败");
      } finally {
        setDetailLoading(false);
      }
    }
    loadDetail();
  }, [selectedRunId]);

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Trace</p>
          <h1>Agent 执行追踪</h1>
          <p className="lead">把 Agent Run、节点耗时、工具输出和 RAG 命中串成一条可审计链路。</p>
        </div>
      </section>
      {error ? <ErrorCard message={error} /> : null}
      {loading ? <LoadingCard /> : null}
      {!loading && !items.length && !error ? <EmptyCard text="暂无 Agent 执行记录。" /> : null}
      {items.length ? (
        <section className="trace-layout">
          <div className="run-list">
            {items.map((item) => (
              <button
                className={`run-item ${item.run_id === selectedRunId ? "selected" : ""}`}
                key={item.run_id}
                onClick={() => setSelectedRunId(item.run_id)}
                type="button"
              >
                <span className="pill">{item.status}</span>
                <strong>{item.run_type}</strong>
                <small>{item.run_id}</small>
                <small>{item.total_duration_ms} ms · {item.user_id}</small>
              </button>
            ))}
          </div>

          <div className="trace-detail">
            {detailLoading ? <LoadingCard text="正在读取 Agent 审计链路..." /> : null}
            {detail ? (
              <>
                <div className="trace-summary">
                  <div>
                    <p className="eyebrow">{detail.run.graph_name}</p>
                    <h2>{detail.run.run_type}</h2>
                    <p>{detail.run.run_id}</p>
                  </div>
                  <span className="pill">{detail.run.status}</span>
                </div>

                <div className="timeline">
                  {detail.steps.map((step, index) => (
                    <article className="step-card" key={step.step_id}>
                      <div className="step-index">{index + 1}</div>
                      <div>
                        <div className="step-title">
                          <h3>{step.node_name}</h3>
                          <span className="pill">{step.status}</span>
                        </div>
                        <p>{step.tool_name || "无工具调用"} · {step.duration_ms} ms</p>
                        {step.error_message ? <p className="danger-text">{step.error_message}</p> : null}
                        <details>
                          <summary>查看输出 JSON</summary>
                          <pre>{prettyJson(step.output_json)}</pre>
                        </details>
                      </div>
                    </article>
                  ))}
                </div>

                <section className="rag-trace-panel">
                  <div className="section-heading">
                    <p className="eyebrow">RAG Evidence</p>
                    <strong>{detail.rag_traces.length} 条检索链路</strong>
                  </div>
                  {!detail.rag_traces.length ? <p className="muted-text">当前 Run 未关联 RAG 检索。</p> : null}
                  {detail.rag_traces.map((trace) => (
                    <article className="rag-trace-card" key={trace.trace_id}>
                      <div>
                        <strong>{trace.trace_id}</strong>
                        <p>{trace.original_query}</p>
                        <small>{trace.strategy} · {trace.total_ms} ms · {trace.hit_count} hits</small>
                      </div>
                      <div className="hit-list">
                        {trace.hits.map((hit) => (
                          <div className="hit-item" key={hit.hit_id}>
                            <span>#{hit.rank_no}</span>
                            <strong>{hit.doc_id}/{hit.section_id || "-"}</strong>
                            <p>{hit.text_preview}</p>
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </section>
              </>
            ) : null}
          </div>
        </section>
      ) : null}
    </AppShell>
  );
}
