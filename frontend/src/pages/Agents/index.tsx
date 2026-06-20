import { useEffect, useState } from 'react'
import {
  Card, List, Tag, Button, Space, Modal, Tabs, Table, Descriptions,
  message, Popconfirm, Empty, Typography, Badge, Input, Drawer, Timeline, Collapse,
} from 'antd'
import {
  RobotOutlined, DeleteOutlined, ReloadOutlined, CopyOutlined,
  PlusOutlined, EyeOutlined, RocketOutlined, SearchOutlined,
  NodeIndexOutlined, ClockCircleOutlined, CodeOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import Editor from '@monaco-editor/react'
import { agentsApi, webhookApi, tasksApi } from '@/services/api'
import { useNavigate } from 'react-router-dom'
import type { Agent, AgentActivity, DeployInfo, TraceDetail, TraceStep } from '@/types'

const { Paragraph } = Typography

export default function Agents() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const [detailVisible, setDetailVisible] = useState(false)
  const [activity, setActivity] = useState<AgentActivity[]>([])
  const [deployInfo, setDeployInfo] = useState<DeployInfo | null>(null)
  const [yamlContent, setYamlContent] = useState('')
  const [webhookTasks, setWebhookTasks] = useState<any[]>([])
  const [search, setSearch] = useState('')
  const [traceVisible, setTraceVisible] = useState(false)
  const [traceData, setTraceData] = useState<TraceDetail | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)
  const [testInput, setTestInput] = useState('')
  const [testResult, setTestResult] = useState<any>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [versions, setVersions] = useState<any[]>([])
  const [versionContent, setVersionContent] = useState('')
  const navigate = useNavigate()

  const loadAgents = () => {
    agentsApi.list().then((r) => setAgents(r.data)).catch(() => {})
    webhookApi.getTasks().then((r) => setWebhookTasks(r.data)).catch(() => {})
  }

  useEffect(() => {
    loadAgents()
    const interval = setInterval(loadAgents, 8000)
    return () => clearInterval(interval)
  }, [])

  const openDetail = async (agentName: string) => {
    setSelectedAgent(agentName)
    setDetailVisible(true)
    setTestResult(null)
    setTestInput('')
    setVersions([])
    setVersionContent('')
    try {
      const [actRes, deployRes, detailRes, versRes] = await Promise.all([
        agentsApi.getActivity(agentName),
        agentsApi.getDeployInfo(agentName),
        agentsApi.get(agentName),
        agentsApi.getVersions(agentName),
      ])
      setActivity(actRes.data)
      setDeployInfo(deployRes.data)
      setYamlContent(JSON.stringify(detailRes.data, null, 2))
      setVersions(versRes.data || [])
    } catch {
      message.error('加载详情失败')
    }
  }

  const handleDelete = async (name: string) => {
    try {
      await agentsApi.delete(name)
      message.success('已删除')
      loadAgents()
    } catch {
      message.error('删除失败')
    }
  }

  const handleReload = async (name: string) => {
    try {
      await agentsApi.reload(name)
      message.success('已重载')
      loadAgents()
    } catch {
      message.error('重载失败')
    }
  }

  const copyText = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('已复制')
  }

  const openTrace = async (taskId: string) => {
    setTraceLoading(true)
    setTraceVisible(true)
    try {
      const res = await tasksApi.getTrace(taskId)
      setTraceData(res.data)
    } catch {
      message.error('加载链路失败')
    }
    setTraceLoading(false)
  }

  const runTest = async () => {
    if (!selectedAgent || !testInput.trim()) {
      message.warning('请输入测试内容')
      return
    }
    setTestLoading(true)
    setTestResult(null)
    try {
      const res = await agentsApi.test(selectedAgent, testInput)
      setTestResult(res.data)
    } catch {
      message.error('测试执行失败')
    }
    setTestLoading(false)
  }

  const filteredAgents = agents.filter((a) =>
    !search || a.name.includes(search) || a.id.includes(search)
  )

  const activityColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'time',
      width: 160,
      render: (v: number) => v ? new Date(v * 1000).toLocaleString() : '-',
    },
    { title: '输入', dataIndex: 'input_text', key: 'input', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (s: string) => {
        const colors: Record<string, string> = {
          completed: 'green', failed: 'red', running: 'blue', blocked: 'orange',
        }
        return <Tag color={colors[s] || 'default'}>{s}</Tag>
      },
    },
    {
      title: '耗时',
      key: 'duration',
      width: 80,
      render: (_: any, r: AgentActivity) => {
        if (r.completed_at && r.created_at && r.completed_at > 0) {
          return `${(r.completed_at - r.created_at).toFixed(1)}s`
        }
        return '-'
      },
    },
    { title: '输出摘要', dataIndex: 'output_text', key: 'output', ellipsis: true, width: 200 },
    {
      title: '链路',
      key: 'trace',
      width: 80,
      render: (_: any, r: AgentActivity) => (
        r.task_id ? (
          <Button type="link" size="small" icon={<NodeIndexOutlined />} onClick={() => openTrace(r.task_id)}>
            追踪
          </Button>
        ) : '-'
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索Agent..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 240 }}
            allowClear
          />
          <Tag color="blue">{agents.length} 个Agent</Tag>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/agents/create')}>
          创建Agent
        </Button>
      </div>

      {filteredAgents.length === 0 ? (
        <Card>
          <Empty description="暂无Agent，点击右上角创建">
            <Button type="primary" onClick={() => navigate('/agents/create')}>创建第一个Agent</Button>
          </Empty>
        </Card>
      ) : (
        <List
          grid={{ gutter: 16, xs: 1, sm: 2, lg: 3 }}
          dataSource={filteredAgents}
          renderItem={(agent) => {
            const agentTasks = webhookTasks.filter((t) => t.key?.includes(agent.id))
            const lastTask = agentTasks[0]
            return (
              <List.Item>
                <Card
                  size="small"
                  title={
                    <Space>
                      <RobotOutlined style={{ color: '#1890ff' }} />
                      <span>{agent.name}</span>
                    </Space>
                  }
                  extra={
                    <Badge status={agent.enabled ? 'success' : 'default'} text={agent.enabled ? '启用' : '禁用'} />
                  }
                  actions={[
                    <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDetail(agent.id)}>
                      详情
                    </Button>,
                    <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => handleReload(agent.id)}>
                      重载
                    </Button>,
                    <Popconfirm title="确认删除?" onConfirm={() => handleDelete(agent.id)}>
                      <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                    </Popconfirm>,
                  ]}
                >
                  <p style={{ color: '#666', marginBottom: 8, fontSize: 12 }}>{agent.description}</p>
                  <Space size={4} wrap>
                    <Tag>v{agent.version}</Tag>
                    {agent.requires_approval && <Tag color="orange">需审批</Tag>}
                    {lastTask && (
                      <Tag color={lastTask.status === 'completed' ? 'green' : 'blue'}>
                        最近: {lastTask.status}
                      </Tag>
                    )}
                  </Space>
                </Card>
              </List.Item>
            )
          }}
        />
      )}

      <Modal
        title={`Agent详情: ${selectedAgent}`}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        width={900}
        footer={null}
      >
        <Tabs items={[
          {
            key: 'activity',
            label: '活动日志',
            children: (
              <Table
                dataSource={activity.map((a, i) => ({ ...a, key: i }))}
                columns={activityColumns}
                size="small"
                pagination={{ pageSize: 5 }}
                locale={{ emptyText: '暂无执行记录' }}
              />
            ),
          },
          {
            key: 'deploy',
            label: '部署信息',
            children: deployInfo ? (
              <div>
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="Agent名称">{deployInfo.display_name}</Descriptions.Item>
                  <Descriptions.Item label="类型"><Tag>{deployInfo.type}</Tag></Descriptions.Item>
                  <Descriptions.Item label="可用工具">
                    {deployInfo.tools.map((t) => <Tag key={t}>{t}</Tag>)}
                  </Descriptions.Item>
                  {deployInfo.deploy_info.webhook_url && (
                    <Descriptions.Item label="Webhook URL">
                      <Space>
                        <code>{deployInfo.deploy_info.webhook_url}</code>
                        <Button size="small" icon={<CopyOutlined />}
                          onClick={() => copyText(deployInfo.deploy_info.webhook_url!)} />
                      </Space>
                    </Descriptions.Item>
                  )}
                  {deployInfo.deploy_info.webhook_urls && (
                    <Descriptions.Item label="Webhook URLs">
                      {Object.entries(deployInfo.deploy_info.webhook_urls).map(([k, v]) => (
                        <div key={k} style={{ marginBottom: 4 }}>
                          <Tag>{k}</Tag>
                          <code>{v}</code>
                          <Button size="small" icon={<CopyOutlined />} onClick={() => copyText(v)} style={{ marginLeft: 8 }} />
                        </div>
                      ))}
                    </Descriptions.Item>
                  )}
                  {deployInfo.deploy_info.trigger_events && (
                    <Descriptions.Item label="触发事件">
                      {deployInfo.deploy_info.trigger_events.map((e) => <Tag key={e} color="blue">{e}</Tag>)}
                    </Descriptions.Item>
                  )}
                </Descriptions>
                {deployInfo.deploy_info.setup_guide && (
                  <Card size="small" title="部署指南" style={{ marginTop: 16 }}>
                    <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', margin: 0 }}>
                      {deployInfo.deploy_info.setup_guide}
                    </pre>
                  </Card>
                )}
              </div>
            ) : <Empty description="加载中..." />,
          },
          {
            key: 'config',
            label: 'YAML配置',
            children: (
              <div style={{ height: 400, border: '1px solid #d9d9d9', borderRadius: 4 }}>
                <Editor
                  height="100%"
                  language="json"
                  value={yamlContent}
                  options={{ minimap: { enabled: false }, readOnly: true, fontSize: 13 }}
                />
              </div>
            ),
          },
          {
            key: 'test',
            label: '沙盒测试',
            children: (
              <div>
                <Input.TextArea
                  rows={4}
                  placeholder="输入测试内容，如：请审核这段代码..."
                  value={testInput}
                  onChange={(e) => setTestInput(e.target.value)}
                  style={{ marginBottom: 12 }}
                />
                <Button type="primary" icon={<RocketOutlined />} loading={testLoading} onClick={runTest}>
                  运行测试
                </Button>
                {testResult && (
                  <Card size="small" style={{ marginTop: 16 }}>
                    <Descriptions size="small" column={4}>
                      <Descriptions.Item label="状态">
                        <Tag color={testResult.status === 'completed' ? 'green' : 'red'}>{testResult.status}</Tag>
                      </Descriptions.Item>
                      <Descriptions.Item label="耗时">{testResult.duration}s</Descriptions.Item>
                      <Descriptions.Item label="Prompt">{testResult.prompt_tokens}</Descriptions.Item>
                      <Descriptions.Item label="Completion">{testResult.completion_tokens}</Descriptions.Item>
                    </Descriptions>
                    {testResult.error && <p style={{ color: '#f5222d', marginTop: 8 }}>{testResult.error}</p>}
                    {testResult.output && (
                      <div style={{ marginTop: 8, background: '#f5f5f5', padding: 12, borderRadius: 4, maxHeight: 300, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 13 }}>
                        {testResult.output}
                      </div>
                    )}
                  </Card>
                )}
              </div>
            ),
          },
          {
            key: 'versions',
            label: '版本历史',
            children: (
              <div>
                {versions.length === 0 ? (
                  <Empty description="暂无历史版本" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <div style={{ display: 'flex', gap: 16 }}>
                    <div style={{ width: 200 }}>
                      <Table
                        dataSource={versions.map((v, i) => ({ ...v, key: i }))}
                        columns={[
                          {
                            title: '版本时间',
                            dataIndex: 'time',
                            key: 'time',
                            render: (t: string, r: any) => (
                              <Button type="link" size="small" onClick={async () => {
                                const res = await agentsApi.getVersion(selectedAgent!, String(r.timestamp))
                                setVersionContent(res.data.content)
                              }}>{t}</Button>
                            ),
                          },
                        ]}
                        size="small"
                        pagination={{ pageSize: 8 }}
                      />
                      <Button
                        size="small"
                        danger
                        disabled={!versionContent}
                        onClick={async () => {
                          const ts = versions.find((v) => true)?.timestamp
                          if (ts && selectedAgent) {
                            await agentsApi.rollback(selectedAgent, String(ts))
                            message.success('已回滚')
                          }
                        }}
                      >
                        回滚到选中版本
                      </Button>
                    </div>
                    <div style={{ flex: 1, border: '1px solid #d9d9d9', borderRadius: 4 }}>
                      <Editor
                        height={350}
                        language="yaml"
                        value={versionContent || '# 点击左侧版本查看内容'}
                        options={{ minimap: { enabled: false }, readOnly: true, fontSize: 13 }}
                      />
                    </div>
                  </div>
                )}
              </div>
            ),
          },
        ]} />
      </Modal>

      <Drawer
        title="执行链路追踪"
        open={traceVisible}
        onClose={() => setTraceVisible(false)}
        width={600}
      >
        {traceLoading ? (
          <Empty description="加载中..." />
        ) : traceData ? (
          <div>
            <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="任务ID">{traceData.task_id}</Descriptions.Item>
              <Descriptions.Item label="技能">{traceData.skill_name}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={traceData.status === 'completed' ? 'green' : 'red'}>{traceData.status}</Tag></Descriptions.Item>
              <Descriptions.Item label="总耗时">{traceData.duration}s</Descriptions.Item>
              <Descriptions.Item label="Prompt Tokens">{traceData.prompt_tokens}</Descriptions.Item>
              <Descriptions.Item label="Completion Tokens">{traceData.completion_tokens}</Descriptions.Item>
            </Descriptions>
            <Timeline
              items={traceData.trace.map((step, i) => ({
                color: step.step_type === 'llm' ? 'blue' : 'green',
                dot: step.step_type === 'llm' ? <ThunderboltOutlined /> : <CodeOutlined />,
                children: (
                  <Collapse size="small" items={[{
                    key: i,
                    label: (
                      <Space>
                        <Tag color={step.step_type === 'llm' ? 'blue' : 'green'}>{step.step_type.toUpperCase()}</Tag>
                        <span style={{ fontWeight: 500 }}>{step.name}</span>
                        <span style={{ color: '#999', fontSize: 12 }}>
                          <ClockCircleOutlined /> {((step.end_time - step.start_time)).toFixed(2)}s
                        </span>
                        {step.tokens?.prompt_tokens && (
                          <span style={{ color: '#999', fontSize: 12 }}>
                            {step.tokens.prompt_tokens + (step.tokens.completion_tokens || 0)} tokens
                          </span>
                        )}
                      </Space>
                    ),
                    children: (
                      <div style={{ fontSize: 12 }}>
                        {step.input && (
                          <div style={{ marginBottom: 8 }}>
                            <strong>输入:</strong>
                            <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{step.input}</pre>
                          </div>
                        )}
                        {step.output && (
                          <div>
                            <strong>输出:</strong>
                            <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{step.output}</pre>
                          </div>
                        )}
                      </div>
                    ),
                  }]} />
                ),
              }))}
            />
          </div>
        ) : (
          <Empty description="无链路数据" />
        )}
      </Drawer>
    </div>
  )
}
