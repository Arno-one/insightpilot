import { AppShell } from "@/components/layout/AppShell";

export default function ApprovalsPage() {
  return (
    <AppShell>
      <p className="eyebrow">Human in the loop</p>
      <h1>AI 任务审批台</h1>
      <p className="lead">AI 只生成任务草稿，主管确认后才创建正式销售任务。</p>
    </AppShell>
  );
}
