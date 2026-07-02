USE insightpilot;

INSERT IGNORE INTO tenant (tenant_id, tenant_name, status)
VALUES ('demo_tenant', 'InsightPilot 演示公司', 1);

INSERT IGNORE INTO sys_role (tenant_id, role_id, role_code, role_name, status, remark)
VALUES
('demo_tenant', 'role_admin', 'admin', '系统管理员', 1, '负责角色权限开关与用户角色分配'),
('demo_tenant', 'role_owner', 'owner', '老板', 1, '查看全局经营数据、报告与 Agent 执行链路'),
('demo_tenant', 'role_manager', 'manager', '销售主管', 1, '管理团队客户风险并审批 AI 任务'),
('demo_tenant', 'role_salesperson', 'salesperson', '销售员', 1, '跟进自己负责的客户和销售任务');

INSERT IGNORE INTO sys_permission (permission_id, permission_code, permission_name, module, action, description, status)
VALUES
('perm_crm_customer_read_self', 'crm:customer:read:self', '查看自己客户', 'crm', 'read', '销售员查看自己负责的客户', 1),
('perm_crm_customer_read_team', 'crm:customer:read:team', '查看团队客户', 'crm', 'read', '主管查看团队客户', 1),
('perm_crm_customer_read_all', 'crm:customer:read:all', '查看全部客户', 'crm', 'read', '老板查看全部客户', 1),
('perm_crm_risk_read_team', 'crm:risk:read:team', '查看团队风险', 'risk', 'read', '查看团队客户风险', 1),
('perm_crm_risk_read_all', 'crm:risk:read:all', '查看全部风险', 'risk', 'read', '查看全部客户风险', 1),
('perm_agent_run_risk', 'agent:run:risk_analysis', '运行风险扫描', 'agent', 'run', '触发客户风险扫描 Agent', 1),
('perm_agent_run_report', 'agent:run:business_report', '运行经营日报', 'agent', 'run', '触发经营日报 Agent', 1),
('perm_agent_log_read', 'agent:log:read', '查看 Agent 日志', 'agent', 'read', '查看 Agent Run 与 Step 链路', 1),
('perm_approval_review', 'approval:review:agent_task', '审批 AI 任务', 'approval', 'review', '审批 AI 生成的任务草稿', 1),
('perm_task_read_self', 'task:read:self', '查看自己任务', 'task', 'read', '查看自己负责的销售任务', 1),
('perm_task_read_team', 'task:read:team', '查看团队任务', 'task', 'read', '主管查看团队任务', 1),
('perm_task_read_all', 'task:read:all', '查看全部任务', 'task', 'read', '老板查看全部任务', 1),
('perm_report_read_team', 'report:read:team', '查看团队报告', 'report', 'read', '查看团队经营报告', 1),
('perm_report_read_all', 'report:read:all', '查看全部报告', 'report', 'read', '查看全局经营报告', 1),
('perm_system_rbac_manage', 'system:rbac:manage', '管理角色权限', 'system', 'manage', '系统管理员维护不同角色的功能权限开关', 1),
('perm_system_user_role_manage', 'system:user_role:manage', '管理用户角色', 'system', 'manage', '系统管理员维护用户与角色的分配关系', 1),
('perm_rag_ingest_run', 'rag:ingest:run', '运行 RAG 入库', 'rag', 'run', '触发 RAG 知识库入库任务', 1);

INSERT IGNORE INTO sys_user (tenant_id, user_id, username, password_hash, real_name, phone, email, status, is_deleted)
VALUES
('demo_tenant', 'u_admin_001', 'admin', 'pbkdf2_sha256$600000$8mM3UlAApitBEmZ-dUeyUg$vbcE5u_jhNww8bIxyiRZVPtQCFPSdZeyz0wsIVwTJu0', '系统管理员', '13800000000', 'admin@insightpilot.local', 1, 0),
('demo_tenant', 'u_owner_001', 'owner', 'pbkdf2_sha256$600000$sw3mgBMBpcW6KR1MAw1GcQ$xbMHWUVpkYmHfQ8fYywi5gidIzgmtXiVihPFPoN9Wt4', '林总', '13800000001', 'owner@insightpilot.local', 1, 0),
('demo_tenant', 'u_manager_001', 'manager', 'pbkdf2_sha256$600000$smTv8qJszI0dxhM8I0HWfw$RxZ6qjmDkDpdMOGAVynrf5gZJ7tdGIfu_o_UL3p3-zk', '周主管', '13800000002', 'manager@insightpilot.local', 1, 0),
('demo_tenant', 'u_sales_001', 'sales01', 'pbkdf2_sha256$600000$pIfpQoqyq64eTRgmHhUMgA$ED6hUlXATYFa8Ryv0OkHf7CaAuyKpzv1rxX5Wdb0_jg', '陈晨', '13800000003', 'sales01@insightpilot.local', 1, 0),
('demo_tenant', 'u_sales_002', 'sales02', 'pbkdf2_sha256$600000$pIfpQoqyq64eTRgmHhUMgA$ED6hUlXATYFa8Ryv0OkHf7CaAuyKpzv1rxX5Wdb0_jg', '何璐', '13800000004', 'sales02@insightpilot.local', 1, 0),
('demo_tenant', 'u_sales_003', 'sales03', 'pbkdf2_sha256$600000$pIfpQoqyq64eTRgmHhUMgA$ED6hUlXATYFa8Ryv0OkHf7CaAuyKpzv1rxX5Wdb0_jg', '吴桐', '13800000005', 'sales03@insightpilot.local', 1, 0);

INSERT IGNORE INTO sys_user_role (tenant_id, user_id, role_id)
VALUES
('demo_tenant', 'u_admin_001', 'role_admin'),
('demo_tenant', 'u_owner_001', 'role_owner'),
('demo_tenant', 'u_manager_001', 'role_manager'),
('demo_tenant', 'u_sales_001', 'role_salesperson'),
('demo_tenant', 'u_sales_002', 'role_salesperson'),
('demo_tenant', 'u_sales_003', 'role_salesperson');

INSERT IGNORE INTO sys_role_permission (tenant_id, role_id, permission_id)
VALUES
('demo_tenant', 'role_admin', 'perm_system_rbac_manage'),
('demo_tenant', 'role_admin', 'perm_system_user_role_manage'),
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
('demo_tenant','c_001','深圳星河教育科技','u_sales_001','教育培训','深圳','官网咨询','quotation','high','A','200-500人',60000,120000,DATE_ADD(CURDATE(), INTERVAL 20 DAY),'confirmed',1,NULL,DATE_SUB(NOW(), INTERVAL 22 DAY),'negative','报价后陷入沉默，客户明确提到竞品报价更低'),
('demo_tenant','c_002','杭州云帆软件','u_sales_001','软件服务','杭州','老客户转介绍','solution','medium','A','50-200人',40000,90000,DATE_ADD(CURDATE(), INTERVAL 35 DAY),'identified',0,DATE_ADD(NOW(), INTERVAL 2 DAY),DATE_SUB(NOW(), INTERVAL 3 DAY),'positive','客户认可风险看板，希望继续看试点方案'),
('demo_tenant','c_003','广州南和商贸','u_sales_002','批发零售','广州','展会线索','quotation','medium','B','50-100人',20000,50000,DATE_ADD(CURDATE(), INTERVAL 15 DAY),'identified',0,NULL,DATE_SUB(NOW(), INTERVAL 16 DAY),'neutral','报价之后说要内部讨论，但一直没有明确反馈'),
('demo_tenant','c_004','成都远景制造','u_sales_002','制造业','成都','电话开拓','communicated','high','A','500人以上',100000,200000,DATE_ADD(CURDATE(), INTERVAL 45 DAY),'confirmed',1,DATE_ADD(NOW(), INTERVAL 1 DAY),DATE_SUB(NOW(), INTERVAL 8 DAY),'neutral','竞品已经进场，但客户仍愿意继续看方案差异'),
('demo_tenant','c_005','北京麦田咨询','u_sales_003','企业服务','北京','内容营销','new_lead','low','C','20-50人',10000,30000,NULL,'unknown',0,NULL,NULL,'neutral','新线索，尚未完成首次有效触达'),
('demo_tenant','c_006','苏州北桥医疗','u_sales_003','医疗健康','苏州','老客户推荐','quotation','high','A','200-500人',80000,150000,DATE_ADD(CURDATE(), INTERVAL 10 DAY),'confirmed',0,NULL,DATE_SUB(NOW(), INTERVAL 31 DAY),'negative','高金额项目，客户担心预算审批和 AI 可控性'),
('demo_tenant','c_007','南京青木物流','u_sales_001','物流','南京','官网咨询','won','high','A','100-200人',50000,90000,DATE_SUB(CURDATE(), INTERVAL 5 DAY),'confirmed',0,DATE_ADD(NOW(), INTERVAL 20 DAY),DATE_SUB(NOW(), INTERVAL 2 DAY),'positive','已成交，处于交付衔接阶段'),
('demo_tenant','c_008','武汉江城餐饮连锁','u_sales_002','餐饮连锁','武汉','朋友介绍','communicated','medium','B','100-300人',30000,80000,DATE_ADD(CURDATE(), INTERVAL 60 DAY),'identified',0,DATE_ADD(NOW(), INTERVAL 5 DAY),DATE_SUB(NOW(), INTERVAL 6 DAY),'neutral','客户关注门店管理效率，希望看落地案例'),
('demo_tenant','c_009','西安矩阵传媒','u_sales_003','广告传媒','西安','广告投放','solution','medium','B','50-100人',20000,60000,DATE_ADD(CURDATE(), INTERVAL 30 DAY),'unknown',0,NULL,DATE_SUB(NOW(), INTERVAL 18 DAY),'neutral','方案发出后没有继续追进，热度明显下降'),
('demo_tenant','c_010','厦门蓝湾文旅','u_sales_001','文旅','厦门','展会线索','lost','low','C','20-50人',10000,20000,NULL,'identified',0,NULL,DATE_SUB(NOW(), INTERVAL 70 DAY),'negative','客户已经确认选择竞品，适合进入复盘案例'),
('demo_tenant','c_011','天津瑞成集团','u_sales_002','综合集团','天津','渠道推荐','quotation','high','A','500人以上',120000,260000,DATE_ADD(CURDATE(), INTERVAL 25 DAY),'confirmed',1,NULL,DATE_SUB(NOW(), INTERVAL 15 DAY),'negative','高金额报价后沉默，竞品给出了更低总价'),
('demo_tenant','c_012','长沙橙子科技','u_sales_003','软件服务','长沙','官网咨询','solution','medium','B','50-200人',30000,70000,DATE_ADD(CURDATE(), INTERVAL 40 DAY),'identified',0,DATE_ADD(NOW(), INTERVAL 4 DAY),DATE_SUB(NOW(), INTERVAL 4 DAY),'positive','技术团队认可方案，正在安排接口评估');

INSERT IGNORE INTO crm_contact (tenant_id, contact_id, customer_id, contact_name, title, phone, email, wechat, is_decision_maker)
VALUES
('demo_tenant','ct_001','c_001','王校长','校长','13900001001','wang@xinghe.local','wx_xinghe',1),
('demo_tenant','ct_002','c_002','李静','运营经理','13900001002','li@yunfan.local','wx_yunfan',1),
('demo_tenant','ct_003','c_003','赵敏','总经理','13900001003','zhao@nanhe.local','wx_nanhe',1),
('demo_tenant','ct_004','c_004','孙涛','销售总监','13900001004','sun@yuanjing.local','wx_yuanjing',1),
('demo_tenant','ct_005','c_005','刘蕾','项目协调人','13900001005','liu@maitian.local','wx_maitian',0),
('demo_tenant','ct_006','c_006','陈院长','院长','13900001006','chen@beiqiao.local','wx_beiqiao',1),
('demo_tenant','ct_007','c_007','蒋总','运营副总裁','13900001007','jiang@qingmu.local','wx_qingmu',1),
('demo_tenant','ct_008','c_008','何倩','数字化负责人','13900001008','he@jiangcheng.local','wx_jiangcheng',0),
('demo_tenant','ct_009','c_009','马辰','商务经理','13900001009','ma@juzhen.local','wx_juzhen',0),
('demo_tenant','ct_010','c_010','周航','招商主管','13900001010','zhou@lanwan.local','wx_lanwan',1),
('demo_tenant','ct_011','c_011','高翔','副总裁','13900001011','gao@ruicheng.local','wx_ruicheng',1),
('demo_tenant','ct_012','c_012','唐禾','技术经理','13900001012','tang@orange.local','wx_orange',0);

INSERT IGNORE INTO crm_deal (
  tenant_id, deal_id, customer_id, owner_user_id, deal_name, stage, amount,
  quote_amount, quoted_at, expected_close_at, closed_at, close_result, lost_reason
)
VALUES
('demo_tenant','d_001','c_001','u_sales_001','星河教育销售运营看板项目','quotation',88000,92000,DATE_SUB(NOW(), INTERVAL 18 DAY),DATE_ADD(CURDATE(), INTERVAL 20 DAY),NULL,'open',NULL),
('demo_tenant','d_002','c_002','u_sales_001','云帆软件试点版部署','solution',76000,NULL,NULL,DATE_ADD(CURDATE(), INTERVAL 35 DAY),NULL,'open',NULL),
('demo_tenant','d_003','c_003','u_sales_002','南和商贸客户风险看板','quotation',42000,45000,DATE_SUB(NOW(), INTERVAL 9 DAY),DATE_ADD(CURDATE(), INTERVAL 15 DAY),NULL,'open',NULL),
('demo_tenant','d_004','c_004','u_sales_002','远景制造多团队销售治理项目','communicated',160000,NULL,NULL,DATE_ADD(CURDATE(), INTERVAL 45 DAY),NULL,'open',NULL),
('demo_tenant','d_006','c_006','u_sales_003','北桥医疗经营驾驶舱','quotation',128000,138000,DATE_SUB(NOW(), INTERVAL 20 DAY),DATE_ADD(CURDATE(), INTERVAL 10 DAY),NULL,'open',NULL),
('demo_tenant','d_007','c_007','u_sales_001','青木物流任务闭环系统','won',68000,68000,DATE_SUB(NOW(), INTERVAL 18 DAY),DATE_SUB(CURDATE(), INTERVAL 5 DAY),DATE_SUB(NOW(), INTERVAL 5 DAY),'won',NULL),
('demo_tenant','d_009','c_009','u_sales_003','矩阵传媒销售 SOP 知识库','solution',52000,NULL,NULL,DATE_ADD(CURDATE(), INTERVAL 30 DAY),NULL,'open',NULL),
('demo_tenant','d_010','c_010','u_sales_001','蓝湾文旅营销试点','lost',18000,20000,DATE_SUB(NOW(), INTERVAL 80 DAY),DATE_SUB(CURDATE(), INTERVAL 70 DAY),DATE_SUB(NOW(), INTERVAL 70 DAY),'lost','客户最终选择竞品'),
('demo_tenant','d_011','c_011','u_sales_002','瑞成集团企业版试点','quotation',220000,238000,DATE_SUB(NOW(), INTERVAL 15 DAY),DATE_ADD(CURDATE(), INTERVAL 25 DAY),NULL,'open',NULL),
('demo_tenant','d_012','c_012','u_sales_003','橙子科技专业版试点','solution',62000,NULL,NULL,DATE_ADD(CURDATE(), INTERVAL 40 DAY),NULL,'open',NULL);

INSERT IGNORE INTO crm_follow_up_record (
  tenant_id, follow_up_id, customer_id, deal_id, owner_user_id, follow_up_type, content,
  sentiment, customer_feedback, next_action, next_follow_up_at, occurred_at
)
VALUES
('demo_tenant','fu_001','c_001','d_001','u_sales_001','wechat','客户表示竞品整体报价更低，目前内部还没有决定下一步。','negative','价格偏高，竞品已介入','建议主管介入，重新梳理价值点',NULL,DATE_SUB(NOW(), INTERVAL 22 DAY)),
('demo_tenant','fu_002','c_002','d_002','u_sales_001','meeting','客户认可风险识别与审批机制，希望尽快看到试点方案和上线节奏。','positive','认可产品方向','准备试点方案并约二次演示',DATE_ADD(NOW(), INTERVAL 2 DAY),DATE_SUB(NOW(), INTERVAL 3 DAY)),
('demo_tenant','fu_003','c_003','d_003','u_sales_002','phone','客户说报价要先拿去内部讨论预算，暂时给不出明确答复。','neutral','需要内部审批预算','一周后再次确认预算结论',NULL,DATE_SUB(NOW(), INTERVAL 16 DAY)),
('demo_tenant','fu_004','c_004','d_004','u_sales_002','meeting','客户正在对比竞品方案，但愿意继续看我们在审批闭环和审计上的差异。','neutral','竞品正在比较','整理差异化价值说明',DATE_ADD(NOW(), INTERVAL 1 DAY),DATE_SUB(NOW(), INTERVAL 8 DAY)),
('demo_tenant','fu_005','c_005',NULL,'u_sales_003','phone','首次触达时客户还没有明确需求，建议暂时保持轻跟进。','neutral','线索仍在培育','补齐客户背景信息',DATE_ADD(NOW(), INTERVAL 7 DAY),DATE_SUB(NOW(), INTERVAL 5 DAY)),
('demo_tenant','fu_006','c_006','d_006','u_sales_003','email','客户反馈预算审批暂缓，院方担心 AI 建议是否足够可控。','negative','担心预算和 AI 可靠性','建议主管介入解释审批与审计机制',NULL,DATE_SUB(NOW(), INTERVAL 31 DAY)),
('demo_tenant','fu_007','c_007','d_007','u_sales_001','meeting','双方已确认交付排期，客户希望下周完成启动会。','positive','准备进入交付阶段','确认启动会参会人',DATE_ADD(NOW(), INTERVAL 3 DAY),DATE_SUB(NOW(), INTERVAL 2 DAY)),
('demo_tenant','fu_008','c_008',NULL,'u_sales_002','meeting','客户最关心门店巡检和营运执行的追踪能力。','neutral','关注管理效率','补充同业案例',DATE_ADD(NOW(), INTERVAL 5 DAY),DATE_SUB(NOW(), INTERVAL 6 DAY)),
('demo_tenant','fu_009','c_009','d_009','u_sales_003','email','方案发出后没有后续反馈，客户可能把优先级下调了。','neutral','需要重新激活需求','尝试换一个切入口重新联系',NULL,DATE_SUB(NOW(), INTERVAL 18 DAY)),
('demo_tenant','fu_010','c_010','d_010','u_sales_001','phone','客户已确认和竞品签约，当前只保留关系维护。','negative','项目已流失','归档为流失案例',NULL,DATE_SUB(NOW(), INTERVAL 70 DAY)),
('demo_tenant','fu_011','c_011','d_011','u_sales_002','phone','客户提到竞品总价更低，集团高层还没拍板。','negative','竞品低价，高层犹豫','建议主管约高层会谈',NULL,DATE_SUB(NOW(), INTERVAL 15 DAY)),
('demo_tenant','fu_012','c_012','d_012','u_sales_003','meeting','客户技术团队认可方案，计划下周开始接口评估。','positive','技术路线认可','准备接口和权限说明',DATE_ADD(NOW(), INTERVAL 4 DAY),DATE_SUB(NOW(), INTERVAL 4 DAY));

INSERT IGNORE INTO agent_run (
  tenant_id, run_id, user_id, run_type, graph_name, input_json, output_json,
  status, started_at, finished_at, total_duration_ms
)
VALUES
('demo_tenant','run_seed_001','u_manager_001','risk_analysis','risk_analysis_graph','{"scope":"team"}','{"risk_count":4,"approval_count":4,"items":["risk_001","risk_003","risk_006","risk_011"]}','awaiting_approval',DATE_SUB(NOW(), INTERVAL 65 MINUTE),DATE_SUB(NOW(), INTERVAL 62 MINUTE),182000),
('demo_tenant','run_seed_002','u_owner_001','business_report','business_report_graph','{"report_type":"daily","report_date":"today"}','{"report_id":"report_001","high_risk_customers":3,"pending_approvals":2}','success',DATE_SUB(NOW(), INTERVAL 32 MINUTE),DATE_SUB(NOW(), INTERVAL 31 MINUTE),47000);

INSERT IGNORE INTO agent_step (
  tenant_id, step_id, run_id, node_name, tool_name, required_permissions_json,
  input_json, output_json, status, started_at, finished_at, duration_ms
)
VALUES
('demo_tenant','step_seed_001','run_seed_001','load_crm_data','crm_query_tool','["crm:customer:read:team"]','{"scope":"team"}','{"customer_count":12,"deal_count":10}','success',DATE_SUB(NOW(), INTERVAL 65 MINUTE),DATE_SUB(NOW(), INTERVAL 65 MINUTE),1800),
('demo_tenant','step_seed_002','run_seed_001','calculate_rule_risk','risk_rule_tool','["crm:risk:read:team"]','{"customer_count":12}','{"candidate_count":4,"high":3,"medium":1}','success',DATE_SUB(NOW(), INTERVAL 64 MINUTE),DATE_SUB(NOW(), INTERVAL 64 MINUTE),3400),
('demo_tenant','step_seed_003','run_seed_001','retrieve_sales_knowledge','rag_retrieval_tool','["crm:risk:read:team"]','{"query":"报价后客户迟迟不回复怎么办"}','{"retrieval_count":4,"success_count":4,"trace_ids":["trace_001","trace_003","trace_006","trace_011"]}','success',DATE_SUB(NOW(), INTERVAL 63 MINUTE),DATE_SUB(NOW(), INTERVAL 63 MINUTE),2600),
('demo_tenant','step_seed_004','run_seed_001','generate_task_draft','llm_risk_advice_tool','["approval:review:agent_task"]','{"candidate_count":4}','{"created_count":4,"approval_ids":["appr_001","appr_003","appr_006","appr_011"]}','success',DATE_SUB(NOW(), INTERVAL 62 MINUTE),DATE_SUB(NOW(), INTERVAL 62 MINUTE),4200),
('demo_tenant','step_seed_101','run_seed_002','collect_business_metrics','business_metric_sql_tool','["report:read:all"]','{}','{"high_risk_customers":3,"pending_approvals":2,"active_tasks":3}','success',DATE_SUB(NOW(), INTERVAL 32 MINUTE),DATE_SUB(NOW(), INTERVAL 32 MINUTE),1600),
('demo_tenant','step_seed_102','run_seed_002','analyze_risk_top','risk_snapshot_sql_tool','["report:read:all"]','{}','{"risk_top_count":3,"customers":["c_011","c_006","c_001"]}','success',DATE_SUB(NOW(), INTERVAL 32 MINUTE),DATE_SUB(NOW(), INTERVAL 31 MINUTE),1500),
('demo_tenant','step_seed_103','run_seed_002','generate_report_narrative','llm_report_narrative_tool','["report:read:all"]','{}','{"summary":"报价阶段暴露 3 个高风险客户","suggestions":"主管优先处理瑞成集团、北桥医疗和星河教育"}','success',DATE_SUB(NOW(), INTERVAL 31 MINUTE),DATE_SUB(NOW(), INTERVAL 31 MINUTE),2800),
('demo_tenant','step_seed_104','run_seed_002','persist_business_report','business_report_repository','["report:read:all"]','{}','{"report_id":"report_001"}','success',DATE_SUB(NOW(), INTERVAL 31 MINUTE),DATE_SUB(NOW(), INTERVAL 31 MINUTE),700);

INSERT IGNORE INTO customer_risk_snapshot (
  tenant_id, risk_snapshot_id, customer_id, deal_id, owner_user_id, risk_score, risk_level,
  rule_hits_json, evidence_json, llm_reason, llm_suggestion, suggested_task_json, status, generated_by_run_id
)
VALUES
('demo_tenant','risk_001','c_001','d_001','u_sales_001',85,'high','[{"rule_code":"quote_no_response_14d","score":35},{"rule_code":"competitor_involved","score":20},{"rule_code":"negative_sentiment","score":15},{"rule_code":"missing_next_follow","score":10}]','{"quoted_days":18,"competitor_involved":true,"last_sentiment":"negative","rag_trace_id":"trace_001"}','客户报价后 18 天没有明确回应，同时已经提到竞品低价，属于高概率流失客户。','建议主管介入重新确认客户评估维度，避免销售只在价格层面反复拉扯。','{"task_type":"manager_intervention","title":"主管介入星河教育报价风险","assignee_user_id":"u_sales_001","priority":"urgent","recommended_script":"先确认客户是在比较价格，还是担心后续执行与审批效率，再对齐价值点。"}','pending_review','run_seed_001'),
('demo_tenant','risk_003','c_003','d_003','u_sales_002',55,'medium','[{"rule_code":"quote_no_response_7d","score":20},{"rule_code":"no_follow_14d","score":20},{"rule_code":"missing_next_follow","score":10}]','{"quoted_days":9,"no_follow_days":16,"rag_trace_id":"trace_003"}','客户报价后进入内部讨论，但销售没有补下一次跟进时间，热度正在自然下滑。','建议销售员以低压力方式确认预算讨论进度，并主动给出下一步推进建议。','{"task_type":"quote_follow","title":"跟进南和商贸报价反馈","assignee_user_id":"u_sales_002","priority":"medium","recommended_script":"这次不是催决策，只是想确认报价方案是否还值得继续评估。"}','pending_review','run_seed_001'),
('demo_tenant','risk_006','c_006','d_006','u_sales_003',90,'high','[{"rule_code":"quote_no_response_14d","score":35},{"rule_code":"no_follow_30d","score":35},{"rule_code":"negative_sentiment","score":15},{"rule_code":"high_value_deal","score":10}]','{"quoted_days":20,"no_follow_days":31,"amount":128000,"rag_trace_id":"trace_006"}','客户是高金额项目，但预算审批停滞且对 AI 可控性有疑虑，继续拖延会快速丢失窗口。','建议主管出面解释规则打分、人工审批和审计链路，先消除“AI 不可控”的心理阻力。','{"task_type":"manager_intervention","title":"主管介入北桥医疗高金额风险","assignee_user_id":"u_sales_003","priority":"urgent","recommended_script":"我们不是让 AI 直接做决定，而是先用规则识别风险，再由主管确认动作。"}','pending_review','run_seed_001'),
('demo_tenant','risk_011','c_011','d_011','u_sales_002',95,'high','[{"rule_code":"quote_no_response_14d","score":35},{"rule_code":"competitor_involved","score":20},{"rule_code":"negative_sentiment","score":15},{"rule_code":"high_value_deal","score":10},{"rule_code":"missing_next_follow","score":10}]','{"quoted_days":15,"competitor_involved":true,"amount":220000,"rag_trace_id":"trace_011"}','客户金额高、竞品低价压力强、集团高层还没有拍板，是今天优先级最高的流失风险。','建议主管直接约高层对齐价值和实施风险，不要只靠普通销售继续微信催进。','{"task_type":"manager_intervention","title":"约谈瑞成集团高层确认竞品比较维度","assignee_user_id":"u_sales_002","priority":"urgent","recommended_script":"与其继续比较单点价格，不如一起确认哪些流程和管理损耗才是集团真正关心的。"}','pending_review','run_seed_001');

INSERT IGNORE INTO approval_record (
  tenant_id, approval_id, approval_type, run_id, risk_snapshot_id, customer_id,
  proposed_payload_json, status, requested_by_user_id, reviewer_user_id, reviewed_at, review_comment
)
VALUES
('demo_tenant','appr_001','agent_task_draft','run_seed_001','risk_001','c_001','{"task_type":"manager_intervention","title":"主管介入星河教育报价风险","assignee_user_id":"u_sales_001","priority":"urgent","due_at":"tomorrow","description":"主管陪同销售再次确认客户比较逻辑"}','pending','u_manager_001',NULL,NULL,NULL),
('demo_tenant','appr_003','agent_task_draft','run_seed_001','risk_003','c_003','{"task_type":"quote_follow","title":"跟进南和商贸报价反馈","assignee_user_id":"u_sales_002","priority":"medium","due_at":"in_2_days","description":"确认内部预算讨论结论"}','approved','u_manager_001','u_manager_001',DATE_SUB(NOW(), INTERVAL 20 MINUTE),'同意先由销售低压力跟进，暂不需要主管出面'),
('demo_tenant','appr_006','agent_task_draft','run_seed_001','risk_006','c_006','{"task_type":"manager_intervention","title":"主管介入北桥医疗高金额风险","assignee_user_id":"u_sales_003","priority":"urgent","due_at":"tomorrow","description":"由主管解释 AI 审批与审计机制"}','pending','u_manager_001',NULL,NULL,NULL),
('demo_tenant','appr_011','agent_task_draft','run_seed_001','risk_011','c_011','{"task_type":"manager_intervention","title":"约谈瑞成集团高层确认竞品比较维度","assignee_user_id":"u_sales_002","priority":"urgent","due_at":"today","description":"准备高层沟通提纲与价值对齐材料"}','rejected','u_manager_001','u_manager_001',DATE_SUB(NOW(), INTERVAL 10 MINUTE),'先补齐客户组织关系图和历史报价对比，再安排高层会谈');

INSERT IGNORE INTO sales_task (
  tenant_id, task_id, approval_id, customer_id, deal_id, assignee_user_id, creator_user_id,
  task_type, title, description, recommended_script, priority, status, due_at
)
VALUES
('demo_tenant','task_003','appr_003','c_003','d_003','u_sales_002','u_manager_001','quote_follow','跟进南和商贸报价反馈','确认客户内部预算讨论结论，并把下一次明确时间点约出来。','这次不是催您做决定，只是想确认这份报价是否还值得继续评估。','medium','pending',DATE_ADD(NOW(), INTERVAL 2 DAY)),
('demo_tenant','task_007',NULL,'c_007','d_007','u_sales_001','u_manager_001','delivery_handoff','青木物流成交后交付衔接','确认交付负责人、启动会时间和上线前准备事项。','我们已经进入交付阶段，这次主要想把启动会参与人和业务目标先对齐好。','medium','in_progress',DATE_ADD(NOW(), INTERVAL 3 DAY)),
('demo_tenant','task_012',NULL,'c_012','d_012','u_sales_003','u_manager_001','solution_follow','橙子科技技术评估资料准备','整理接口说明、权限控制和安全机制说明。','我先把技术评估需要的接口和权限材料整理给您，方便技术团队快速判断。','medium','pending',DATE_ADD(NOW(), INTERVAL 4 DAY));

INSERT IGNORE INTO approval_task_event (
  tenant_id, event_id, entity_type, entity_id, approval_id, task_id, customer_id,
  risk_snapshot_id, action_type, operator_user_id, note, detail_json, happened_at
)
VALUES
('demo_tenant','evt_seed_appr_001_created','approval','appr_001','appr_001',NULL,'c_001','risk_001','approval_created','u_manager_001','AI 风险建议已进入人工审批队列','{"approval_type":"agent_task_draft","priority":"urgent"}',DATE_SUB(NOW(), INTERVAL 62 MINUTE)),
('demo_tenant','evt_seed_appr_003_created','approval','appr_003','appr_003',NULL,'c_003','risk_003','approval_created','u_manager_001','AI 风险建议已进入人工审批队列','{"approval_type":"agent_task_draft","priority":"medium"}',DATE_SUB(NOW(), INTERVAL 62 MINUTE)),
('demo_tenant','evt_seed_appr_003_approved','approval','appr_003','appr_003',NULL,'c_003','risk_003','approval_approved','u_manager_001','同意先由销售低压力跟进，暂不需要主管出面','{"review_comment":"同意先由销售低压力跟进，暂不需要主管出面"}',DATE_SUB(NOW(), INTERVAL 20 MINUTE)),
('demo_tenant','evt_seed_appr_006_created','approval','appr_006','appr_006',NULL,'c_006','risk_006','approval_created','u_manager_001','AI 风险建议已进入人工审批队列','{"approval_type":"agent_task_draft","priority":"urgent"}',DATE_SUB(NOW(), INTERVAL 62 MINUTE)),
('demo_tenant','evt_seed_appr_011_created','approval','appr_011','appr_011',NULL,'c_011','risk_011','approval_created','u_manager_001','AI 风险建议已进入人工审批队列','{"approval_type":"agent_task_draft","priority":"urgent"}',DATE_SUB(NOW(), INTERVAL 62 MINUTE)),
('demo_tenant','evt_seed_appr_011_rejected','approval','appr_011','appr_011',NULL,'c_011','risk_011','approval_rejected','u_manager_001','先补齐客户组织关系图和历史报价对比，再安排高层会谈','{"review_comment":"先补齐客户组织关系图和历史报价对比，再安排高层会谈"}',DATE_SUB(NOW(), INTERVAL 10 MINUTE)),
('demo_tenant','evt_seed_task_003_created','task','task_003','appr_003','task_003','c_003','risk_003','task_created','u_manager_001','审批通过后已创建正式销售任务','{"title":"跟进南和商贸报价反馈","priority":"medium"}',DATE_SUB(NOW(), INTERVAL 20 MINUTE)),
('demo_tenant','evt_seed_task_007_created','task','task_007',NULL,'task_007','c_007',NULL,'task_created','u_manager_001','任务已创建，等待执行','{"title":"青木物流成交后交付衔接","priority":"medium"}',DATE_SUB(NOW(), INTERVAL 2 DAY)),
('demo_tenant','evt_seed_task_007_progress','task','task_007',NULL,'task_007','c_007',NULL,'task_in_progress','u_sales_001','任务已开始执行','{"status":"in_progress"}',DATE_SUB(NOW(), INTERVAL 1 DAY)),
('demo_tenant','evt_seed_task_012_created','task','task_012',NULL,'task_012','c_012',NULL,'task_created','u_manager_001','任务已创建，等待执行','{"title":"橙子科技技术评估资料准备","priority":"medium"}',DATE_SUB(NOW(), INTERVAL 4 DAY));

INSERT IGNORE INTO business_report (
  tenant_id, report_id, run_id, report_type, report_date, summary, metrics_json,
  risk_top_json, suggestions, created_by_user_id
)
VALUES
('demo_tenant','report_001','run_seed_002','daily',CURDATE(),'今日报价阶段暴露 3 个高风险客户，其中瑞成集团、北桥医疗和星河教育都需要主管优先介入。','{"new_customers":1,"effective_followups":7,"high_risk_customers":3,"pending_approvals":2,"active_tasks":3}','[{"customer_id":"c_011","risk_score":95},{"customer_id":"c_006","risk_score":90},{"customer_id":"c_001","risk_score":85}]','建议主管优先处理瑞成集团、北桥医疗和星河教育三条高价值风险线，同时尽快消化待审批动作，避免建议停留在纸面。','u_owner_001');

INSERT IGNORE INTO rag_document (tenant_id, document_id, doc_id, title, category, source_file, source_type, version, status)
VALUES
('demo_tenant','doc_sales_sop_v1','sales_sop_v1','InsightPilot 销售 SOP 知识库','sales_sop','01_销售_SOP.md','document','v1','active'),
('demo_tenant','doc_product_pricing_v1','product_pricing_v1','InsightPilot 产品与定价资料','product_pricing','02_产品与定价资料.md','document','v1','active'),
('demo_tenant','doc_objection_handling_v1','objection_handling_v1','InsightPilot 异议处理话术库','objection_handling','03_异议处理话术.md','document','v1','active');

INSERT IGNORE INTO rag_qa_pair (
  tenant_id, qa_id, doc_id, section_id, question, answer_preview, tags_json,
  source_type, milvus_collection, status
)
VALUES
('demo_tenant','qa_obj_001_001','objection_handling_v1','OBJ-001','客户说价格太贵怎么办？','不要急着降价，先确认客户觉得“贵”是预算有限，还是还没有看到系统能减少多少管理损耗。','["异议处理","价格太贵","报价阶段"]','qa','insightpilot_qa_pairs','active'),
('demo_tenant','qa_obj_006_001','objection_handling_v1','OBJ-006','客户担心 AI 不可靠应该怎么解释？','可以说明 InsightPilot 不会让 AI 直接做关键业务决策。风险分由规则引擎计算，任务必须经过主管审批。','["AI 可靠性","人工确认","规则引擎"]','qa','insightpilot_qa_pairs','active'),
('demo_tenant','qa_sop_004_001','sales_sop_v1','SOP-004','AI 可以直接创建销售任务吗？','不可以。AI 只能生成任务草稿，必须经过主管人工确认后，才会创建正式销售任务。','["任务生成","人工确认","Agent 安全"]','qa','insightpilot_qa_pairs','active');

INSERT IGNORE INTO rag_retrieval_trace (
  tenant_id, trace_id, run_id, user_id, original_query, rewritten_query, strategy,
  rewrite_ms, embed_ms, search_ms, rerank_ms, total_ms, top_k, hit_count
)
VALUES
('demo_tenant','trace_001','run_seed_001','u_manager_001','报价后客户一直不回复怎么办','报价后客户无回应且竞品介入时，销售应该如何重新建立价值感','hybrid_rrf_rerank',45,118,236,92,491,3,3),
('demo_tenant','trace_003','run_seed_001','u_manager_001','报价发出后客户没反馈怎么办','客户说内部讨论预算，但销售长时间没有下一次跟进时间，应该如何低压力推进','hybrid_rrf_rerank',38,109,214,86,447,3,3),
('demo_tenant','trace_006','run_seed_001','u_manager_001','客户担心 AI 不可靠怎么办','医疗客户担心 AI 可控性和预算审批时，主管应该如何解释流程安全性','hybrid_rrf_rerank',41,122,229,98,490,3,3),
('demo_tenant','trace_011','run_seed_001','u_manager_001','高金额客户被竞品低价压制怎么办','集团客户在高金额报价阶段被竞品低价影响时，主管应如何争取高层会谈','hybrid_rrf_rerank',43,116,240,94,493,3,3);

INSERT IGNORE INTO rag_retrieval_hit (
  tenant_id, trace_id, hit_id, source_collection, source_type, doc_id, section_id,
  source_pk, rank_no, dense_score, sparse_score, rrf_score, rerank_score, text_preview
)
VALUES
('demo_tenant','trace_001','hit_001_1','insightpilot_qa_pairs','qa','objection_handling_v1','OBJ-001','qa_obj_001_001',1,0.842110,0.712500,0.931250,0.912000,'客户说价格太贵时，先确认是真预算不足，还是还没有理解系统带来的管理收益。'),
('demo_tenant','trace_001','hit_001_2','insightpilot_document_chunks','document','sales_sop_v1','SOP-014','chunk_sop_014',2,0.801220,0.693100,0.884200,0.861000,'对于报价后沉默客户，不要只催回复，应先找出客户当前停滞的真实原因。'),
('demo_tenant','trace_001','hit_001_3','insightpilot_document_chunks','document','product_pricing_v1','PRI-003','chunk_price_003',3,0.774520,0.655000,0.842100,0.833000,'高价值项目需要从审批效率、团队执行和可审计性解释整体价值，而不是只谈价格。'),
('demo_tenant','trace_003','hit_003_1','insightpilot_document_chunks','document','sales_sop_v1','SOP-009','chunk_sop_009',1,0.833210,0.701200,0.918210,0.901000,'客户说内部讨论时，销售要主动约定下一个明确时间点，而不是等待客户自己回头。'),
('demo_tenant','trace_003','hit_003_2','insightpilot_qa_pairs','qa','sales_sop_v1','SOP-004','qa_sop_004_001',2,0.779000,0.640100,0.856400,0.844000,'AI 不能直接创建任务，必须经过主管审批后再进入正式执行。'),
('demo_tenant','trace_003','hit_003_3','insightpilot_document_chunks','document','objection_handling_v1','OBJ-002','chunk_obj_002',3,0.744300,0.621000,0.829500,0.818000,'低压力跟进的关键是先确认评估是否继续，而不是直接催促客户表态。'),
('demo_tenant','trace_006','hit_006_1','insightpilot_qa_pairs','qa','objection_handling_v1','OBJ-006','qa_obj_006_001',1,0.851230,0.721500,0.935120,0.920000,'当客户担心 AI 不可靠时，要解释系统由规则引擎定级、主管审批动作、Trace 留痕。'),
('demo_tenant','trace_006','hit_006_2','insightpilot_document_chunks','document','sales_sop_v1','SOP-021','chunk_sop_021',2,0.792100,0.671000,0.871200,0.860000,'高金额客户如果拖在预算审批阶段，主管介入比继续由销售单线跟进更有效。'),
('demo_tenant','trace_006','hit_006_3','insightpilot_document_chunks','document','product_pricing_v1','PRI-007','chunk_price_007',3,0.758800,0.630500,0.838300,0.827000,'面对预算疑虑时，要给客户清晰的分阶段落地路径和风险控制机制。'),
('demo_tenant','trace_011','hit_011_1','insightpilot_document_chunks','document','sales_sop_v1','SOP-018','chunk_sop_018',1,0.847500,0.709000,0.929300,0.915000,'高金额客户被竞品低价压制时，应该优先争取高层会谈，不要只靠一线微信追进。'),
('demo_tenant','trace_011','hit_011_2','insightpilot_document_chunks','document','product_pricing_v1','PRI-005','chunk_price_005',2,0.804600,0.682200,0.883100,0.869000,'对集团客户要把价格对比拉回到管理损耗、审批链路和跨团队协同收益。'),
('demo_tenant','trace_011','hit_011_3','insightpilot_qa_pairs','qa','objection_handling_v1','OBJ-001','qa_obj_001_001',3,0.771100,0.648000,0.844700,0.836000,'客户说价格贵，不一定是预算问题，也可能是价值点没有被看见。');
