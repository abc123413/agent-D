import { useState, useEffect } from 'react'
import { Card, Tabs, Button, Space, message, Tag, Table, Timeline, Descriptions, Badge, Form, Input, Select, InputNumber, Popconfirm, Empty } from 'antd'
import { SaveOutlined, ReloadOutlined, WarningOutlined, SafetyOutlined, StopOutlined, PlusOutlined, DeleteOutlined, BellOutlined } from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import { configApi, policyApi, alertsApi } from '@/services/api'
import type { PolicyRules, Violation } from '@/types'

const configFiles = [
  { key: '00_全局配置.yaml', label: '全局配置' },
  { key: '01_Harness引擎提示词.yaml', label: 'Harness引擎' },
  { key: '02_策略引擎规则.yaml', label: '策略规则' },
  { key: '03_技能注册表.yaml', label: '技能注册表' },
]

export default function Settings() {
  return (
    <Card title="系统设置">
      <Tabs items={[
        { key: 'config', label: '全局配置', children: <ConfigEditor /> },
        { key: 'policy', label: '策略引擎', children: <PolicyPanel /> },
        { key: 'alerts', label: '告警设置', children: <AlertsPanel /> },
        { key: 'env', label: '环境变量', children: <EnvPanel /> },
      ]} />
    </Card>
  )
}

function ConfigEditor() {
  const [activeFile, setActiveFile] = useState(configFiles[0].key)
  const [content, setContent] = useState('')
  const [saved, setSaved] = useState(true)

  useEffect(() => {
    loadConfig(activeFile)
  }, [activeFile])

  const loadConfig = (filename: string) => {
    configApi.get(filename).then((res) => {
      setContent(res.data.content)
      setSaved(true)
    }).catch(() => {
      setContent(`# ${filename}\n# 加载失败`)
      setSaved(true)
    })
  }

  const handleSave = () => {
    configApi.update(activeFile, content).then(() => {
      message.success('配置已保存')
      setSaved(true)
    }).catch((e) => {
      message.error(e.response?.data?.detail || '保存失败')
    })
  }

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between' }}>
        <Tabs
          activeKey={activeFile}
          onChange={setActiveFile}
          size="small"
          items={configFiles.map((f) => ({ key: f.key, label: f.label }))}
        />
        <Space>
          {!saved && <Tag color="warning">未保存</Tag>}
          <Button icon={<ReloadOutlined />} size="small" onClick={() => loadConfig(activeFile)}>重置</Button>
          <Button type="primary" icon={<SaveOutlined />} size="small" onClick={handleSave} disabled={saved}>保存</Button>
        </Space>
      </div>
      <div style={{ height: 450, border: '1px solid #d9d9d9', borderRadius: 4 }}>
        <Editor
          height="100%"
          language="yaml"
          value={content}
          onChange={(v) => { setContent(v || ''); setSaved(false) }}
          options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: 'on' }}
        />
      </div>
    </div>
  )
}

function PolicyPanel() {
  const [rules, setRules] = useState<PolicyRules | null>(null)
  const [violations, setViolations] = useState<Violation[]>([])

  const loadData = () => {
    policyApi.getRules().then((r) => setRules(r.data)).catch(() => {})
    policyApi.getViolations().then((r) => setViolations(r.data)).catch(() => {})
  }

  useEffect(() => { loadData() }, [])

  const handleReload = () => {
    policyApi.reload().then(() => {
      message.success('策略已重载')
      loadData()
    }).catch(() => message.error('重载失败'))
  }

  const permColumns = [
    { title: '技能', dataIndex: 'skill', key: 'skill' },
    {
      title: '允许', dataIndex: 'allowed', key: 'allowed',
      render: (v: string[]) => v?.map((a) => <Tag key={a} color="green">{a}</Tag>),
    },
    {
      title: '禁止', dataIndex: 'blocked', key: 'blocked',
      render: (v: string[]) => v?.map((a) => <Tag key={a} color="red">{a}</Tag>),
    },
    {
      title: '审批', dataIndex: 'requires_approval', key: 'approval',
      render: (v: boolean) => v ? <Tag color="orange">是</Tag> : <Tag>否</Tag>,
    },
  ]

  const permData = rules
    ? Object.entries(rules.skill_permissions).map(([skill, p]) => ({
        key: skill, skill, allowed: p.allowed_actions, blocked: p.blocked_actions, requires_approval: p.requires_approval,
      }))
    : []

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ fontWeight: 500 }}>权限矩阵</span>
        <Button icon={<ReloadOutlined />} size="small" onClick={handleReload}>热重载</Button>
      </div>
      <Table dataSource={permData} columns={permColumns} pagination={false} size="small" style={{ marginBottom: 24 }} />

      {rules?.sensitive_patterns && rules.sensitive_patterns.length > 0 && (
        <Card size="small" title="敏感信息规则" style={{ marginBottom: 16 }}>
          <Descriptions column={1} size="small">
            {rules.sensitive_patterns.map((p, i) => (
              <Descriptions.Item key={i} label={p.description}>
                <code>{p.pattern}</code> → <Tag color="blue">{p.action}</Tag>
              </Descriptions.Item>
            ))}
          </Descriptions>
        </Card>
      )}

      {rules?.blocked_outputs && rules.blocked_outputs.length > 0 && (
        <Card size="small" title="输出黑名单" style={{ marginBottom: 16 }}>
          <Space wrap>
            {rules.blocked_outputs.map((item, i) => (
              <Tag key={i} color="red" icon={<StopOutlined />}>{item}</Tag>
            ))}
          </Space>
        </Card>
      )}

      <Card size="small" title={<Space>违规日志 <Badge count={violations.length} /></Space>}>
        {violations.length > 0 ? (
          <Timeline
            items={violations.slice(0, 10).map((v, i) => ({
              color: 'red',
              dot: <WarningOutlined />,
              children: (
                <div key={i}>
                  <Tag>{new Date(v.timestamp * 1000).toLocaleTimeString()}</Tag>
                  <Tag color="red">{v.action_taken}</Tag>
                  <strong>{v.rule_name}</strong>
                  <p style={{ margin: '4px 0 0', color: '#666', fontSize: 12 }}>{v.content}</p>
                </div>
              ),
            }))}
          />
        ) : (
          <p style={{ color: '#999', textAlign: 'center' }}>暂无违规记录</p>
        )}
      </Card>
    </div>
  )
}

function AlertsPanel() {
  const [rules, setRules] = useState<any[]>([])
  const [history, setHistory] = useState<any[]>([])
  const [form] = Form.useForm()

  const loadData = () => {
    alertsApi.getRules().then((r) => setRules(r.data)).catch(() => {})
    alertsApi.getHistory().then((r) => setHistory(r.data)).catch(() => {})
  }

  useEffect(() => { loadData() }, [])

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      await alertsApi.createRule(values)
      message.success('规则已创建')
      form.resetFields()
      loadData()
    } catch {
      // validation error
    }
  }

  const handleDelete = async (id: string) => {
    await alertsApi.deleteRule(id)
    message.success('已删除')
    loadData()
  }

  const ruleColumns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '条件',
      key: 'condition',
      render: (_: any, r: any) => {
        const metricLabels: Record<string, string> = { success_rate: '成功率', avg_duration: '平均耗时', error_count: '失败数', total_tokens: 'Token总量' }
        const opLabels: Record<string, string> = { lt: '<', gt: '>', eq: '=' }
        return `${metricLabels[r.metric] || r.metric} ${opLabels[r.operator] || r.operator} ${r.threshold}`
      },
    },
    { title: '通道', dataIndex: 'channel', key: 'channel', render: (v: string) => <Tag>{v}</Tag> },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: any, r: any) => (
        <Popconfirm title="确认删除?" onConfirm={() => handleDelete(r.id)}>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <Card size="small" title="创建告警规则" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" size="small">
          <Form.Item name="name" rules={[{ required: true }]}>
            <Input placeholder="规则名称" style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="metric" rules={[{ required: true }]} initialValue="success_rate">
            <Select style={{ width: 120 }} options={[
              { value: 'success_rate', label: '成功率' },
              { value: 'avg_duration', label: '平均耗时' },
              { value: 'error_count', label: '失败数' },
              { value: 'total_tokens', label: 'Token总量' },
            ]} />
          </Form.Item>
          <Form.Item name="operator" rules={[{ required: true }]} initialValue="lt">
            <Select style={{ width: 70 }} options={[
              { value: 'lt', label: '<' },
              { value: 'gt', label: '>' },
              { value: 'eq', label: '=' },
            ]} />
          </Form.Item>
          <Form.Item name="threshold" rules={[{ required: true }]}>
            <InputNumber placeholder="阈值" style={{ width: 90 }} />
          </Form.Item>
          <Form.Item name="channel" initialValue="platform">
            <Select style={{ width: 100 }} options={[
              { value: 'platform', label: '平台通知' },
              { value: 'feishu', label: '飞书' },
            ]} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>添加</Button>
          </Form.Item>
        </Form>
      </Card>

      <Table dataSource={rules.map((r, i) => ({ ...r, key: i }))} columns={ruleColumns} size="small" pagination={false} style={{ marginBottom: 16 }} />

      <Card size="small" title={<Space>告警历史 <Badge count={history.length} /></Space>}>
        {history.length > 0 ? (
          <Timeline
            items={history.slice(0, 15).map((e, i) => ({
              color: 'red',
              dot: <BellOutlined />,
              children: (
                <div key={i}>
                  <Tag>{new Date(e.timestamp * 1000).toLocaleString()}</Tag>
                  <strong>{e.rule_name}</strong>
                  <p style={{ margin: '4px 0 0', color: '#666', fontSize: 12 }}>{e.message}</p>
                </div>
              ),
            }))}
          />
        ) : (
          <Empty description="暂无告警记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
    </div>
  )
}

function EnvPanel() {
  const envVars = [
    { name: 'OPENAI_API_KEY', desc: 'LLM API密钥', required: true },
    { name: 'OPENAI_API_BASE', desc: 'LLM API地址（兼容接口）', required: false },
    { name: 'MODEL_NAME', desc: '模型名称', required: false },
    { name: 'GITHUB_WEBHOOK_SECRET', desc: 'GitHub Webhook签名密钥', required: false },
    { name: 'GITHUB_TOKEN', desc: 'GitHub API Token（用于PR评论）', required: false },
    { name: 'GITLAB_TOKEN', desc: 'GitLab API Token', required: false },
    { name: 'GITLAB_WEBHOOK_SECRET', desc: 'GitLab Webhook验证', required: false },
    { name: 'ZENDESK_API_BASE', desc: 'Zendesk API地址', required: false },
    { name: 'ZENDESK_TOKEN', desc: 'Zendesk API Token', required: false },
    { name: 'JIRA_API_BASE', desc: 'Jira API地址', required: false },
    { name: 'JIRA_TOKEN', desc: 'Jira API Token', required: false },
    { name: 'FEISHU_TOKEN', desc: '飞书开放平台Token', required: false },
    { name: 'DEPLOY_HOST', desc: '平台部署地址（用于生成webhook URL）', required: false },
  ]

  return (
    <div>
      <p style={{ color: '#666', marginBottom: 16 }}>
        以下环境变量需在 <code>agent/.env</code> 文件中配置。此处不显示实际值。
      </p>
      <Table
        dataSource={envVars.map((v, i) => ({ ...v, key: i }))}
        pagination={false}
        size="small"
        columns={[
          { title: '变量名', dataIndex: 'name', key: 'name', render: (v: string) => <code>{v}</code> },
          { title: '说明', dataIndex: 'desc', key: 'desc' },
          {
            title: '必需',
            dataIndex: 'required',
            key: 'required',
            width: 80,
            render: (v: boolean) => v ? <Tag color="red">必需</Tag> : <Tag>可选</Tag>,
          },
        ]}
      />
    </div>
  )
}
