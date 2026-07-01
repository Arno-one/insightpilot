export function LoadingCard({ text = "正在读取实时数据..." }: { text?: string }) {
  return <div className="card wide">{text}</div>;
}

export function ErrorCard({ message }: { message: string }) {
  return <div className="card wide danger-text">{message}</div>;
}

export function EmptyCard({ text = "暂无数据" }: { text?: string }) {
  return <div className="card wide muted-text">{text}</div>;
}
