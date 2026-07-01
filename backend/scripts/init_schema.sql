CREATE DATABASE IF NOT EXISTS insightpilot DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE insightpilot;

CREATE TABLE IF NOT EXISTS tenant (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  tenant_name VARCHAR(100) NOT NULL,
  status TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户表，V1 只启用 demo_tenant';

CREATE TABLE IF NOT EXISTS sys_user (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  username VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  real_name VARCHAR(80) NOT NULL,
  phone VARCHAR(30) NULL,
  email VARCHAR(120) NULL,
  status TINYINT NOT NULL DEFAULT 1,
  is_deleted TINYINT NOT NULL DEFAULT 0,
  last_login_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_tenant_username (tenant_id, username),
  UNIQUE KEY uk_user_id (user_id),
  KEY idx_tenant_status (tenant_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统用户';

CREATE TABLE IF NOT EXISTS sys_role (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  role_id VARCHAR(64) NOT NULL,
  role_code VARCHAR(50) NOT NULL,
  role_name VARCHAR(80) NOT NULL,
  status TINYINT NOT NULL DEFAULT 1,
  remark VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_tenant_role_code (tenant_id, role_code),
  UNIQUE KEY uk_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色';

CREATE TABLE IF NOT EXISTS sys_permission (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  permission_id VARCHAR(64) NOT NULL,
  permission_code VARCHAR(100) NOT NULL,
  permission_name VARCHAR(100) NOT NULL,
  module VARCHAR(50) NOT NULL,
  action VARCHAR(50) NOT NULL,
  description VARCHAR(255) NULL,
  status TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_permission_id (permission_id),
  UNIQUE KEY uk_permission_code (permission_code),
  KEY idx_permission_module (module)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限点';

CREATE TABLE IF NOT EXISTS sys_user_role (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  role_id VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_role (tenant_id, user_id, role_id),
  KEY idx_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户角色关系';

CREATE TABLE IF NOT EXISTS sys_role_permission (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  role_id VARCHAR(64) NOT NULL,
  permission_id VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_role_permission (tenant_id, role_id, permission_id),
  KEY idx_permission_id (permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色权限关系';

CREATE TABLE IF NOT EXISTS crm_customer (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  customer_id VARCHAR(64) NOT NULL,
  customer_name VARCHAR(150) NOT NULL,
  owner_user_id VARCHAR(64) NOT NULL,
  industry VARCHAR(80) NULL,
  region VARCHAR(80) NULL,
  source VARCHAR(50) NULL,
  lifecycle_stage VARCHAR(30) NOT NULL,
  intent_level VARCHAR(20) NOT NULL DEFAULT 'medium',
  customer_level VARCHAR(20) NOT NULL DEFAULT 'B',
  company_size VARCHAR(50) NULL,
  budget_min DECIMAL(12,2) NULL,
  budget_max DECIMAL(12,2) NULL,
  expected_purchase_at DATE NULL,
  decision_maker_status VARCHAR(30) NOT NULL DEFAULT 'unknown',
  competitor_involved TINYINT NOT NULL DEFAULT 0,
  next_follow_up_at DATETIME NULL,
  last_follow_up_at DATETIME NULL,
  last_sentiment VARCHAR(20) NOT NULL DEFAULT 'neutral',
  lost_reason VARCHAR(255) NULL,
  remark TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_customer_id (customer_id),
  KEY idx_tenant_owner (tenant_id, owner_user_id),
  KEY idx_tenant_stage (tenant_id, lifecycle_stage),
  KEY idx_tenant_last_follow (tenant_id, last_follow_up_at),
  KEY idx_tenant_competitor (tenant_id, competitor_involved)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户主表';

CREATE TABLE IF NOT EXISTS crm_contact (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  contact_id VARCHAR(64) NOT NULL,
  customer_id VARCHAR(64) NOT NULL,
  contact_name VARCHAR(80) NOT NULL,
  title VARCHAR(80) NULL,
  phone VARCHAR(30) NULL,
  email VARCHAR(120) NULL,
  wechat VARCHAR(80) NULL,
  is_decision_maker TINYINT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_contact_id (contact_id),
  KEY idx_tenant_customer (tenant_id, customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户联系人';

CREATE TABLE IF NOT EXISTS crm_deal (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  deal_id VARCHAR(64) NOT NULL,
  customer_id VARCHAR(64) NOT NULL,
  owner_user_id VARCHAR(64) NOT NULL,
  deal_name VARCHAR(150) NOT NULL,
  stage VARCHAR(30) NOT NULL,
  amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  quote_amount DECIMAL(12,2) NULL,
  quoted_at DATETIME NULL,
  expected_close_at DATE NULL,
  closed_at DATETIME NULL,
  close_result VARCHAR(20) NOT NULL DEFAULT 'open',
  lost_reason VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_deal_id (deal_id),
  KEY idx_tenant_customer (tenant_id, customer_id),
  KEY idx_tenant_owner_stage (tenant_id, owner_user_id, stage),
  KEY idx_tenant_quoted_at (tenant_id, quoted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商机';

CREATE TABLE IF NOT EXISTS crm_follow_up_record (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  follow_up_id VARCHAR(64) NOT NULL,
  customer_id VARCHAR(64) NOT NULL,
  deal_id VARCHAR(64) NULL,
  owner_user_id VARCHAR(64) NOT NULL,
  follow_up_type VARCHAR(30) NOT NULL,
  content TEXT NOT NULL,
  sentiment VARCHAR(20) NOT NULL DEFAULT 'neutral',
  customer_feedback VARCHAR(255) NULL,
  next_action VARCHAR(255) NULL,
  next_follow_up_at DATETIME NULL,
  occurred_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_follow_up_id (follow_up_id),
  KEY idx_tenant_customer_time (tenant_id, customer_id, occurred_at),
  KEY idx_tenant_owner_time (tenant_id, owner_user_id, occurred_at),
  KEY idx_tenant_sentiment (tenant_id, sentiment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='跟进记录';

CREATE TABLE IF NOT EXISTS customer_risk_snapshot (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  risk_snapshot_id VARCHAR(64) NOT NULL,
  customer_id VARCHAR(64) NOT NULL,
  deal_id VARCHAR(64) NULL,
  owner_user_id VARCHAR(64) NOT NULL,
  risk_score INT NOT NULL,
  risk_level VARCHAR(20) NOT NULL,
  rule_hits_json JSON NULL,
  evidence_json JSON NULL,
  llm_reason TEXT NULL,
  llm_suggestion TEXT NULL,
  suggested_task_json JSON NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'pending_review',
  generated_by_run_id VARCHAR(64) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_risk_snapshot_id (risk_snapshot_id),
  KEY idx_tenant_customer (tenant_id, customer_id),
  KEY idx_tenant_level_score (tenant_id, risk_level, risk_score),
  KEY idx_tenant_status (tenant_id, status),
  KEY idx_generated_run (generated_by_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户风险快照';

CREATE TABLE IF NOT EXISTS risk_rule_config (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  rule_code VARCHAR(80) NOT NULL,
  rule_name VARCHAR(120) NOT NULL,
  rule_type VARCHAR(50) NOT NULL,
  score_weight INT NOT NULL,
  threshold_json JSON NULL,
  enabled TINYINT NOT NULL DEFAULT 1,
  version VARCHAR(30) NOT NULL DEFAULT 'v1',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_tenant_rule (tenant_id, rule_code, version),
  KEY idx_tenant_enabled (tenant_id, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='风险规则配置预留表，V1 暂不生效';

CREATE TABLE IF NOT EXISTS approval_record (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  approval_id VARCHAR(64) NOT NULL,
  approval_type VARCHAR(50) NOT NULL,
  run_id VARCHAR(64) NULL,
  risk_snapshot_id VARCHAR(64) NULL,
  customer_id VARCHAR(64) NOT NULL,
  proposed_payload_json JSON NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  requested_by_user_id VARCHAR(64) NOT NULL,
  reviewer_user_id VARCHAR(64) NULL,
  reviewed_at DATETIME NULL,
  review_comment VARCHAR(500) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_approval_id (approval_id),
  KEY idx_tenant_status (tenant_id, status),
  KEY idx_tenant_reviewer (tenant_id, reviewer_user_id),
  KEY idx_risk_snapshot (risk_snapshot_id),
  KEY idx_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人工审批记录';

CREATE TABLE IF NOT EXISTS sales_task (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  approval_id VARCHAR(64) NULL,
  customer_id VARCHAR(64) NOT NULL,
  deal_id VARCHAR(64) NULL,
  assignee_user_id VARCHAR(64) NOT NULL,
  creator_user_id VARCHAR(64) NOT NULL,
  task_type VARCHAR(50) NOT NULL,
  title VARCHAR(150) NOT NULL,
  description TEXT NULL,
  recommended_script TEXT NULL,
  priority VARCHAR(20) NOT NULL DEFAULT 'medium',
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  due_at DATETIME NULL,
  completed_at DATETIME NULL,
  result_note TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_task_id (task_id),
  KEY idx_tenant_assignee_status (tenant_id, assignee_user_id, status),
  KEY idx_tenant_customer (tenant_id, customer_id),
  KEY idx_tenant_due (tenant_id, due_at),
  KEY idx_approval_id (approval_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售任务';

CREATE TABLE IF NOT EXISTS agent_run (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  run_type VARCHAR(50) NOT NULL,
  graph_name VARCHAR(80) NOT NULL,
  input_json JSON NULL,
  output_json JSON NULL,
  status VARCHAR(30) NOT NULL,
  error_message TEXT NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  total_duration_ms INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_run_id (run_id),
  KEY idx_tenant_user (tenant_id, user_id),
  KEY idx_tenant_type_status (tenant_id, run_type, status),
  KEY idx_tenant_started (tenant_id, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent 执行记录';

CREATE TABLE IF NOT EXISTS agent_step (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  step_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NOT NULL,
  node_name VARCHAR(80) NOT NULL,
  tool_name VARCHAR(80) NULL,
  required_permissions_json JSON NULL,
  input_json JSON NULL,
  output_json JSON NULL,
  status VARCHAR(30) NOT NULL,
  error_message TEXT NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  duration_ms INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_step_id (step_id),
  KEY idx_run_id (run_id),
  KEY idx_tenant_node (tenant_id, node_name),
  KEY idx_tenant_tool (tenant_id, tool_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent 步骤记录';

CREATE TABLE IF NOT EXISTS business_report (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  report_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NULL,
  report_type VARCHAR(30) NOT NULL,
  report_date DATE NOT NULL,
  summary TEXT NOT NULL,
  metrics_json JSON NULL,
  risk_top_json JSON NULL,
  suggestions TEXT NULL,
  created_by_user_id VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_report_id (report_id),
  KEY idx_tenant_type_date (tenant_id, report_type, report_date),
  KEY idx_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营报告';

CREATE TABLE IF NOT EXISTS rag_document (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  document_id VARCHAR(64) NOT NULL,
  doc_id VARCHAR(80) NOT NULL,
  title VARCHAR(150) NOT NULL,
  category VARCHAR(50) NOT NULL,
  source_file VARCHAR(255) NOT NULL,
  source_type VARCHAR(30) NOT NULL DEFAULT 'document',
  version VARCHAR(30) NOT NULL DEFAULT 'v1',
  status VARCHAR(30) NOT NULL DEFAULT 'active',
  checksum VARCHAR(64) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_document_id (document_id),
  KEY idx_tenant_doc (tenant_id, doc_id),
  KEY idx_tenant_category (tenant_id, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 文档元信息';

CREATE TABLE IF NOT EXISTS rag_chunk (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  chunk_id VARCHAR(64) NOT NULL,
  document_id VARCHAR(64) NOT NULL,
  doc_id VARCHAR(80) NOT NULL,
  section_id VARCHAR(80) NOT NULL,
  chunk_index INT NOT NULL,
  title VARCHAR(150) NULL,
  text_preview VARCHAR(500) NULL,
  token_count INT NOT NULL DEFAULT 0,
  milvus_collection VARCHAR(100) NOT NULL,
  milvus_pk VARCHAR(100) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_chunk_id (chunk_id),
  KEY idx_tenant_doc_section (tenant_id, doc_id, section_id),
  KEY idx_document_id (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 切片元信息';

CREATE TABLE IF NOT EXISTS rag_qa_pair (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  qa_id VARCHAR(80) NOT NULL,
  doc_id VARCHAR(80) NOT NULL,
  section_id VARCHAR(80) NOT NULL,
  question VARCHAR(500) NOT NULL,
  answer_preview VARCHAR(800) NOT NULL,
  tags_json JSON NULL,
  source_type VARCHAR(30) NOT NULL DEFAULT 'qa',
  milvus_collection VARCHAR(100) NOT NULL,
  milvus_pk VARCHAR(100) NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_qa_id (qa_id),
  KEY idx_tenant_doc_section (tenant_id, doc_id, section_id),
  KEY idx_tenant_status (tenant_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG QA 元信息';

CREATE TABLE IF NOT EXISTS rag_ingest_job (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  job_id VARCHAR(64) NOT NULL,
  job_type VARCHAR(30) NOT NULL,
  source_path VARCHAR(500) NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  total_count INT NOT NULL DEFAULT 0,
  success_count INT NOT NULL DEFAULT 0,
  failed_count INT NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_job_id (job_id),
  KEY idx_tenant_status (tenant_id, status),
  KEY idx_tenant_started (tenant_id, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 入库任务';

CREATE TABLE IF NOT EXISTS rag_retrieval_trace (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  trace_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NULL,
  user_id VARCHAR(64) NOT NULL,
  original_query TEXT NOT NULL,
  rewritten_query TEXT NULL,
  strategy VARCHAR(80) NOT NULL,
  rewrite_ms INT NOT NULL DEFAULT 0,
  embed_ms INT NOT NULL DEFAULT 0,
  search_ms INT NOT NULL DEFAULT 0,
  rerank_ms INT NOT NULL DEFAULT 0,
  total_ms INT NOT NULL DEFAULT 0,
  top_k INT NOT NULL DEFAULT 0,
  hit_count INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_trace_id (trace_id),
  KEY idx_tenant_user_time (tenant_id, user_id, created_at),
  KEY idx_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 检索链路';

CREATE TABLE IF NOT EXISTS rag_retrieval_hit (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  trace_id VARCHAR(64) NOT NULL,
  hit_id VARCHAR(64) NOT NULL,
  source_collection VARCHAR(100) NOT NULL,
  source_type VARCHAR(30) NOT NULL,
  doc_id VARCHAR(80) NOT NULL,
  section_id VARCHAR(80) NULL,
  source_pk VARCHAR(100) NULL,
  rank_no INT NOT NULL,
  dense_score DECIMAL(10,6) NULL,
  sparse_score DECIMAL(10,6) NULL,
  rrf_score DECIMAL(10,6) NULL,
  rerank_score DECIMAL(10,6) NULL,
  text_preview VARCHAR(800) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_trace_rank (trace_id, rank_no),
  KEY idx_tenant_doc (tenant_id, doc_id),
  KEY idx_source_type (source_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG 检索命中';
