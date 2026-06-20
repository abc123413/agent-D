import { useState } from 'react'
import {
  Card, Steps, Form, Input, Select, Button, Checkbox, InputNumber,
  Slider, Switch, Space, Result, Typography, message, Alert,
} from 'antd'
import { CopyOutlined, CheckOutlined } from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import { agentsApi, cronApi } from '@/services/api'
import { useNavigate } from 'react-router-dom'

const { TextArea } = Input
const { Paragraph } = Typography

const AGENT_TYPES = [
  { value: 'code_review', label: '代码审查' },
  { value: 'customer_service', label: '智能客服' },
  { value: 'resume_screening', label: '简历筛选' },
  { value: 'contract_review', label: '合同审核' },
  { value: 'schedule_management', label: '日程管理' },
  { value: 'info_retrieval', label: '信息检索' },
  { value: 'custom', label: '自定义' },
]

const ALL_TOOLS = [
  { value: 'git_diff', label: 'git_diff - Git差异获取' },
  { value: 'git_log', label: 'git_log - Git日志查询' },
  { value: 'file_reader', label: 'file_reader - 文件读取' },
  { value: 'list_directory', label: 'list_directory - 目录列表' },
  { value: 'search_files', label: 'search_files - 文件搜索' },
  { value: 'shell_run', label: 'shell_run - Shell命令执行' },
  { value: 'http_request', label: 'http_request - HTTP请求' },
]

const SECURITY_CHECKS = [
  { value: 'sql_injection', label: 'SQL注入' },
  { value: 'xss', label: 'XSS漏洞' },
  { value: 'hardcoded_secrets', label: '硬编码密钥' },
  { value: 'command_injection', label: '命令注入' },
  { value: 'ssrf', label: 'SSRF' },
  { value: 'insecure_deserialization', label: '不安全反序列化' },
  { value: 'prototype_pollution', label: '原型污染(JS)' },
  { value: 'jwt_issues', label: 'JWT安全问题' },
  { value: 'path_traversal', label: '路径穿越' },
  { value: 'unsafe_redirect', label: '开放重定向' },
]

export default function AgentCreate() {
  const [current, setCurrent] = useState(0)
  const [form] = Form.useForm()
  const [createdResult, setCreatedResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [yamlPreview, setYamlPreview] = useState('')
  const navigate = useNavigate()

  const agentType = Form.useWatch('agent_type', form)

  const steps = [
    { title: '基础信息' },
    { title: '工具与能力' },
    { title: '触发方式' },
    { title: '业务规则' },
    { title: '确认创建' },
  ]

  const next = () => {
    form.validateFields().then(() => {
      if (current === 3) {
        buildYamlPreview()
      }
      setCurrent(current + 1)
    }).catch(() => {})
  }

  const prev = () => setCurrent(current - 1)

  const buildYamlPreview = () => {
    const values = form.getFieldsValue(true)
    const preview = `name: ${values.name}
display_name: ${values.display_name}
version: ${values.version || '1.0.0'}
description: ${values.description || ''}
enabled: true
type: ${values.agent_type}

tools:
${(values.tools || []).map((t: string) => `  - ${t}`).join('\n')}

webhook_config:
  platform: ${values.platform || 'github'}
  secret: ${values.webhook_secret || '(自动生成)'}

rules:
  pass_score: ${values.pass_score || 70}
  security_checks: ${JSON.stringify(values.security_checks || [])}
`
    setYamlPreview(preview)
  }

  const handleCreate = async () => {
    setLoading(true)
    try {
      const values = form.getFieldsValue(true)
      const payload = {
        name: values.name,
        display_name: values.display_name,
        agent_type: values.agent_type,
        description: values.description || '',
        version: values.version || '1.0.0',
        tools: values.tools || [],
        webhook_config: {
          platform: values.platform,
          secret: values.webhook_secret,
          trigger_events: values.trigger_events,
          approve_action: values.approve_action,
          reject_action: values.reject_action,
          ticket_platform: values.ticket_platform,
          api_base: values.api_base,
          auto_reply: values.auto_reply,
        },
        rules_config: {
          pass_score: values.pass_score,
          security_checks: values.security_checks,
          quality_checks: values.quality_checks,
          standards_checks: values.standards_checks,
          linter_cmd: values.linter_cmd,
          sentiment_detection: values.sentiment_detection,
          escalate_rules: values.escalate_rules,
          dimensions: values.dimensions,
          anti_bias: values.anti_bias,
        },
      }
      const res = await agentsApi.create(payload)
      setCreatedResult(res.data)

      // 如果配置了定时触发，创建cron任务
      if (values.trigger_mode === 'cron' && values.cron_expr) {
        const expr = Array.isArray(values.cron_expr) ? values.cron_expr[0] : values.cron_expr
        await cronApi.create(values.name, expr, values.cron_input || '').catch(() => {})
      }

      setCurrent(5)
      message.success('Agent创建成功')
    } catch (e: any) {
      message.error(e.response?.data?.detail || '创建失败')
    }
    setLoading(false)
  }

  const copyText = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('已复制')
  }

  return (
    <div>
      <Card title="创建新Agent">
        {current < 5 && (
          <Steps current={current} items={steps} style={{ marginBottom: 32 }} />
        )}

        <Form form={form} layout="vertical" initialValues={{ version: '1.0.0', pass_score: 70, anti_bias: true }}>
          {/* Step 1: 基础信息 */}
          <div style={{ display: current === 0 ? 'block' : 'none' }}>
            <Form.Item name="name" label="Agent标识名" rules={[{ required: true, message: '请输入英文标识' }]}
              extra="英文+下划线，如 code_review">
              <Input placeholder="my_agent" />
            </Form.Item>
            <Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}>
              <Input placeholder="我的智能Agent" />
            </Form.Item>
            <Form.Item name="agent_type" label="Agent类型" rules={[{ required: true }]}>
              <Select options={AGENT_TYPES} placeholder="选择类型" />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <TextArea rows={3} placeholder="描述这个Agent的用途" />
            </Form.Item>
            <Form.Item name="version" label="版本">
              <Input />
            </Form.Item>
          </div>

          {/* Step 2: 工具与能力 */}
          <div style={{ display: current === 1 ? 'block' : 'none' }}>
            <Form.Item name="tools" label="可用工具">
              <Checkbox.Group>
                <Space direction="vertical">
                  {ALL_TOOLS.map((t) => (
                    <Checkbox key={t.value} value={t.value}>{t.label}</Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            </Form.Item>
            <Form.Item name="max_rounds" label="最大工具调用轮次" extra="Agent每次执行最多调用工具的轮次">
              <InputNumber min={1} max={10} defaultValue={5} />
            </Form.Item>
          </div>

          {/* Step 3: 触发方式 */}
          <div style={{ display: current === 2 ? 'block' : 'none' }}>
            {renderWebhookConfig(agentType, form)}
          </div>

          {/* Step 4: 业务规则 */}
          <div style={{ display: current === 3 ? 'block' : 'none' }}>
            {renderRulesConfig(agentType)}
          </div>

          {/* Step 5: 确认 */}
          <div style={{ display: current === 4 ? 'block' : 'none' }}>
            <Alert message="请确认以下配置，点击创建后Agent将立即可用" type="info" style={{ marginBottom: 16 }} />
            <div style={{ height: 300, border: '1px solid #d9d9d9', borderRadius: 4 }}>
              <Editor
                height="100%"
                language="yaml"
                value={yamlPreview}
                options={{ minimap: { enabled: false }, readOnly: true, fontSize: 13 }}
              />
            </div>
          </div>
        </Form>

        {/* 创建成功 */}
        {current === 5 && createdResult && (
          <Result
            status="success"
            title="Agent创建成功"
            subTitle={`${createdResult.agent_name} 已就绪`}
            extra={[
              <Button type="primary" key="manage" onClick={() => navigate('/agents')}>
                前往Agent管理
              </Button>,
              <Button key="new" onClick={() => { setCurrent(0); setCreatedResult(null) }}>
                继续创建
              </Button>,
            ]}
          >
            {createdResult.deploy_info?.webhook_url && (
              <Card size="small" title="Webhook URL" style={{ textAlign: 'left', marginTop: 16 }}>
                <Space>
                  <code>{createdResult.deploy_info.webhook_url}</code>
                  <Button
                    size="small" icon={<CopyOutlined />}
                    onClick={() => copyText(createdResult.deploy_info.webhook_url)}
                  />
                </Space>
              </Card>
            )}
            {createdResult.deploy_info?.setup_guide && (
              <Card size="small" title="部署指南" style={{ textAlign: 'left', marginTop: 12 }}>
                <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
                  {createdResult.deploy_info.setup_guide}
                </pre>
              </Card>
            )}
          </Result>
        )}

        {/* 底部按钮 */}
        {current < 5 && (
          <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between' }}>
            <Button disabled={current === 0} onClick={prev}>上一步</Button>
            <Space>
              {current < 4 && <Button type="primary" onClick={next}>下一步</Button>}
              {current === 4 && (
                <Button type="primary" loading={loading} onClick={handleCreate}>
                  创建Agent
                </Button>
              )}
            </Space>
          </div>
        )}
      </Card>
    </div>
  )
}

function renderWebhookConfig(agentType: string, form: any) {
  if (agentType === 'code_review') {
    return (
      <>
        <Form.Item name="platform" label="代码托管平台" initialValue="github">
          <Select options={[
            { value: 'github', label: 'GitHub' },
            { value: 'gitlab', label: 'GitLab' },
            { value: 'gitee', label: 'Gitee' },
          ]} />
        </Form.Item>
        <Form.Item name="webhook_secret" label="Webhook Secret" extra="用于验证webhook请求签名">
          <Input.Password placeholder="留空将自动生成" />
        </Form.Item>
        <Form.Item name="trigger_events" label="触发事件" initialValue={['opened', 'synchronize']}>
          <Checkbox.Group options={[
            { value: 'opened', label: 'PR创建' },
            { value: 'synchronize', label: 'PR更新(push)' },
            { value: 'reopened', label: 'PR重新打开' },
          ]} />
        </Form.Item>
        <Form.Item name="approve_action" label="通过动作" initialValue="approve">
          <Select options={[
            { value: 'approve', label: '自动Approve' },
            { value: 'comment', label: '仅评论' },
          ]} />
        </Form.Item>
        <Form.Item name="reject_action" label="不通过动作" initialValue="request_changes">
          <Select options={[
            { value: 'request_changes', label: 'Request Changes' },
            { value: 'draft', label: '评论+标记Draft' },
          ]} />
        </Form.Item>
      </>
    )
  }

  if (agentType === 'customer_service') {
    return (
      <>
        <Form.Item name="ticket_platform" label="工单平台" initialValue="zendesk">
          <Select options={[
            { value: 'zendesk', label: 'Zendesk' },
            { value: 'jira', label: 'Jira Service Management' },
            { value: 'feishu', label: '飞书服务台' },
          ]} />
        </Form.Item>
        <Form.Item name="api_base" label="平台API地址">
          <Input placeholder="https://your-domain.zendesk.com" />
        </Form.Item>
        <Form.Item name="platform_token" label="认证Token">
          <Input.Password placeholder="平台API Token" />
        </Form.Item>
        <Form.Item name="auto_reply" label="自动回复" valuePropName="checked" initialValue={true}>
          <Switch />
        </Form.Item>
      </>
    )
  }

  return (
    <>
      <Form.Item name="trigger_mode" label="触发方式" initialValue="webhook">
        <Select options={[
          { value: 'webhook', label: 'Webhook触发' },
          { value: 'cron', label: '定时触发' },
          { value: 'manual', label: '手动触发' },
        ]} />
      </Form.Item>
      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.trigger_mode !== cur.trigger_mode}>
        {({ getFieldValue }) => getFieldValue('trigger_mode') === 'cron' ? (
          <>
            <Form.Item name="cron_expr" label="Cron表达式" rules={[{ required: true, message: '请输入cron表达式' }]}
              extra="格式: 分 时 日 月 周，如 0 9 * * 1-5 表示工作日每天9点">
              <Select
                mode="tags"
                maxCount={1}
                placeholder="选择预设或输入自定义表达式"
                options={[
                  { value: '*/30 * * * *', label: '每30分钟' },
                  { value: '0 * * * *', label: '每小时' },
                  { value: '0 9 * * *', label: '每天9:00' },
                  { value: '0 9 * * 1-5', label: '工作日9:00' },
                  { value: '0 0 * * 1', label: '每周一0:00' },
                ]}
              />
            </Form.Item>
            <Form.Item name="cron_input" label="执行时输入内容" extra="每次定时执行时传入的内容">
              <TextArea rows={3} placeholder="如：执行每日代码质量检查" />
            </Form.Item>
          </>
        ) : (
          <Alert
            message={getFieldValue('trigger_mode') === 'webhook' ? '创建完成后将生成Webhook URL' : '创建完成后可手动触发执行'}
            type="info"
          />
        )}
      </Form.Item>
    </>
  )
}

function renderRulesConfig(agentType: string) {
  if (agentType === 'code_review') {
    return (
      <>
        <Form.Item name="pass_score" label="通过分数阈值">
          <Slider min={0} max={100} marks={{ 0: '0', 50: '50', 70: '70', 100: '100' }} />
        </Form.Item>
        <Form.Item name="security_checks" label="安全检查项"
          initialValue={['sql_injection', 'xss', 'hardcoded_secrets', 'command_injection', 'ssrf']}>
          <Checkbox.Group options={SECURITY_CHECKS} />
        </Form.Item>
        <Form.Item name="quality_checks" label="质量检查"
          initialValue={['function_length', 'cyclomatic_complexity']}>
          <Checkbox.Group options={[
            { value: 'function_length', label: '函数过长(>80行)' },
            { value: 'cyclomatic_complexity', label: '圈复杂度过高' },
            { value: 'duplicate_code', label: '重复代码' },
            { value: 'magic_numbers', label: '魔法数字' },
          ]} />
        </Form.Item>
        <Form.Item name="standards_checks" label="规范检查"
          initialValue={['naming_convention', 'error_handling']}>
          <Checkbox.Group options={[
            { value: 'naming_convention', label: '命名规范' },
            { value: 'error_handling', label: '错误处理' },
            { value: 'todo_fixme', label: 'TODO/FIXME检测' },
          ]} />
        </Form.Item>
        <Form.Item name="linter_cmd" label="Linter命令" extra="如 flake8 --max-line-length=120">
          <Input placeholder="flake8 --max-line-length=120 --count" />
        </Form.Item>
      </>
    )
  }

  if (agentType === 'customer_service') {
    return (
      <>
        <Form.Item name="sentiment_detection" label="情绪检测" valuePropName="checked" initialValue={true}>
          <Switch />
        </Form.Item>
        <Form.Item name="escalate_rules" label="升级到人工条件" extra="每行一条规则">
          <TextArea rows={4} placeholder={"用户要求人工客服\n连续3次未解决\n涉及退款超过500元"} />
        </Form.Item>
      </>
    )
  }

  if (agentType === 'resume_screening') {
    return (
      <>
        <Form.Item name="pass_score" label="通过分数">
          <Slider min={0} max={100} marks={{ 55: '待定', 70: '推荐', 85: '强烈推荐' }} />
        </Form.Item>
        <Form.Item name="anti_bias" label="反歧视检查" valuePropName="checked">
          <Switch />
        </Form.Item>
      </>
    )
  }

  return (
    <Alert message="该类型暂无额外规则配置" description="Agent将使用默认规则执行。创建后可通过YAML编辑高级配置。" type="info" />
  )
}
