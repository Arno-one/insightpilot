import { ReactNode } from "react";

type StateCardProps = {
  title: string;
  text: string;
  tone: "loading" | "error" | "empty";
  detail?: string;
  action?: ReactNode;
};

function StateCard({ title, text, tone, detail, action }: StateCardProps) {
  // 中文注释：统一加载、报错、空状态的视觉骨架，避免每个页面各写一套提示卡。
  return (
    <section className={`state-card state-card-${tone}`}>
      <div className="state-badge" aria-hidden="true">
        {tone === "loading" ? "..." : tone === "error" ? "!!" : "//"}
      </div>
      <div className="state-copy">
        <p className="eyebrow">{title}</p>
        <h3>{text}</h3>
        {detail ? <p className="state-detail">{detail}</p> : null}
      </div>
      {action ? <div className="state-action">{action}</div> : null}
    </section>
  );
}

export function LoadingCard({ text = "正在同步实时数据...", detail }: { text?: string; detail?: string }) {
  return <StateCard detail={detail} text={text} title="系统载入中" tone="loading" />;
}

export function ErrorCard({ message, detail }: { message: string; detail?: string }) {
  return <StateCard detail={detail} text={message} title="链路告警" tone="error" />;
}

export function EmptyCard({ text = "当前还没有可展示的数据。", detail }: { text?: string; detail?: string }) {
  return <StateCard detail={detail} text={text} title="等待信号" tone="empty" />;
}
