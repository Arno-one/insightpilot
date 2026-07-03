"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyCard, ErrorCard, LoadingCard } from "@/components/DataState";
import { AppShell } from "@/components/layout/AppShell";
import { apiFetch, getStoredUser, hasAnyPermission } from "@/lib/api";
import { formatDateTime } from "@/lib/presentation";
import styles from "./notifications.module.css";

type NotificationDelivery = {
  notification_id: string;
  task_id: string | null;
  approval_id: string | null;
  customer_id: string | null;
  recipient_user_id: string;
  sender_user_id: string;
  notification_type: string;
  channel: string;
  title: string;
  content: string;
  status: string;
  delivered_at: string | null;
  read_at: string | null;
  created_at: string;
  delivery_status: string;
  provider: string | null;
  provider_message_id: string | null;
  retry_count: number;
  last_attempted_at: string | null;
  next_retry_at: string | null;
  last_error: string | null;
  can_retry: boolean;
};

const NOTIFICATION_PERMISSIONS = [
  "task:read:self",
  "task:read:team",
  "task:read:all",
  "approval:review:agent_task"
];

const DELIVERY_STATUS_META: Record<
  string,
  {
    label: string;
    tone: "success" | "warning" | "danger" | "neutral";
  }
> = {
  failed: { label: "重试失败", tone: "danger" },
  fallback_internal: { label: "已回退站内通知", tone: "warning" },
  skipped: { label: "跳过邮件投递", tone: "warning" },
  sent: { label: "首次发送成功", tone: "success" },
  sent_after_retry: { label: "重试发送成功", tone: "success" }
};

function getDeliveryStatusMeta(status: string) {
  return DELIVERY_STATUS_META[status] || { label: status, tone: "neutral" as const };
}

function formatNotificationTime(value: string | null) {
  if (!value) {
    return "暂无";
  }
  return formatDateTime(value);
}

function trimSummary(text: string, maxLength = 10) {
  const value = text.trim();
  if (!value) {
    return "未命名通知";
  }
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

export default function NotificationsPage() {
  const currentUser = useMemo(() => getStoredUser(), []);
  const canAccess = useMemo(
    () => hasAnyPermission(currentUser, NOTIFICATION_PERMISSIONS),
    [currentUser]
  );
  const [items, setItems] = useState<NotificationDelivery[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<NotificationDelivery | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [message, setMessage] = useState("");

  async function loadFailedNotifications(nextSelectedId?: string) {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch<NotificationDelivery[]>("/api/notifications/failed");
      const nextItems = response.data;
      setItems(nextItems);
      setSelectedId((current) => {
        const preferredId = nextSelectedId ?? current;
        if (preferredId && nextItems.some((item) => item.notification_id === preferredId)) {
          return preferredId;
        }
        return nextItems[0]?.notification_id || "";
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "通知失败列表加载失败。");
      setItems([]);
      setSelectedId("");
    } finally {
      setLoading(false);
    }
  }

  async function loadNotificationDetail(notificationId: string) {
    if (!notificationId) {
      setDetail(null);
      return;
    }
    // 中文注释：列表先用失败列表数据秒开，详情再单独拉全量字段，避免右侧信息滞后。
    setDetailLoading(true);
    setDetailError("");
    try {
      const response = await apiFetch<NotificationDelivery>(`/api/notifications/${notificationId}`);
      setDetail(response.data);
    } catch (exc) {
      setDetail(null);
      setDetailError(exc instanceof Error ? exc.message : "通知详情加载失败。");
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleRetry() {
    if (!detail?.can_retry || retrying) {
      return;
    }
    setRetrying(true);
    setError("");
    setDetailError("");
    setMessage("");
    try {
      // 中文注释：手动重试成功后，同时刷新详情和失败列表；如果已补发成功，会自动从左侧失败列表移除。
      const response = await apiFetch<NotificationDelivery>(`/api/notifications/${detail.notification_id}/retry`, {
        method: "POST"
      });
      setDetail(response.data);
      setMessage(response.msg);
      await loadFailedNotifications(response.data.can_retry ? response.data.notification_id : undefined);
    } catch (exc) {
      setDetailError(exc instanceof Error ? exc.message : "通知重试失败。");
    } finally {
      setRetrying(false);
    }
  }

  useEffect(() => {
    if (!canAccess) {
      setLoading(false);
      return;
    }
    loadFailedNotifications();
  }, [canAccess]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError("");
      return;
    }
    loadNotificationDetail(selectedId);
  }, [selectedId]);

  const selectedStatusMeta = detail ? getDeliveryStatusMeta(detail.delivery_status) : null;

  return (
    <AppShell>
      {!canAccess ? (
        <ErrorCard
          message="当前账号暂未开放通知中心权限。"
          detail="请为当前席位补充任务读取或审批复核权限后再访问。"
        />
      ) : null}

      {canAccess ? (
        <section className="command-panel">
          <div className="section-eyebrow-row">
            <p className="eyebrow">Delivery Recovery</p>
            <div className="topbar-pills">
              <span className="info-pill">失败通知 {items.length}</span>
              <span className="info-pill">支持手动补发</span>
            </div>
          </div>
          <div className="panel-header">
            <h1 className={styles.pageTitle}>通知中心</h1>
            <p className="panel-copy">
              先把失败投递拉出来，再决定是否重新发送邮件，让任务、通知、日程这条动作链不丢单。
            </p>
          </div>
        </section>
      ) : null}

      {canAccess && loading ? (
        <LoadingCard text="正在加载失败通知..." detail="系统正在同步最近一批需要人工处理的投递记录。" />
      ) : null}

      {canAccess && !loading && error ? (
        <ErrorCard message={error} detail="可以稍后重试，或检查后端通知接口与登录态是否正常。" />
      ) : null}

      {canAccess && !loading && !error && !items.length ? (
        <EmptyCard
          text="当前没有失败通知。"
          detail="邮件投递与站内兜底都处于稳定状态，暂时不需要人工补发。"
        />
      ) : null}

      {canAccess && !loading && !error && items.length ? (
        <section className={`workspace-grid ${styles.notificationWorkspace}`}>
          <div className={`command-panel ${styles.notificationListPanel}`}>
            <div className="section-eyebrow-row">
              <p className="eyebrow">Failed Deliveries</p>
              <button className={`ghost-button ${styles.notificationRefreshButton}`} onClick={() => loadFailedNotifications()} type="button">
                刷新列表
              </button>
            </div>
            <div className={`card-stack ${styles.notificationList}`}>
              {items.map((item) => {
                const statusMeta = getDeliveryStatusMeta(item.delivery_status);
                const isActive = item.notification_id === selectedId;
                return (
                  <button
                    className={`${styles.notificationItem}${isActive ? ` ${styles.notificationItemActive}` : ""}`}
                    key={item.notification_id}
                    onClick={() => setSelectedId(item.notification_id)}
                    type="button"
                  >
                    <div className={styles.notificationItemHeader}>
                      <strong>{trimSummary(item.title)}</strong>
                      <span className={`meta-chip meta-chip-${statusMeta.tone}`}>{statusMeta.label}</span>
                    </div>
                    <p className={styles.notificationItemCopy}>{item.title}</p>
                    <div className={`meta-row ${styles.notificationMetaRow}`}>
                      <span>通知ID {item.notification_id}</span>
                      <span>重试 {item.retry_count} 次</span>
                    </div>
                    <div className={`meta-row ${styles.notificationMetaRow}`}>
                      <span>客户 {item.customer_id || "暂无"}</span>
                      <span>{formatNotificationTime(item.next_retry_at || item.last_attempted_at || item.created_at)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className={`command-panel ${styles.notificationDetailPanel}`}>
            {message ? <p className={`${styles.notificationFeedback} ${styles.notificationFeedbackSuccess}`}>{message}</p> : null}
            {detailError ? <p className={`${styles.notificationFeedback} ${styles.notificationFeedbackDanger}`}>{detailError}</p> : null}

            {detailLoading ? (
              <LoadingCard text="正在加载通知详情..." detail="准备展示这条通知的失败原因与补发上下文。" />
            ) : null}

            {!detailLoading && !detail ? (
              <EmptyCard text="请选择一条失败通知。" detail="左侧选中后，右侧会展示详情、错误原因与重试入口。" />
            ) : null}

            {!detailLoading && detail ? (
              <>
                <div className="section-eyebrow-row">
                  <p className="eyebrow">Notification Detail</p>
                  {selectedStatusMeta ? (
                    <span className={`meta-chip meta-chip-${selectedStatusMeta.tone}`}>{selectedStatusMeta.label}</span>
                  ) : null}
                </div>

                <div className={styles.notificationDetailHero}>
                  <div>
                    <h2 className={styles.notificationDetailTitle}>{detail.title}</h2>
                    <p className={styles.notificationDetailCopy}>{detail.content}</p>
                  </div>
                  <div className={styles.notificationDetailActions}>
                    <button
                      className="button-secondary"
                      disabled={!detail.can_retry || retrying}
                      onClick={handleRetry}
                      type="button"
                    >
                      {retrying ? "正在重试..." : detail.can_retry ? "重新执行当前通知" : "当前无需重试"}
                    </button>
                  </div>
                </div>

                <div className={styles.notificationDetailGrid}>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>通知 ID</span>
                    <strong>{detail.notification_id}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>任务 ID</span>
                    <strong>{detail.task_id || "暂无"}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>审批 ID</span>
                    <strong>{detail.approval_id || "暂无"}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>客户 ID</span>
                    <strong>{detail.customer_id || "暂无"}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>接收人</span>
                    <strong>{detail.recipient_user_id}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>发起人</span>
                    <strong>{detail.sender_user_id}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>投递通道</span>
                    <strong>{detail.channel}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>服务商</span>
                    <strong>{detail.provider || "平台内通知"}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>已重试次数</span>
                    <strong>{detail.retry_count}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>创建时间</span>
                    <strong>{formatNotificationTime(detail.created_at)}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>最近尝试</span>
                    <strong>{formatNotificationTime(detail.last_attempted_at)}</strong>
                  </div>
                  <div className={`detail-item ${styles.notificationDetailItem}`}>
                    <span>下次建议重试</span>
                    <strong>{formatNotificationTime(detail.next_retry_at)}</strong>
                  </div>
                </div>

                <div className={styles.notificationErrorBlock}>
                  <p className="eyebrow">Failure Reason</p>
                  <p>{detail.last_error || "当前没有错误信息，可能已经由站内通知兜底。"}</p>
                </div>
              </>
            ) : null}
          </div>
        </section>
      ) : null}
    </AppShell>
  );
}
