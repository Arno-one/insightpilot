export default function LoginPage() {
  return (
    <main className="login-page">
      <section className="login-card">
        <p className="eyebrow">AI Operating Copilot</p>
        <h1 style={{ fontSize: 48 }}>登录 InsightPilot</h1>
        <p className="lead">使用演示账号进入经营驾驶舱，查看客户风险、AI 审批和 Agent 执行链路。</p>
        <form>
          <input name="username" placeholder="账号，例如 owner" />
          <input name="password" placeholder="密码，例如 Owner@123456" type="password" />
          <button className="button" style={{ marginTop: 18, width: "100%" }} type="button">
            进入工作台
          </button>
        </form>
      </section>
    </main>
  );
}
