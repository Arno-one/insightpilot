"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch } from "@/lib/api";

type Permission = {
  permission_id: string;
  permission_code: string;
  permission_name: string;
  module: string;
  action: string;
  description: string | null;
};

type Role = {
  role_id: string;
  role_code: string;
  role_name: string;
  status: number;
  remark: string | null;
  permission_codes: string[];
};

type User = {
  user_id: string;
  username: string;
  real_name: string;
  status: number;
  role_ids: string[];
  role_codes: string[];
  role_names: string[];
};

type AccessControlData = {
  roles: Role[];
  permissions: Permission[];
  users: User[];
};

function sortValues(values: string[]) {
  return [...values].sort((left, right) => left.localeCompare(right, "zh-CN"));
}

export default function AccessControlPage() {
  const [data, setData] = useState<AccessControlData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [savingKey, setSavingKey] = useState("");
  const [rolePermissionDrafts, setRolePermissionDrafts] = useState<Record<string, string[]>>({});
  const [userRoleDrafts, setUserRoleDrafts] = useState<Record<string, string[]>>({});

  async function loadAccessControl() {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<AccessControlData>("/api/system/access-control");
      setData(response.data);
      setRolePermissionDrafts(
        Object.fromEntries(response.data.roles.map((role) => [role.role_id, sortValues(role.permission_codes)]))
      );
      setUserRoleDrafts(Object.fromEntries(response.data.users.map((user) => [user.user_id, [...user.role_ids]])));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "系统权限配置加载失败。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAccessControl();
  }, []);

  const permissionGroups = useMemo(() => {
    if (!data) {
      return [];
    }
    const grouped = new Map<string, Permission[]>();
    for (const permission of data.permissions) {
      const items = grouped.get(permission.module) || [];
      items.push(permission);
      grouped.set(permission.module, items);
    }
    return [...grouped.entries()].map(([module, permissions]) => ({
      module,
      permissions,
    }));
  }, [data]);

  const adminCount = useMemo(() => {
    return data?.users.filter((user) => user.role_codes.includes("admin")).length || 0;
  }, [data]);

  function toggleRolePermission(roleId: string, permissionCode: string) {
    setRolePermissionDrafts((current) => {
      const nextValues = new Set(current[roleId] || []);
      if (nextValues.has(permissionCode)) {
        nextValues.delete(permissionCode);
      } else {
        nextValues.add(permissionCode);
      }
      return {
        ...current,
        [roleId]: sortValues([...nextValues]),
      };
    });
  }

  function toggleUserRole(userId: string, roleId: string) {
    setUserRoleDrafts((current) => {
      const nextValues = new Set(current[userId] || []);
      if (nextValues.has(roleId)) {
        nextValues.delete(roleId);
      } else {
        nextValues.add(roleId);
      }
      return {
        ...current,
        [userId]: [...nextValues],
      };
    });
  }

  // 中文注释：角色和用户分开逐块保存，避免一次操作把整张权限矩阵全部重写。
  async function saveRolePermissions(role: Role) {
    setSavingKey(`role:${role.role_id}`);
    setMessage("");
    setError("");
    try {
      await apiFetch(`/api/system/roles/${role.role_id}/permissions`, {
        method: "PATCH",
        body: JSON.stringify({
          permission_codes: rolePermissionDrafts[role.role_id] || [],
        }),
      });
      setMessage(`角色「${role.role_name}」的权限开关已更新。`);
      await loadAccessControl();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "角色权限更新失败。");
    } finally {
      setSavingKey("");
    }
  }

  async function saveUserRoles(user: User) {
    setSavingKey(`user:${user.user_id}`);
    setMessage("");
    setError("");
    try {
      await apiFetch(`/api/system/users/${user.user_id}/roles`, {
        method: "PATCH",
        body: JSON.stringify({
          role_ids: userRoleDrafts[user.user_id] || [],
        }),
      });
      setMessage(`用户「${user.real_name}」的角色分配已更新。`);
      await loadAccessControl();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "用户角色更新失败。");
    } finally {
      setSavingKey("");
    }
  }

  return (
    <AppShell>
      <section className="page-hero">
        <div>
          <p className="eyebrow">Access Control</p>
          <h1>把权限边界交给系统管理，而不是继续手改数据库。</h1>
          <p className="lead">
            admin 角色可以在这里统一维护“哪个角色能看什么、做什么”，也能直接调整每个账号挂在哪个角色下面。
          </p>
        </div>
      </section>

      {message ? <p className="success-text">{message}</p> : null}
      {error ? <ErrorCard message={error} detail="请确认 admin 权限、系统管理接口与数据库连接状态。" /> : null}
      {loading ? <LoadingCard detail="正在同步角色、权限点与用户角色分配矩阵。" /> : null}
      {!loading && !data && !error ? (
        <EmptyCard text="当前没有可展示的权限数据。" detail="请先确认权限种子数据是否已经初始化完成。" />
      ) : null}

      {data ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <strong className="metric-value">{data.roles.length}</strong>
              <span className="metric-label">角色数量</span>
              <p className="metric-detail">当前租户下所有启用中的系统角色。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{data.permissions.length}</strong>
              <span className="metric-label">权限点数量</span>
              <p className="metric-detail">这些权限点会决定每个页面、接口和业务动作是否可访问。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{data.users.length}</strong>
              <span className="metric-label">账号数量</span>
              <p className="metric-detail">可以直接在本页调整每个账号挂载的角色集合。</p>
            </article>
            <article className="metric-card">
              <strong className="metric-value">{adminCount}</strong>
              <span className="metric-label">admin 账号</span>
              <p className="metric-detail">系统会兜底保证至少保留一个 admin，避免彻底锁死权限管理入口。</p>
            </article>
          </section>

          <section className="workspace-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Role Strategy</p>
                  <h2>角色权限建议这样维护</h2>
                </div>
              </div>
              <div className="detail-list">
                <div className="detail-item">
                  <strong>先定角色职责，再开功能权限</strong>
                  <p>角色应该表达岗位职责，不要为了某一个临时需求把权限点胡乱堆到同一个角色里。</p>
                </div>
                <div className="detail-item">
                  <strong>主管和老板的权限边界要清楚</strong>
                  <p>当前团队和全局范围在部分列表里仍是同租户视角，后续如果补组织架构，这里会是最重要的收口点。</p>
                </div>
                <div className="detail-item">
                  <strong>admin 只做权限治理，不直接掺业务</strong>
                  <p>这样既方便运维，也能避免系统管理账号混入真实业务链路，导致审计口径变乱。</p>
                </div>
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Governance Reminder</p>
                  <h2>本页负责两件事</h2>
                </div>
              </div>
              <div className="summary-list">
                <div className="summary-item">
                  <strong>角色权限开关</strong>
                  <p>例如某个角色能不能看审批、能不能跑日报、能不能看 Agent Trace，都可以在角色维度统一切换。</p>
                </div>
                <div className="summary-item">
                  <strong>用户角色分配</strong>
                  <p>账号和角色脱钩后，未来新增主管、调整销售负责人时，只改分配关系就够了，不用再碰代码。</p>
                </div>
              </div>
            </article>
          </section>

          <section className="system-grid">
            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Role Permission Matrix</p>
                  <h2>角色权限开关</h2>
                </div>
              </div>

              <div className="card-stack">
                {data.roles.map((role) => (
                  <article className="task-card" key={role.role_id}>
                    <div className="task-card-header">
                      <div>
                        <p className="eyebrow">{role.role_code}</p>
                        <h3 className="section-title">{role.role_name}</h3>
                        <p className="panel-copy">{role.remark || "当前角色暂无补充说明。"}</p>
                      </div>
                      <div className="meta-row">
                        <span className="meta-chip">已启用权限 {rolePermissionDrafts[role.role_id]?.length || 0}</span>
                      </div>
                    </div>

                    <div className="permission-module-list">
                      {permissionGroups.map((group) => (
                        <section className="permission-module" key={`${role.role_id}-${group.module}`}>
                          <div>
                            <strong>{group.module.toUpperCase()}</strong>
                            <p className="panel-copy">按模块集中配置，避免一个角色的权限点散得太乱。</p>
                          </div>
                          <div className="toggle-grid">
                            {group.permissions.map((permission) => {
                              const checked = (rolePermissionDrafts[role.role_id] || []).includes(permission.permission_code);
                              return (
                                <label className="toggle-item" key={`${role.role_id}-${permission.permission_code}`}>
                                  <input
                                    checked={checked}
                                    onChange={() => toggleRolePermission(role.role_id, permission.permission_code)}
                                    type="checkbox"
                                  />
                                  <div>
                                    <strong>{permission.permission_name}</strong>
                                    <span>{permission.permission_code}</span>
                                    <small>{permission.description || `${permission.module} / ${permission.action}`}</small>
                                  </div>
                                </label>
                              );
                            })}
                          </div>
                        </section>
                      ))}
                    </div>

                    <div className="action-row">
                      <button
                        className="button"
                        disabled={savingKey === `role:${role.role_id}`}
                        onClick={() => saveRolePermissions(role)}
                        type="button"
                      >
                        保存角色权限
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </article>

            <article className="command-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">User Role Mapping</p>
                  <h2>用户角色分配</h2>
                </div>
              </div>

              <div className="card-stack">
                {data.users.map((user) => (
                  <article className="approval-card" key={user.user_id}>
                    <div className="approval-card-header">
                      <div>
                        <p className="eyebrow">{user.username}</p>
                        <h3 className="section-title">{user.real_name}</h3>
                      </div>
                      <div className="meta-row">
                        <span className="meta-chip">当前角色 {user.role_names.join(" / ")}</span>
                      </div>
                    </div>

                    <div className="toggle-grid">
                      {data.roles.map((role) => {
                        const checked = (userRoleDrafts[user.user_id] || []).includes(role.role_id);
                        return (
                          <label className="toggle-item" key={`${user.user_id}-${role.role_id}`}>
                            <input
                              checked={checked}
                              onChange={() => toggleUserRole(user.user_id, role.role_id)}
                              type="checkbox"
                            />
                            <div>
                              <strong>{role.role_name}</strong>
                              <span>{role.role_code}</span>
                              <small>{role.remark || "暂无说明"}</small>
                            </div>
                          </label>
                        );
                      })}
                    </div>

                    <div className="action-row">
                      <button
                        className="button-secondary"
                        disabled={savingKey === `user:${user.user_id}`}
                        onClick={() => saveUserRoles(user)}
                        type="button"
                      >
                        保存用户角色
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
