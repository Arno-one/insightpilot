"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { login, saveSession } from "@/lib/api";

const demoAccounts = [
  { label: "老板", username: "owner", password: "Owner@123456" },
  { label: "销售主管", username: "manager", password: "Manager@123456" },
  { label: "销售员", username: "sales01", password: "Sales@123456" }
];

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("manager");
  const [password, setPassword] = useState("Manager@123456");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const response = await login(username, password);
      saveSession(response.data);
      router.replace("/dashboard");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "登录失败，请检查账号和后端服务");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <p className="eyebrow">AI Operating Copilot</p>
        <h1 className="login-title">登录 InsightPilot</h1>
        <p className="lead">使用演示账号进入经营驾驶舱，查看客户风险、AI 审批和 Agent 执行链路。</p>
        <form onSubmit={handleSubmit}>
          <input name="username" onChange={(event) => setUsername(event.target.value)} placeholder="账号" value={username} />
          <input name="password" onChange={(event) => setPassword(event.target.value)} placeholder="密码" type="password" value={password} />
          {error ? <p className="form-error">{error}</p> : null}
          <button className="button" disabled={submitting} style={{ marginTop: 18, width: "100%" }} type="submit">
            {submitting ? "正在登录..." : "进入工作台"}
          </button>
        </form>
        <div className="demo-row">
          {demoAccounts.map((account) => (
            <button
              key={account.username}
              onClick={() => {
                setUsername(account.username);
                setPassword(account.password);
              }}
              type="button"
            >
              {account.label}
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
