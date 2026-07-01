import { AppShell } from "@/components/layout/AppShell";

export default function AgentTracePage() {
  return (
    <AppShell>
      <p className="eyebrow">Trace</p>
      <h1>Agent 执行追踪</h1>
      <p className="lead">这里会展示 LangGraph 节点、工具调用、权限校验、RAG 命中和耗时 trace。</p>
    </AppShell>
  );
}
