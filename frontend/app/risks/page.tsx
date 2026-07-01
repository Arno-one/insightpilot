import { AppShell } from "@/components/layout/AppShell";

export default function RisksPage() {
  return (
    <AppShell>
      <p className="eyebrow">Risk center</p>
      <h1>客户风险中心</h1>
      <p className="lead">这里将展示风险分、规则命中、RAG 来源和 AI 建议。</p>
    </AppShell>
  );
}
