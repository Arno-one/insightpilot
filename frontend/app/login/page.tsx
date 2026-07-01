"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { getDefaultRoute, login, saveSession } from "@/lib/api";

const demoAccounts = [
  { label: "系统管理席位", username: "admin", password: "Admin@123456", note: "维护角色权限开关与用户角色分配。" },
  { label: "老板席位", username: "owner", password: "Owner@123456", note: "查看经营全景、日报与全局风险。" },
  { label: "主管席位", username: "manager", password: "Manager@123456", note: "审批 AI 任务并调度销售执行。" },
  { label: "销售席位", username: "sales01", password: "Sales@123456", note: "跟进自己的任务与客户动作。" }
];

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("manager");
  const [password, setPassword] = useState("Manager@123456");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // 中文注释：登录成功后直接根据权限跳到默认工作台，避免 admin 先落到无权限页面。
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const response = await login(username, password);
      saveSession(response.data);
      router.replace(getDefaultRoute(response.data.user));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "登录失败，请检查账号、密码或后端服务。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="auth-shell">
        <article className="auth-hero">
          <div className="auth-copy">
            <p className="eyebrow">Sales War Room</p>
            <h1 className="login-title">让经营动作不再埋在 CRM 的安静角落。</h1>
            <p className="lead">
              InsightPilot 会把报价后沉默、竞品介入、长期未跟进等弱信号拉到台前，再通过审批、任务与日报把建议推到执行闭环。
            </p>
          </div>

          <div className="auth-points">
            <div className="auth-point">
              <strong>风险信号前置</strong>
              <span>把“看起来没问题”的客户提前识别出来，不等商机冷掉才回头补救。</span>
            </div>
            <div className="auth-point">
              <strong>AI 建议有人把关</strong>
              <span>所有 AI 动作先进入主管审批，再转成正式销售任务，兼顾效率和安全感。</span>
            </div>
            <div className="auth-point">
              <strong>权限边界可随时调整</strong>
              <span>新增 admin 席位后，角色权限和用户角色分配都可以在系统管理页直接开关，不需要再手改数据库。</span>
            </div>
            <div className="auth-point">
              <strong>全链路可审计</strong>
              <span>从风险判断、RAG 证据到 Agent 节点耗时，关键决策都有可追踪的执行链路。</span>
            </div>
          </div>
        </article>

        <section className="login-card">
          <div>
            <p className="eyebrow">Access Node</p>
            <h2 className="section-title">登录 InsightPilot 指挥台</h2>
            <p className="panel-copy">选择一个演示席位，快速进入经营驾驶舱、审批台、系统管理、Trace 审计和 RAG 评估页面。</p>
          </div>

          <form className="login-form" onSubmit={handleSubmit}>
            <div className="login-field">
              <label htmlFor="username">账号</label>
              <input id="username" name="username" onChange={(event) => setUsername(event.target.value)} value={username} />
            </div>
            <div className="login-field">
              <label htmlFor="password">密码</label>
              <input
                id="password"
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                value={password}
              />
            </div>
            {error ? <p className="form-error">{error}</p> : null}
            <button className="button" disabled={submitting} type="submit">
              {submitting ? "正在接入指挥台..." : "进入工作台"}
            </button>
          </form>

          <div className="credential-grid">
            {demoAccounts.map((account) => (
              <button
                className="credential-card"
                key={account.username}
                onClick={() => {
                  setUsername(account.username);
                  setPassword(account.password);
                }}
                type="button"
              >
                <div>
                  <strong>{account.label}</strong>
                  <span>{account.note}</span>
                </div>
                <small>{account.username}</small>
              </button>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
