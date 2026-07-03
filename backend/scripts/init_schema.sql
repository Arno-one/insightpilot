CREATE DATABASE IF NOT EXISTS insightpilot DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE insightpilot;

CREATE TABLE IF NOT EXISTS tenant (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '租户业务主键，V1 默认使用 demo_tenant',
  tenant_name VARCHAR(100) NOT NULL COMMENT '租户名称，用于前端展示和演示数据区分',
  status TINYINT NOT NULL DEFAULT 1 COMMENT '租户状态：1 启用，0 停用',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户表，V1 仅启用单租户 demo_tenant';

CREATE TABLE IF NOT EXISTS sys_user (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  user_id VARCHAR(64) NOT NULL COMMENT '用户业务主键',
  username VARCHAR(64) NOT NULL COMMENT '登录账号',
  password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希，使用 PBKDF2 形式保存',
  real_name VARCHAR(80) NOT NULL COMMENT '用户真实姓名',
  phone VARCHAR(30) NULL COMMENT '手机号',
  email VARCHAR(120) NULL COMMENT '邮箱',
  status TINYINT NOT NULL DEFAULT 1 COMMENT '用户状态：1 启用，0 停用',
  is_deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除标记：0 未删除，1 已删除',
  last_login_at DATETIME NULL COMMENT '最后登录时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_tenant_username (tenant_id, username),
  UNIQUE KEY uk_user_id (user_id),
  KEY idx_tenant_status (tenant_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统用户表';

CREATE TABLE IF NOT EXISTS sys_role (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  role_id VARCHAR(64) NOT NULL COMMENT '角色业务主键',
  role_code VARCHAR(50) NOT NULL COMMENT '角色编码，例如 owner / manager / salesperson',
  role_name VARCHAR(80) NOT NULL COMMENT '角色名称',
  status TINYINT NOT NULL DEFAULT 1 COMMENT '角色状态：1 启用，0 停用',
  remark VARCHAR(255) NULL COMMENT '角色说明',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_tenant_role_code (tenant_id, role_code),
  UNIQUE KEY uk_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色表';

CREATE TABLE IF NOT EXISTS sys_permission (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  permission_id VARCHAR(64) NOT NULL COMMENT '权限业务主键',
  permission_code VARCHAR(100) NOT NULL COMMENT '权限编码',
  permission_name VARCHAR(100) NOT NULL COMMENT '权限名称',
  module VARCHAR(50) NOT NULL COMMENT '所属模块，例如 crm / task / agent',
  action VARCHAR(50) NOT NULL COMMENT '动作，例如 read / run / review',
  description VARCHAR(255) NULL COMMENT '权限说明',
  status TINYINT NOT NULL DEFAULT 1 COMMENT '权限状态：1 启用，0 停用',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_permission_id (permission_id),
  UNIQUE KEY uk_permission_code (permission_code),
  KEY idx_permission_module (module)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限点表';

CREATE TABLE IF NOT EXISTS sys_user_role (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  user_id VARCHAR(64) NOT NULL COMMENT '用户业务主键',
  role_id VARCHAR(64) NOT NULL COMMENT '角色业务主键',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_user_role (tenant_id, user_id, role_id),
  KEY idx_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户角色关联表';

CREATE TABLE IF NOT EXISTS sys_role_permission (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  role_id VARCHAR(64) NOT NULL COMMENT '角色业务主键',
  permission_id VARCHAR(64) NOT NULL COMMENT '权限业务主键',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_role_permission (tenant_id, role_id, permission_id),
  KEY idx_permission_id (permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色权限关联表';

CREATE TABLE IF NOT EXISTS crm_customer (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  customer_id VARCHAR(64) NOT NULL COMMENT '客户业务主键',
  customer_name VARCHAR(150) NOT NULL COMMENT '客户名称',
  owner_user_id VARCHAR(64) NOT NULL COMMENT '当前负责人用户 ID',
  industry VARCHAR(80) NULL COMMENT '所属行业',
  region VARCHAR(80) NULL COMMENT '所在区域',
  source VARCHAR(50) NULL COMMENT '客户来源',
  lifecycle_stage VARCHAR(30) NOT NULL COMMENT '客户生命周期阶段',
  intent_level VARCHAR(20) NOT NULL DEFAULT 'medium' COMMENT '意向等级：low / medium / high',
  customer_level VARCHAR(20) NOT NULL DEFAULT 'B' COMMENT '客户分级：A / B / C',
  company_size VARCHAR(50) NULL COMMENT '企业规模描述',
  budget_min DECIMAL(12,2) NULL COMMENT '预算下限',
  budget_max DECIMAL(12,2) NULL COMMENT '预算上限',
  expected_purchase_at DATE NULL COMMENT '预计采购日期',
  decision_maker_status VARCHAR(30) NOT NULL DEFAULT 'unknown' COMMENT '决策人状态：unknown / identified / confirmed',
  competitor_involved TINYINT NOT NULL DEFAULT 0 COMMENT '是否已出现竞品介入：1 是，0 否',
  next_follow_up_at DATETIME NULL COMMENT '下一次跟进时间',
  last_follow_up_at DATETIME NULL COMMENT '最近一次跟进时间',
  last_sentiment VARCHAR(20) NOT NULL DEFAULT 'neutral' COMMENT '最近一次客户情绪：positive / neutral / negative',
  lost_reason VARCHAR(255) NULL COMMENT '流失原因',
  remark TEXT NULL COMMENT '补充备注',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_customer_id (customer_id),
  KEY idx_tenant_owner (tenant_id, owner_user_id),
  KEY idx_tenant_stage (tenant_id, lifecycle_stage),
  KEY idx_tenant_last_follow (tenant_id, last_follow_up_at),
  KEY idx_tenant_competitor (tenant_id, competitor_involved)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户主表';

CREATE TABLE IF NOT EXISTS crm_contact (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  contact_id VARCHAR(64) NOT NULL COMMENT '联系人业务主键',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  contact_name VARCHAR(80) NOT NULL COMMENT '联系人姓名',
  title VARCHAR(80) NULL COMMENT '联系人职位',
  phone VARCHAR(30) NULL COMMENT '联系人手机号',
  email VARCHAR(120) NULL COMMENT '联系人邮箱',
  wechat VARCHAR(80) NULL COMMENT '联系人微信',
  is_decision_maker TINYINT NOT NULL DEFAULT 0 COMMENT '是否为决策人：1 是，0 否',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_contact_id (contact_id),
  KEY idx_tenant_customer (tenant_id, customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户联系人表';

CREATE TABLE IF NOT EXISTS crm_deal (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  deal_id VARCHAR(64) NOT NULL COMMENT '商机业务主键',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  owner_user_id VARCHAR(64) NOT NULL COMMENT '当前负责人用户 ID',
  deal_name VARCHAR(150) NOT NULL COMMENT '商机名称',
  stage VARCHAR(30) NOT NULL COMMENT '商机阶段',
  amount DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '预估成交金额',
  quote_amount DECIMAL(12,2) NULL COMMENT '最新报价金额',
  quoted_at DATETIME NULL COMMENT '最近报价时间',
  expected_close_at DATE NULL COMMENT '预计关闭日期',
  closed_at DATETIME NULL COMMENT '实际关闭时间',
  close_result VARCHAR(20) NOT NULL DEFAULT 'open' COMMENT '关闭结果：open / won / lost',
  lost_reason VARCHAR(255) NULL COMMENT '输单原因',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_deal_id (deal_id),
  KEY idx_tenant_customer (tenant_id, customer_id),
  KEY idx_tenant_owner_stage (tenant_id, owner_user_id, stage),
  KEY idx_tenant_quoted_at (tenant_id, quoted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商机表';

CREATE TABLE IF NOT EXISTS crm_follow_up_record (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  follow_up_id VARCHAR(64) NOT NULL COMMENT '跟进记录业务主键',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  deal_id VARCHAR(64) NULL COMMENT '关联商机 ID',
  owner_user_id VARCHAR(64) NOT NULL COMMENT '记录所属销售 ID',
  follow_up_type VARCHAR(30) NOT NULL COMMENT '跟进方式，例如 phone / wechat / meeting / email',
  content TEXT NOT NULL COMMENT '跟进内容原文',
  sentiment VARCHAR(20) NOT NULL DEFAULT 'neutral' COMMENT '本次跟进情绪判断：positive / neutral / negative',
  customer_feedback VARCHAR(255) NULL COMMENT '客户反馈摘要',
  next_action VARCHAR(255) NULL COMMENT '建议的下一步动作',
  next_follow_up_at DATETIME NULL COMMENT '建议的下一次跟进时间',
  occurred_at DATETIME NOT NULL COMMENT '跟进发生时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_follow_up_id (follow_up_id),
  KEY idx_tenant_customer_time (tenant_id, customer_id, occurred_at),
  KEY idx_tenant_owner_time (tenant_id, owner_user_id, occurred_at),
  KEY idx_tenant_sentiment (tenant_id, sentiment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户跟进记录表';

CREATE TABLE IF NOT EXISTS customer_risk_snapshot (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  risk_snapshot_id VARCHAR(64) NOT NULL COMMENT '风险快照业务主键',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  deal_id VARCHAR(64) NULL COMMENT '关联商机 ID',
  owner_user_id VARCHAR(64) NOT NULL COMMENT '当前负责人用户 ID',
  risk_score INT NOT NULL COMMENT '风险分',
  risk_level VARCHAR(20) NOT NULL COMMENT '风险等级：low / medium / high',
  rule_hits_json JSON NULL COMMENT '命中规则明细 JSON',
  evidence_json JSON NULL COMMENT '风险证据 JSON',
  llm_reason TEXT NULL COMMENT 'LLM 生成的风险解释',
  llm_suggestion TEXT NULL COMMENT 'LLM 生成的处理建议',
  suggested_task_json JSON NULL COMMENT '建议任务草稿 JSON',
  status VARCHAR(30) NOT NULL DEFAULT 'pending_review' COMMENT '处理状态，例如 pending_review / approved / ignored',
  generated_by_run_id VARCHAR(64) NULL COMMENT '生成该快照的 Agent Run ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_risk_snapshot_id (risk_snapshot_id),
  KEY idx_tenant_customer (tenant_id, customer_id),
  KEY idx_tenant_level_score (tenant_id, risk_level, risk_score),
  KEY idx_tenant_status (tenant_id, status),
  KEY idx_generated_run (generated_by_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户风险快照表';

CREATE TABLE IF NOT EXISTS risk_rule_config (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  rule_code VARCHAR(80) NOT NULL COMMENT '规则编码',
  rule_name VARCHAR(120) NOT NULL COMMENT '规则名称',
  rule_type VARCHAR(50) NOT NULL COMMENT '规则类型',
  score_weight INT NOT NULL COMMENT '风险分权重',
  threshold_json JSON NULL COMMENT '规则阈值配置 JSON',
  enabled TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用：1 是，0 否',
  version VARCHAR(30) NOT NULL DEFAULT 'v1' COMMENT '规则版本',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_tenant_rule (tenant_id, rule_code, version),
  KEY idx_tenant_enabled (tenant_id, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='风险规则配置表，V1 先以内置规则为主';

CREATE TABLE IF NOT EXISTS approval_record (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  approval_id VARCHAR(64) NOT NULL COMMENT '审批业务主键',
  approval_type VARCHAR(50) NOT NULL COMMENT '审批类型，例如 agent_task_draft',
  run_id VARCHAR(64) NULL COMMENT '来源 Agent Run ID',
  risk_snapshot_id VARCHAR(64) NULL COMMENT '关联风险快照 ID',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  proposed_payload_json JSON NOT NULL COMMENT '待审批 payload JSON',
  status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '审批状态：pending / approved / rejected',
  requested_by_user_id VARCHAR(64) NOT NULL COMMENT '发起审批的用户 ID',
  reviewer_user_id VARCHAR(64) NULL COMMENT '审批人用户 ID',
  reviewed_at DATETIME NULL COMMENT '审批时间',
  review_comment VARCHAR(500) NULL COMMENT '审批意见',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_approval_id (approval_id),
  KEY idx_tenant_status (tenant_id, status),
  KEY idx_tenant_reviewer (tenant_id, reviewer_user_id),
  KEY idx_risk_snapshot (risk_snapshot_id),
  KEY idx_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人工审批记录表';

CREATE TABLE IF NOT EXISTS sales_task (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  task_id VARCHAR(64) NOT NULL COMMENT '任务业务主键',
  approval_id VARCHAR(64) NULL COMMENT '来源审批 ID',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  deal_id VARCHAR(64) NULL COMMENT '关联商机 ID',
  assignee_user_id VARCHAR(64) NOT NULL COMMENT '任务执行人用户 ID',
  creator_user_id VARCHAR(64) NOT NULL COMMENT '任务创建人用户 ID',
  task_type VARCHAR(50) NOT NULL COMMENT '任务类型',
  title VARCHAR(150) NOT NULL COMMENT '任务标题',
  description TEXT NULL COMMENT '任务说明',
  recommended_script TEXT NULL COMMENT '建议话术',
  priority VARCHAR(20) NOT NULL DEFAULT 'medium' COMMENT '优先级：low / medium / high / urgent',
  status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending / in_progress / completed / cancelled',
  due_at DATETIME NULL COMMENT '截止时间',
  completed_at DATETIME NULL COMMENT '完成时间',
  result_note TEXT NULL COMMENT '执行结果备注',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_task_id (task_id),
  KEY idx_tenant_assignee_status (tenant_id, assignee_user_id, status),
  KEY idx_tenant_customer (tenant_id, customer_id),
  KEY idx_tenant_due (tenant_id, due_at),
  KEY idx_approval_id (approval_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售任务表';

CREATE TABLE IF NOT EXISTS internal_notification (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  notification_id VARCHAR(64) NOT NULL COMMENT '通知业务主键',
  task_id VARCHAR(64) NOT NULL COMMENT '关联任务 ID',
  approval_id VARCHAR(64) NULL COMMENT '关联审批 ID',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  recipient_user_id VARCHAR(64) NOT NULL COMMENT '接收人用户 ID',
  sender_user_id VARCHAR(64) NOT NULL COMMENT '发送人用户 ID',
  notification_type VARCHAR(50) NOT NULL COMMENT '通知类型，例如 task_assignment',
  channel VARCHAR(30) NOT NULL DEFAULT 'internal' COMMENT '通知通道，例如 internal / wecom / email',
  title VARCHAR(150) NOT NULL COMMENT '通知标题',
  content TEXT NOT NULL COMMENT '通知正文',
  status VARCHAR(30) NOT NULL DEFAULT 'sent' COMMENT '通知状态，例如 sent / failed / read',
  delivered_at DATETIME NULL COMMENT '送达时间',
  read_at DATETIME NULL COMMENT '阅读时间',
  delivery_status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '邮件投递状态，例如 pending / sent / failed / fallback_internal / skipped',
  provider VARCHAR(30) NULL COMMENT '外部投递提供方，例如 smtp',
  provider_message_id VARCHAR(128) NULL COMMENT '外部投递消息 ID',
  retry_count INT NOT NULL DEFAULT 0 COMMENT '邮件投递累计尝试次数',
  last_attempted_at DATETIME NULL COMMENT '最近一次外部投递尝试时间',
  next_retry_at DATETIME NULL COMMENT '建议下次重试时间',
  last_error TEXT NULL COMMENT '最近一次外部投递错误信息',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_notification_id (notification_id),
  UNIQUE KEY uk_task_recipient_type (tenant_id, task_id, recipient_user_id, notification_type),
  KEY idx_tenant_recipient_status (tenant_id, recipient_user_id, status),
  KEY idx_tenant_task (tenant_id, task_id),
  KEY idx_tenant_customer (tenant_id, customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='平台内通知记录表';

CREATE TABLE IF NOT EXISTS internal_calendar_event (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  event_id VARCHAR(64) NOT NULL COMMENT '日程业务主键',
  task_id VARCHAR(64) NOT NULL COMMENT '关联任务 ID',
  approval_id VARCHAR(64) NULL COMMENT '关联审批 ID',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  owner_user_id VARCHAR(64) NOT NULL COMMENT '日程负责人用户 ID',
  title VARCHAR(150) NOT NULL COMMENT '日程标题',
  description TEXT NULL COMMENT '日程说明',
  start_at DATETIME NOT NULL COMMENT '开始时间',
  end_at DATETIME NOT NULL COMMENT '结束时间',
  status VARCHAR(30) NOT NULL DEFAULT 'scheduled' COMMENT '日程状态，例如 scheduled / done / cancelled',
  created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建人用户 ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_event_id (event_id),
  UNIQUE KEY uk_task_owner (tenant_id, task_id, owner_user_id),
  KEY idx_tenant_owner_start (tenant_id, owner_user_id, start_at),
  KEY idx_tenant_task (tenant_id, task_id),
  KEY idx_tenant_customer (tenant_id, customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='平台内日程记录表';

CREATE TABLE IF NOT EXISTS approval_task_event (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  event_id VARCHAR(64) NOT NULL COMMENT '事件业务主键',
  entity_type VARCHAR(20) NOT NULL COMMENT '事件主体类型：approval / task',
  entity_id VARCHAR(64) NOT NULL COMMENT '事件主体业务 ID',
  approval_id VARCHAR(64) NULL COMMENT '关联审批 ID',
  task_id VARCHAR(64) NULL COMMENT '关联任务 ID',
  customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
  risk_snapshot_id VARCHAR(64) NULL COMMENT '关联风险快照 ID',
  action_type VARCHAR(50) NOT NULL COMMENT '动作类型，例如 approval_created / task_completed',
  operator_user_id VARCHAR(64) NOT NULL COMMENT '操作人用户 ID',
  note TEXT NULL COMMENT '动作说明或备注',
  detail_json JSON NULL COMMENT '动作补充细节 JSON',
  happened_at DATETIME NOT NULL COMMENT '动作发生时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_event_id (event_id),
  KEY idx_tenant_customer_time (tenant_id, customer_id, happened_at),
  KEY idx_tenant_approval_time (tenant_id, approval_id, happened_at),
  KEY idx_tenant_task_time (tenant_id, task_id, happened_at),
  KEY idx_tenant_entity_time (tenant_id, entity_type, entity_id, happened_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='审批与任务关键动作留痕表';

CREATE TABLE IF NOT EXISTS agent_run (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  run_id VARCHAR(64) NOT NULL COMMENT 'Agent Run 业务主键',
  user_id VARCHAR(64) NOT NULL COMMENT '触发用户 ID',
  run_type VARCHAR(50) NOT NULL COMMENT '运行类型，例如 risk_analysis / business_report',
  graph_name VARCHAR(80) NOT NULL COMMENT '图名称',
  input_json JSON NULL COMMENT '运行输入 JSON',
  output_json JSON NULL COMMENT '运行输出 JSON',
  status VARCHAR(30) NOT NULL COMMENT '运行状态：running / success / failed / awaiting_approval',
  error_message TEXT NULL COMMENT '错误信息',
  started_at DATETIME NULL COMMENT '开始时间',
  finished_at DATETIME NULL COMMENT '结束时间',
  total_duration_ms INT NOT NULL DEFAULT 0 COMMENT '总耗时（毫秒）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_run_id (run_id),
  KEY idx_tenant_user (tenant_id, user_id),
  KEY idx_tenant_type_status (tenant_id, run_type, status),
  KEY idx_tenant_started (tenant_id, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent 执行记录表';

CREATE TABLE IF NOT EXISTS agent_step (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  step_id VARCHAR(64) NOT NULL COMMENT '步骤业务主键',
  run_id VARCHAR(64) NOT NULL COMMENT '所属 Agent Run ID',
  node_name VARCHAR(80) NOT NULL COMMENT '节点名称',
  tool_name VARCHAR(80) NULL COMMENT '调用工具名称',
  required_permissions_json JSON NULL COMMENT '该节点要求的权限 JSON',
  input_json JSON NULL COMMENT '节点输入 JSON',
  output_json JSON NULL COMMENT '节点输出 JSON',
  status VARCHAR(30) NOT NULL COMMENT '节点状态：success / failed / skipped',
  error_message TEXT NULL COMMENT '错误信息',
  started_at DATETIME NULL COMMENT '开始时间',
  finished_at DATETIME NULL COMMENT '结束时间',
  duration_ms INT NOT NULL DEFAULT 0 COMMENT '耗时（毫秒）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_step_id (step_id),
  KEY idx_run_id (run_id),
  KEY idx_tenant_node (tenant_id, node_name),
  KEY idx_tenant_tool (tenant_id, tool_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent 节点执行记录表';

CREATE TABLE IF NOT EXISTS customer_memory (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '���ݿ���������',
  tenant_id VARCHAR(64) NOT NULL COMMENT '�����⻧ ID',
  memory_id VARCHAR(64) NOT NULL COMMENT '�ͻ�����ҵ������',
  customer_id VARCHAR(64) NOT NULL COMMENT '�����ͻ� ID',
  memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer' COMMENT '���䷶Χ��V1 �̶�Ϊ customer',
  summary_text TEXT NOT NULL COMMENT '�� Planner / Reviewer ֱ�����ѵ�ѹ��������ժҪ',
  summary_json JSON NULL COMMENT '�ṹ���ͻ����� JSON',
  source_run_id VARCHAR(64) NULL COMMENT '���һ�θ�����ü���� Agent Run ID',
  last_compiled_at DATETIME NOT NULL COMMENT '���һ�α����ͻ������ʱ��',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '����ʱ��',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '����ʱ��',
  UNIQUE KEY uk_memory_id (memory_id),
  UNIQUE KEY uk_tenant_customer_scope (tenant_id, customer_id, memory_scope),
  KEY idx_tenant_customer (tenant_id, customer_id),
  KEY idx_tenant_compiled_at (tenant_id, last_compiled_at),
  KEY idx_source_run_id (source_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='�ͻ����ڼ������V1 �ȷ��� Risk Agent';

CREATE TABLE IF NOT EXISTS business_report (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  report_id VARCHAR(64) NOT NULL COMMENT '报告业务主键',
  run_id VARCHAR(64) NULL COMMENT '来源 Agent Run ID',
  report_type VARCHAR(30) NOT NULL COMMENT '报告类型，例如 daily / weekly / monthly',
  report_date DATE NOT NULL COMMENT '报告归属日期',
  summary TEXT NOT NULL COMMENT '经营摘要',
  metrics_json JSON NULL COMMENT '聚合指标 JSON',
  risk_top_json JSON NULL COMMENT '重点风险客户 JSON',
  suggestions TEXT NULL COMMENT '行动建议',
  created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建人用户 ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_report_id (report_id),
  KEY idx_tenant_type_date (tenant_id, report_type, report_date),
  KEY idx_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营报告表';

CREATE TABLE IF NOT EXISTS rag_document (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  document_id VARCHAR(64) NOT NULL COMMENT '文档业务主键',
  doc_id VARCHAR(80) NOT NULL COMMENT '文档标识编码',
  title VARCHAR(150) NOT NULL COMMENT '文档标题',
  category VARCHAR(50) NOT NULL COMMENT '文档分类',
  source_file VARCHAR(255) NOT NULL COMMENT '源文件路径或文件名',
  source_type VARCHAR(30) NOT NULL DEFAULT 'document' COMMENT '来源类型：document / qa',
  version VARCHAR(30) NOT NULL DEFAULT 'v1' COMMENT '文档版本',
  status VARCHAR(30) NOT NULL DEFAULT 'active' COMMENT '文档状态',
  checksum VARCHAR(64) NULL COMMENT '文件校验值',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_document_id (document_id),
  KEY idx_tenant_doc (tenant_id, doc_id),
  KEY idx_tenant_category (tenant_id, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 文档元信息表';

CREATE TABLE IF NOT EXISTS rag_chunk (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  chunk_id VARCHAR(64) NOT NULL COMMENT '切片业务主键',
  document_id VARCHAR(64) NOT NULL COMMENT '所属文档 ID',
  doc_id VARCHAR(80) NOT NULL COMMENT '文档标识编码',
  section_id VARCHAR(80) NOT NULL COMMENT '章节或分段标识',
  chunk_index INT NOT NULL COMMENT '切片序号',
  title VARCHAR(150) NULL COMMENT '切片标题',
  text_preview VARCHAR(500) NULL COMMENT '切片文本摘要',
  token_count INT NOT NULL DEFAULT 0 COMMENT '切片 token 数量',
  milvus_collection VARCHAR(100) NOT NULL COMMENT 'Milvus collection 名称',
  milvus_pk VARCHAR(100) NULL COMMENT 'Milvus 主键',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_chunk_id (chunk_id),
  KEY idx_tenant_doc_section (tenant_id, doc_id, section_id),
  KEY idx_document_id (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 切片元信息表';

CREATE TABLE IF NOT EXISTS rag_qa_pair (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  qa_id VARCHAR(80) NOT NULL COMMENT '问答业务主键',
  doc_id VARCHAR(80) NOT NULL COMMENT '所属文档标识',
  section_id VARCHAR(80) NOT NULL COMMENT '章节或分段标识',
  question VARCHAR(500) NOT NULL COMMENT '问题文本',
  answer_preview VARCHAR(800) NOT NULL COMMENT '答案摘要',
  tags_json JSON NULL COMMENT '标签 JSON',
  source_type VARCHAR(30) NOT NULL DEFAULT 'qa' COMMENT '来源类型，默认 qa',
  milvus_collection VARCHAR(100) NOT NULL COMMENT 'Milvus collection 名称',
  milvus_pk VARCHAR(100) NULL COMMENT 'Milvus 主键',
  status VARCHAR(30) NOT NULL DEFAULT 'active' COMMENT '问答状态',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_qa_id (qa_id),
  KEY idx_tenant_doc_section (tenant_id, doc_id, section_id),
  KEY idx_tenant_status (tenant_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 问答元信息表';

CREATE TABLE IF NOT EXISTS rag_ingest_job (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  job_id VARCHAR(64) NOT NULL COMMENT '入库任务业务主键',
  job_type VARCHAR(30) NOT NULL COMMENT '任务类型，例如 document / qa',
  source_path VARCHAR(500) NULL COMMENT '源文件路径',
  status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending / running / success / failed',
  total_count INT NOT NULL DEFAULT 0 COMMENT '总处理数量',
  success_count INT NOT NULL DEFAULT 0 COMMENT '成功数量',
  failed_count INT NOT NULL DEFAULT 0 COMMENT '失败数量',
  error_message TEXT NULL COMMENT '错误信息',
  started_at DATETIME NULL COMMENT '开始时间',
  finished_at DATETIME NULL COMMENT '结束时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_job_id (job_id),
  KEY idx_tenant_status (tenant_id, status),
  KEY idx_tenant_started (tenant_id, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 入库任务表';

CREATE TABLE IF NOT EXISTS rag_retrieval_trace (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  trace_id VARCHAR(64) NOT NULL COMMENT '检索链路业务主键',
  run_id VARCHAR(64) NULL COMMENT '关联 Agent Run ID',
  user_id VARCHAR(64) NOT NULL COMMENT '触发用户 ID',
  original_query TEXT NOT NULL COMMENT '原始查询',
  rewritten_query TEXT NULL COMMENT '重写后的查询',
  strategy VARCHAR(80) NOT NULL COMMENT '检索策略描述',
  rewrite_ms INT NOT NULL DEFAULT 0 COMMENT '查询重写耗时（毫秒）',
  embed_ms INT NOT NULL DEFAULT 0 COMMENT '向量化耗时（毫秒）',
  search_ms INT NOT NULL DEFAULT 0 COMMENT '检索耗时（毫秒）',
  rerank_ms INT NOT NULL DEFAULT 0 COMMENT '重排耗时（毫秒）',
  total_ms INT NOT NULL DEFAULT 0 COMMENT '总耗时（毫秒）',
  top_k INT NOT NULL DEFAULT 0 COMMENT '检索 top_k',
  hit_count INT NOT NULL DEFAULT 0 COMMENT '命中数量',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_trace_id (trace_id),
  KEY idx_tenant_user_time (tenant_id, user_id, created_at),
  KEY idx_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 检索链路表';

CREATE TABLE IF NOT EXISTS rag_retrieval_hit (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
  tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
  trace_id VARCHAR(64) NOT NULL COMMENT '所属检索链路 ID',
  hit_id VARCHAR(64) NOT NULL COMMENT '命中记录业务主键',
  source_collection VARCHAR(100) NOT NULL COMMENT '命中来源 collection',
  source_type VARCHAR(30) NOT NULL COMMENT '命中来源类型',
  doc_id VARCHAR(80) NOT NULL COMMENT '命中文档标识',
  section_id VARCHAR(80) NULL COMMENT '命中章节标识',
  source_pk VARCHAR(100) NULL COMMENT '来源向量主键',
  rank_no INT NOT NULL COMMENT '命中排序',
  dense_score DECIMAL(10,6) NULL COMMENT '稠密向量分数',
  sparse_score DECIMAL(10,6) NULL COMMENT '稀疏向量分数',
  rrf_score DECIMAL(10,6) NULL COMMENT 'RRF 融合分数',
  rerank_score DECIMAL(10,6) NULL COMMENT '重排分数',
  text_preview VARCHAR(800) NULL COMMENT '命中内容摘要',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  KEY idx_trace_rank (trace_id, rank_no),
  KEY idx_tenant_doc (tenant_id, doc_id),
  KEY idx_source_type (source_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 命中明细表';
