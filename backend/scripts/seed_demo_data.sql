USE insightpilot;

INSERT IGNORE INTO tenant (tenant_id, tenant_name, status)
VALUES ('demo_tenant', 'InsightPilot 演示公司', 1);

INSERT IGNORE INTO sys_role (tenant_id, role_id, role_code, role_name, status, remark)
VALUES
('demo_tenant', 'role_owner', 'owner', '老板', 1, '查看全局经营数据和 Agent 执行日志'),
('demo_tenant', 'role_manager', 'manager', '销售主管', 1, '管理团队客户风险和 AI 任务审批'),
('demo_tenant', 'role_salesperson', 'salesperson', '销售员', 1, '处理自己负责的客户和任务');

INSERT IGNORE INTO sys_permission (permission_id, permission_code, permission_name, module, action, description, status)
VALUES
('perm_crm_customer_read_self', 'crm:customer:read:self', '查看自己客户', 'crm', 'read', '销售员查看自己负责的客户', 1),
('perm_crm_customer_read_team', 'crm:customer:read:team', '查看团队客户', 'crm', 'read', '主管查看团队客户', 1),
('perm_crm_customer_read_all', 'crm:customer:read:all', '查看全部客户', 'crm', 'read', '老板查看全部客户', 1),
('perm_crm_risk_read_team', 'crm:risk:read:team', '查看团队风险', 'risk', 'read', '查看团队客户风险', 1),
('perm_crm_risk_read_all', 'crm:risk:read:all', '查看全部风险', 'risk', 'read', '查看全部客户风险', 1),
('perm_agent_run_risk', 'agent:run:risk_analysis', '运行风险分析', 'agent', 'run', '触发客户风险扫描 Agent', 1),
('perm_agent_run_report', 'agent:run:business_report', '运行经营日报', 'agent', 'run', '触发经营日报 Agent', 1),
('perm_agent_log_read', 'agent:log:read', '查看 Agent 日志', 'agent', 'read', '查看 Agent Run 和 Step', 1),
('perm_approval_review', 'approval:review:agent_task', '审批 AI 任务', 'approval', 'review', '审批 AI 生成的任务草稿', 1),
('perm_task_read_self', 'task:read:self', '查看自己任务', 'task', 'read', '查看自己负责的销售任务', 1),
('perm_task_read_team', 'task:read:team', '查看团队任务', 'task', 'read', '主管查看团队任务', 1),
('perm_task_read_all', 'task:read:all', '查看全部任务', 'task', 'read', '老板查看全部任务', 1),
('perm_report_read_team', 'report:read:team', '查看团队报告', 'report', 'read', '查看团队经营报告', 1),
('perm_report_read_all', 'report:read:all', '查看全部报告', 'report', 'read', '查看全局经营报告', 1),
('perm_rag_ingest_run', 'rag:ingest:run', '运行 RAG 入库', 'rag', 'run', '触发 RAG 知识库入库任务', 1);

INSERT IGNORE INTO sys_user (tenant_id, user_id, username, password_hash, real_name, phone, email, status, is_deleted)
VALUES
('demo_tenant', 'u_owner_001', 'owner', 'pbkdf2_sha256$600000$sw3mgBMBpcW6KR1MAw1GcQ$xbMHWUVpkYmHfQ8fYywi5gidIzgmtXiVihPFPoN9Wt4', '林总', '13800000001', 'owner@insightpilot.local', 1, 0),
('demo_tenant', 'u_manager_001', 'manager', 'pbkdf2_sha256$600000$smTv8qJszI0dxhM8I0HWfw$RxZ6qjmDkDpdMOGAVynrf5gZJ7tdGIfu_o_UL3p3-zk', '周主管', '13800000002', 'manager@insightpilot.local', 1, 0),
('demo_tenant', 'u_sales_001', 'sales01', 'pbkdf2_sha256$600000$pIfpQoqyq64eTRgmHhUMgA$ED6hUlXATYFa8Ryv0OkHf7CaAuyKpzv1rxX5Wdb0_jg', '陈销售', '13800000003', 'sales01@insightpilot.local', 1, 0),
('demo_tenant', 'u_sales_002', 'sales02', 'pbkdf2_sha256$600000$pIfpQoqyq64eTRgmHhUMgA$ED6hUlXATYFa8Ryv0OkHf7CaAuyKpzv1rxX5Wdb0_jg', '何销售', '13800000004', 'sales02@insightpilot.local', 1, 0),
('demo_tenant', 'u_sales_003', 'sales03', 'pbkdf2_sha256$600000$pIfpQoqyq64eTRgmHhUMgA$ED6hUlXATYFa8Ryv0OkHf7CaAuyKpzv1rxX5Wdb0_jg', '吴销售', '13800000005', 'sales03@insightpilot.local', 1, 0);

INSERT IGNORE INTO sys_user_role (tenant_id, user_id, role_id)
VALUES
('demo_tenant', 'u_owner_001', 'role_owner'),
('demo_tenant', 'u_manager_001', 'role_manager'),
('demo_tenant', 'u_sales_001', 'role_salesperson'),
('demo_tenant', 'u_sales_002', 'role_salesperson'),
('demo_tenant', 'u_sales_003', 'role_salesperson');

INSERT IGNORE INTO sys_role_permission (tenant_id, role_id, permission_id)
VALUES
('demo_tenant', 'role_owner', 'perm_crm_customer_read_self'),
('demo_tenant', 'role_owner', 'perm_crm_customer_read_team'),
('demo_tenant', 'role_owner', 'perm_crm_customer_read_all'),
('demo_tenant', 'role_owner', 'perm_crm_risk_read_team'),
('demo_tenant', 'role_owner', 'perm_crm_risk_read_all'),
('demo_tenant', 'role_owner', 'perm_agent_run_risk'),
('demo_tenant', 'role_owner', 'perm_agent_run_report'),
('demo_tenant', 'role_owner', 'perm_agent_log_read'),
('demo_tenant', 'role_owner', 'perm_approval_review'),
('demo_tenant', 'role_owner', 'perm_task_read_self'),
('demo_tenant', 'role_owner', 'perm_task_read_team'),
('demo_tenant', 'role_owner', 'perm_task_read_all'),
('demo_tenant', 'role_owner', 'perm_report_read_team'),
('demo_tenant', 'role_owner', 'perm_report_read_all'),
('demo_tenant', 'role_owner', 'perm_rag_ingest_run'),
('demo_tenant', 'role_manager', 'perm_crm_customer_read_self'),
('demo_tenant', 'role_manager', 'perm_crm_customer_read_team'),
('demo_tenant', 'role_manager', 'perm_crm_risk_read_team'),
('demo_tenant', 'role_manager', 'perm_agent_run_risk'),
('demo_tenant', 'role_manager', 'perm_agent_run_report'),
('demo_tenant', 'role_manager', 'perm_agent_log_read'),
('demo_tenant', 'role_manager', 'perm_approval_review'),
('demo_tenant', 'role_manager', 'perm_task_read_self'),
('demo_tenant', 'role_manager', 'perm_task_read_team'),
('demo_tenant', 'role_manager', 'perm_report_read_team'),
('demo_tenant', 'role_salesperson', 'perm_crm_customer_read_self'),
('demo_tenant', 'role_salesperson', 'perm_task_read_self');

INSERT IGNORE INTO crm_customer (
  tenant_id, customer_id, customer_name, owner_user_id, industry, region, source,
  lifecycle_stage, intent_level, customer_level, company_size, budget_min, budget_max,
  expected_purchase_at, decision_maker_status, competitor_involved, next_follow_up_at,
  last_follow_up_at, last_sentiment, remark
)
VALUES
('demo_tenant','c_001','深圳星河教育','u_sales_001','教育培训','深圳','官网','quotation','high','A','200-500人',60000,120000,DATE_ADD(CURDATE(), INTERVAL 20 DAY),'confirmed',1,NULL,DATE_SUB(NOW(), INTERVAL 22 DAY),'negative','报价后沉默，客户提到竞品报价更低'),
('demo_tenant','c_002','杭州云帆科技','u_sales_001','软件服务','杭州','转介绍','solution','medium','A','50-200人',40000,90000,DATE_ADD(CURDATE(), INTERVAL 35 DAY),'identified',0,DATE_ADD(NOW(), INTERVAL 2 DAY),DATE_SUB(NOW(), INTERVAL 3 DAY),'positive','方案评估中，需求清晰'),
('demo_tenant','c_003','广州南禾商贸','u_sales_002','批发零售','广州','展会','quotation','medium','B','50-100人',20000,50000,DATE_ADD(CURDATE(), INTERVAL 15 DAY),'identified',0,NULL,DATE_SUB(NOW(), INTERVAL 16 DAY),'neutral','报价后客户说需要内部讨论'),
('demo_tenant','c_004','成都远景制造','u_sales_002','制造业','成都','电话开发','communicated','high','A','500人以上',100000,200000,DATE_ADD(CURDATE(), INTERVAL 45 DAY),'confirmed',1,DATE_ADD(NOW(), INTERVAL 1 DAY),DATE_SUB(NOW(), INTERVAL 8 DAY),'neutral','竞品已介入，但客户仍愿意沟通'),
('demo_tenant','c_005','北京麦田咨询','u_sales_003','企业服务','北京','内容营销','new_lead','low','C','20-50人',10000,30000,NULL,'unknown',0,NULL,NULL,'neutral','新线索，尚未完成首次联系'),
('demo_tenant','c_006','苏州北桥医疗','u_sales_003','医疗健康','苏州','老客户推荐','quotation','high','A','200-500人',80000,150000,DATE_ADD(CURDATE(), INTERVAL 10 DAY),'confirmed',0,NULL,DATE_SUB(NOW(), INTERVAL 31 DAY),'negative','预算审批卡住，高金额客户'),
('demo_tenant','c_007','南京青木物流','u_sales_001','物流','南京','官网','won','high','A','100-200人',50000,90000,DATE_SUB(CURDATE(), INTERVAL 5 DAY),'confirmed',0,DATE_ADD(NOW(), INTERVAL 20 DAY),DATE_SUB(NOW(), INTERVAL 2 DAY),'positive','已成交，等待交付衔接'),
('demo_tenant','c_008','武汉江城餐饮','u_sales_002','餐饮连锁','武汉','朋友介绍','communicated','medium','B','100-300人',30000,80000,DATE_ADD(CURDATE(), INTERVAL 60 DAY),'identified',0,DATE_ADD(NOW(), INTERVAL 5 DAY),DATE_SUB(NOW(), INTERVAL 6 DAY),'neutral','客户关注门店管理效率'),
('demo_tenant','c_009','西安矩阵传媒','u_sales_003','广告传媒','西安','广告投放','solution','medium','B','50-100人',20000,60000,DATE_ADD(CURDATE(), INTERVAL 30 DAY),'unknown',0,NULL,DATE_SUB(NOW(), INTERVAL 18 DAY),'neutral','方案发送后暂无反馈'),
('demo_tenant','c_010','厦门蓝湾文旅','u_sales_001','文旅','厦门','展会','lost','low','C','20-50人',10000,20000,NULL,'identified',0,NULL,DATE_SUB(NOW(), INTERVAL 70 DAY),'negative','客户选择竞品，已流失'),
('demo_tenant','c_011','天津瑞成集团','u_sales_002','综合集团','天津','渠道','quotation','high','A','500人以上',120000,260000,DATE_ADD(CURDATE(), INTERVAL 25 DAY),'confirmed',1,NULL,DATE_SUB(NOW(), INTERVAL 15 DAY),'negative','高金额报价后沉默，竞品介入'),
('demo_tenant','c_012','长沙橙子科技','u_sales_003','软件服务','长沙','官网','solution','medium','B','50-200人',30000,70000,DATE_ADD(CURDATE(), INTERVAL 40 DAY),'identified',0,DATE_ADD(NOW(), INTERVAL 4 DAY),DATE_SUB(NOW(), INTERVAL 4 DAY),'positive','客户认可价值，等待技术评估');

INSERT IGNORE INTO crm_contact (tenant_id, contact_id, customer_id, contact_name, title, phone, email, wechat, is_decision_maker)
VALUES
('demo_tenant','ct_001','c_001','王校长','校长','13900001001','wang@xinghe.local','wx_xinghe',1),
('demo_tenant','ct_002','c_002','李经理','运营经理','13900001002','li@yunfan.local','wx_yunfan',1),
('demo_tenant','ct_003','c_003','赵总','总经理','13900001003','zhao@nanhe.local','wx_nanhe',1),
('demo_tenant','ct_004','c_004','孙总监','销售总监','13900001004','sun@yuanjing.local','wx_yuanjing',1),
('demo_tenant','ct_005','c_005','刘老师','负责人','13900001005','liu@maitian.local','wx_maitian',0),
('demo_tenant','ct_006','c_006','陈院长','院长','13900001006','chen@beiqiao.local','wx_beiqiao',1),
('demo_tenant','ct_011','c_011','高总','副总裁','13900001011','gao@ruicheng.local','wx_ruicheng',1),
('demo_tenant','ct_012','c_012','唐经理','技术经理','13900001012','tang@orange.local','wx_orange',0);

INSERT IGNORE INTO crm_deal (
  tenant_id, deal_id, customer_id, owner_user_id, deal_name, stage, amount,
  quote_amount, quoted_at, expected_close_at, closed_at, close_result, lost_reason
)
VALUES
('demo_tenant','d_001','c_001','u_sales_001','星河教育销售运营系统','quotation',88000,92000,DATE_SUB(NOW(), INTERVAL 18 DAY),DATE_ADD(CURDATE(), INTERVAL 20 DAY),NULL,'open',NULL),
('demo_tenant','d_002','c_002','u_sales_001','云帆科技销售管理试点','solution',76000,NULL,NULL,DATE_ADD(CURDATE(), INTERVAL 35 DAY),NULL,'open',NULL),
('demo_tenant','d_003','c_003','u_sales_002','南禾商贸客户风险看板','quotation',42000,45000,DATE_SUB(NOW(), INTERVAL 9 DAY),DATE_ADD(CURDATE(), INTERVAL 15 DAY),NULL,'open',NULL),
('demo_tenant','d_004','c_004','u_sales_002','远景制造多团队销售治理','communicated',160000,NULL,NULL,DATE_ADD(CURDATE(), INTERVAL 45 DAY),NULL,'open',NULL),
('demo_tenant','d_006','c_006','u_sales_003','北桥医疗经营驾驶舱','quotation',128000,138000,DATE_SUB(NOW(), INTERVAL 20 DAY),DATE_ADD(CURDATE(), INTERVAL 10 DAY),NULL,'open',NULL),
('demo_tenant','d_007','c_007','u_sales_001','青木物流销售任务闭环','won',68000,68000,DATE_SUB(NOW(), INTERVAL 18 DAY),DATE_SUB(CURDATE(), INTERVAL 5 DAY),DATE_SUB(NOW(), INTERVAL 5 DAY),'won',NULL),
('demo_tenant','d_009','c_009','u_sales_003','矩阵传媒销售 SOP 知识库','solution',52000,NULL,NULL,DATE_ADD(CURDATE(), INTERVAL 30 DAY),NULL,'open',NULL),
('demo_tenant','d_010','c_010','u_sales_001','蓝湾文旅销售管理试点','lost',18000,20000,DATE_SUB(NOW(), INTERVAL 80 DAY),DATE_SUB(CURDATE(), INTERVAL 70 DAY),DATE_SUB(NOW(), INTERVAL 70 DAY),'lost','客户选择竞品'),
('demo_tenant','d_011','c_011','u_sales_002','瑞成集团企业版试点','quotation',220000,238000,DATE_SUB(NOW(), INTERVAL 15 DAY),DATE_ADD(CURDATE(), INTERVAL 25 DAY),NULL,'open',NULL),
('demo_tenant','d_012','c_012','u_sales_003','橙子科技专业版试点','solution',62000,NULL,NULL,DATE_ADD(CURDATE(), INTERVAL 40 DAY),NULL,'open',NULL);

INSERT IGNORE INTO crm_follow_up_record (tenant_id, follow_up_id, customer_id, deal_id, owner_user_id, follow_up_type, content, sentiment, customer_feedback, next_action, next_follow_up_at, occurred_at)
VALUES
('demo_tenant','fu_001','c_001','d_001','u_sales_001','wechat','客户认为竞品报价更低，暂时没有明确回复。','negative','价格偏高，竞品介入','建议主管介入，重新确认价值点',NULL,DATE_SUB(NOW(), INTERVAL 22 DAY)),
('demo_tenant','fu_002','c_002','d_002','u_sales_001','meeting','客户认可风险识别和任务审批，希望看试点方案。','positive','认可价值','准备试点方案',DATE_ADD(NOW(), INTERVAL 2 DAY),DATE_SUB(NOW(), INTERVAL 3 DAY)),
('demo_tenant','fu_003','c_003','d_003','u_sales_002','phone','客户表示需要内部讨论预算。','neutral','需要内部讨论','下周再次确认预算',NULL,DATE_SUB(NOW(), INTERVAL 16 DAY)),
('demo_tenant','fu_004','c_004','d_004','u_sales_002','meeting','客户正在比较竞品，但愿意继续看我们方案。','neutral','竞品介入','整理差异化价值',DATE_ADD(NOW(), INTERVAL 1 DAY),DATE_SUB(NOW(), INTERVAL 8 DAY)),
('demo_tenant','fu_006','c_006','d_006','u_sales_003','email','客户反馈预算审批暂缓，院长担心 AI 不可靠。','negative','预算和 AI 可靠性顾虑','建议主管介入解释审批机制',NULL,DATE_SUB(NOW(), INTERVAL 31 DAY)),
('demo_tenant','fu_011','c_011','d_011','u_sales_002','phone','客户说价格需要再比较，竞品已提供低价方案。','negative','竞品低价，高层仍未拍板','建议主管约高层会议',NULL,DATE_SUB(NOW(), INTERVAL 15 DAY)),
('demo_tenant','fu_012','c_012','d_012','u_sales_003','meeting','客户技术团队认可方案，约定下周评估接口。','positive','技术认可','准备接口说明',DATE_ADD(NOW(), INTERVAL 4 DAY),DATE_SUB(NOW(), INTERVAL 4 DAY));

INSERT IGNORE INTO agent_run (tenant_id, run_id, user_id, run_type, graph_name, input_json, output_json, status, started_at, finished_at, total_duration_ms)
VALUES
('demo_tenant','run_seed_001','u_manager_001','risk_analysis','risk_analysis_graph','{"scope":"team"}','{"risk_count":5,"approval_count":3}','awaiting_approval',DATE_SUB(NOW(), INTERVAL 1 HOUR),DATE_SUB(NOW(), INTERVAL 58 MINUTE),124000),
('demo_tenant','run_seed_002','u_owner_001','business_report','business_report_graph','{"report_type":"daily"}','{"report_id":"report_001"}','success',DATE_SUB(NOW(), INTERVAL 30 MINUTE),DATE_SUB(NOW(), INTERVAL 29 MINUTE),42000);

INSERT IGNORE INTO agent_step (tenant_id, step_id, run_id, node_name, tool_name, required_permissions_json, input_json, output_json, status, started_at, finished_at, duration_ms)
VALUES
('demo_tenant','step_seed_001','run_seed_001','load_crm_data','crm_query_tool','["crm:customer:read:team"]','{"scope":"team"}','{"customer_count":12}','success',DATE_SUB(NOW(), INTERVAL 1 HOUR),DATE_SUB(NOW(), INTERVAL 59 MINUTE),1000),
('demo_tenant','step_seed_002','run_seed_001','calculate_rule_risk','risk_rule_tool','["crm:risk:read:team"]','{"customer_count":12}','{"high":4,"medium":2}','success',DATE_SUB(NOW(), INTERVAL 59 MINUTE),DATE_SUB(NOW(), INTERVAL 58 MINUTE),1600),
('demo_tenant','step_seed_003','run_seed_001','retrieve_sales_knowledge','rag_tool','["crm:risk:read:team"]','{"query":"报价后客户无回应怎么办"}','{"hits":3}','success',DATE_SUB(NOW(), INTERVAL 58 MINUTE),DATE_SUB(NOW(), INTERVAL 58 MINUTE),900);

INSERT IGNORE INTO customer_risk_snapshot (
  tenant_id, risk_snapshot_id, customer_id, deal_id, owner_user_id, risk_score, risk_level,
  rule_hits_json, evidence_json, llm_reason, llm_suggestion, suggested_task_json, status, generated_by_run_id
)
VALUES
('demo_tenant','risk_001','c_001','d_001','u_sales_001',85,'high','[{"rule_code":"quote_no_response_14d","score":35},{"rule_code":"competitor_involved","score":20},{"rule_code":"negative_sentiment","score":15},{"rule_code":"missing_next_follow","score":10}]','{"quoted_days":18,"competitor_involved":true,"last_sentiment":"negative"}','客户报价后 18 天未回应，同时提到竞品低价，存在明显流失风险。','建议销售主管介入，先确认客户比较维度，再用 AI 审批机制和经营闭环价值回应价格异议。','{"task_type":"manager_intervention","title":"主管介入星河教育报价风险","assignee_user_id":"u_sales_001","priority":"urgent"}','pending_review','run_seed_001'),
('demo_tenant','risk_003','c_003','d_003','u_sales_002',55,'medium','[{"rule_code":"quote_no_response_7d","score":20},{"rule_code":"no_follow_14d","score":20},{"rule_code":"missing_next_follow","score":10}]','{"quoted_days":9,"no_follow_days":16}','客户报价后 9 天未明确反馈，且缺少下一步跟进时间。','建议销售员用低压力方式确认预算和内部讨论时间。','{"task_type":"quote_follow","title":"跟进南禾商贸报价反馈","assignee_user_id":"u_sales_002","priority":"medium"}','pending_review','run_seed_001'),
('demo_tenant','risk_006','c_006','d_006','u_sales_003',90,'high','[{"rule_code":"quote_no_response_14d","score":35},{"rule_code":"no_follow_30d","score":35},{"rule_code":"negative_sentiment","score":15},{"rule_code":"high_value_deal","score":10}]','{"quoted_days":20,"no_follow_days":31,"amount":128000}','客户高金额报价后长期无回应，并存在预算和 AI 可靠性顾虑。','建议主管介入，解释规则引擎打分、人工审批和审计日志机制。','{"task_type":"manager_intervention","title":"主管介入北桥医疗高金额风险","assignee_user_id":"u_sales_003","priority":"urgent"}','pending_review','run_seed_001'),
('demo_tenant','risk_011','c_011','d_011','u_sales_002',95,'high','[{"rule_code":"quote_no_response_14d","score":35},{"rule_code":"competitor_involved","score":20},{"rule_code":"negative_sentiment","score":15},{"rule_code":"high_value_deal","score":10},{"rule_code":"missing_next_follow","score":10}]','{"quoted_days":15,"competitor_involved":true,"amount":220000}','客户金额高、竞品介入且报价后沉默，属于优先级最高的流失风险。','建议主管约客户高层做价值对齐，不建议只发送普通微信催促。','{"task_type":"manager_intervention","title":"约谈瑞成集团高层确认竞品比较维度","assignee_user_id":"u_sales_002","priority":"urgent"}','pending_review','run_seed_001');

INSERT IGNORE INTO approval_record (tenant_id, approval_id, approval_type, run_id, risk_snapshot_id, customer_id, proposed_payload_json, status, requested_by_user_id, reviewer_user_id, reviewed_at, review_comment)
VALUES
('demo_tenant','appr_001','agent_task_draft','run_seed_001','risk_001','c_001','{"task_type":"manager_intervention","title":"主管介入星河教育报价风险","assignee_user_id":"u_sales_001","priority":"urgent","due_at":"tomorrow"}','pending','u_manager_001',NULL,NULL,NULL),
('demo_tenant','appr_003','agent_task_draft','run_seed_001','risk_003','c_003','{"task_type":"quote_follow","title":"跟进南禾商贸报价反馈","assignee_user_id":"u_sales_002","priority":"medium","due_at":"in_2_days"}','approved','u_manager_001','u_manager_001',DATE_SUB(NOW(), INTERVAL 20 MINUTE),'同意先由销售员低压力跟进'),
('demo_tenant','appr_006','agent_task_draft','run_seed_001','risk_006','c_006','{"task_type":"manager_intervention","title":"主管介入北桥医疗高金额风险","assignee_user_id":"u_sales_003","priority":"urgent","due_at":"tomorrow"}','pending','u_manager_001',NULL,NULL,NULL),
('demo_tenant','appr_011','agent_task_draft','run_seed_001','risk_011','c_011','{"task_type":"manager_intervention","title":"约谈瑞成集团高层确认竞品比较维度","assignee_user_id":"u_sales_002","priority":"urgent","due_at":"today"}','rejected','u_manager_001','u_manager_001',DATE_SUB(NOW(), INTERVAL 10 MINUTE),'先补充客户组织架构后再约高层');

INSERT IGNORE INTO sales_task (tenant_id, task_id, approval_id, customer_id, deal_id, assignee_user_id, creator_user_id, task_type, title, description, recommended_script, priority, status, due_at)
VALUES
('demo_tenant','task_003','appr_003','c_003','d_003','u_sales_002','u_manager_001','quote_follow','跟进南禾商贸报价反馈','确认客户内部讨论结果和预算边界。','您好，我这边不是催您做决定，只是想确认报价方案是否还有继续评估的必要。','medium','pending',DATE_ADD(NOW(), INTERVAL 2 DAY)),
('demo_tenant','task_007',NULL,'c_007','d_007','u_sales_001','u_manager_001','solution_follow','青木物流成交后交付衔接','确认交付联系人和启动会时间。','我们已经进入交付阶段，我想确认一下启动会参与人和业务目标。','medium','in_progress',DATE_ADD(NOW(), INTERVAL 3 DAY)),
('demo_tenant','task_012',NULL,'c_012','d_012','u_sales_003','u_manager_001','solution_follow','橙子科技技术评估资料准备','准备接口说明和安全机制说明。','我先把技术评估需要的接口和权限材料整理给您，方便技术团队判断。','medium','pending',DATE_ADD(NOW(), INTERVAL 4 DAY));

INSERT IGNORE INTO business_report (tenant_id, report_id, run_id, report_type, report_date, summary, metrics_json, risk_top_json, suggestions, created_by_user_id)
VALUES
('demo_tenant','report_001','run_seed_002','daily',CURDATE(),'今日销售漏斗整体可控，但报价阶段出现 4 个中高风险客户，其中 3 个需要主管优先介入。','{"new_customers":1,"effective_followups":7,"high_risk_customers":3,"pending_approvals":2}','[{"customer_id":"c_011","risk_score":95},{"customer_id":"c_006","risk_score":90},{"customer_id":"c_001","risk_score":85}]','建议主管优先处理瑞成集团、北桥医疗和星河教育三个高金额或竞品介入客户。','u_owner_001');

INSERT IGNORE INTO rag_document (tenant_id, document_id, doc_id, title, category, source_file, source_type, version, status)
VALUES
('demo_tenant','doc_sales_sop_v1','sales_sop_v1','InsightPilot 销售 SOP 知识库','sales_sop','01_销售 SOP.md','document','v1','active'),
('demo_tenant','doc_product_pricing_v1','product_pricing_v1','InsightPilot 示例产品资料与价格策略','product_pricing','02_产品资料与价格策略.md','document','v1','active'),
('demo_tenant','doc_objection_handling_v1','objection_handling_v1','InsightPilot 异议处理话术知识库','objection_handling','03_异议处理话术.md','document','v1','active');

INSERT IGNORE INTO rag_qa_pair (tenant_id, qa_id, doc_id, section_id, question, answer_preview, tags_json, source_type, milvus_collection, status)
VALUES
('demo_tenant','qa_obj_001_001','objection_handling_v1','OBJ-001','客户说价格太贵怎么办？','先不要马上降价，应先确认客户觉得贵的原因，是总预算有限，还是还没有看到系统能减少销售管理损失。','["异议处理","价格太贵","报价阶段"]','qa','insightpilot_qa_pairs','active'),
('demo_tenant','qa_obj_006_001','objection_handling_v1','OBJ-006','客户担心 AI 不可靠怎么解释？','可以说明 InsightPilot 不让 AI 直接做关键业务决策。风险分由规则引擎计算，任务必须主管确认。','["AI 可靠性","人工确认","规则引擎"]','qa','insightpilot_qa_pairs','active'),
('demo_tenant','qa_sop_004_001','sales_sop_v1','SOP-004','AI 可以直接创建销售任务吗？','不可以。AI 可以生成任务草稿，但不得绕过人工确认直接创建正式任务。','["任务生成","人工确认","Agent 安全"]','qa','insightpilot_qa_pairs','active');
