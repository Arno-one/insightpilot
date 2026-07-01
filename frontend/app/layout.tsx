import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "InsightPilot",
  description: "面向销售运营场景的企业级 AI 运营参谋与风险闭环指挥台"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
