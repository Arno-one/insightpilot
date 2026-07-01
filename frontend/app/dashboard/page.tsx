import { AppShell } from "@/components/layout/AppShell";

export default function DashboardPage() {
  return (
    <AppShell>
      <section className="hero">
        <p className="eyebrow">Command room</p>
        <h1>把 CRM 里的沉默信号，变成今天就能执行的动作。</h1>
        <p className="lead">
          InsightPilot 会识别报价后无回应、竞品介入、长期未跟进等风险，并把 Agent 建议送入主管审批流。
        </p>
      </section>

      <section className="grid">
        <div className="card">
          <strong className="danger">3</strong>
          <span>今日高风险客户</span>
        </div>
        <div className="card">
          <strong>7</strong>
          <span>有效跟进记录</span>
        </div>
        <div className="card">
          <strong>4</strong>
          <span>待确认 AI 任务</span>
        </div>
        <div className="card">
          <strong>12</strong>
          <span>活跃商机</span>
        </div>
        <div className="card wide">
          <p className="eyebrow">今日经营摘要</p>
          <span>
            报价阶段出现多个客户沉默信号，瑞成集团、北桥医疗、星河教育建议主管优先介入。
          </span>
        </div>
        <div className="card wide">
          <p className="eyebrow">Agent next move</p>
          <span>
            下一步将接入 LangGraph 风险分析图：读取 CRM 数据、规则打分、RAG 检索、生成审批草稿。
          </span>
        </div>
      </section>
    </AppShell>
  );
}
