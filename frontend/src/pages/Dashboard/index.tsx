import { useEffect, useState } from 'react'
import { Card, Col, Row, Statistic, Table, Tag, Select, Empty } from 'antd'
import {
  RobotOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  DollarOutlined,
  FireOutlined,
} from '@ant-design/icons'
import { Line, Pie, Column, Area } from '@ant-design/charts'
import { dashboardApi, statsApi } from '@/services/api'
import type { DashboardStats, StatsOverview, Activity } from '@/types'

interface TrendItem { date: string; count: number; failed: number }
interface ErrorTrendItem { date: string; rate: number }
interface ResponseDistItem { range: string; count: number }
interface TrendData {
  trend: TrendItem[]
  error_trend: ErrorTrendItem[]
  response_distribution: ResponseDistItem[]
}
interface TokenTrendItem { date: string; prompt_tokens: number; completion_tokens: number }

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [overview, setOverview] = useState<StatsOverview | null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [trendData, setTrendData] = useState<TrendData | null>(null)
  const [tokenTrend, setTokenTrend] = useState<TokenTrendItem[]>([])
  const [timeRange, setTimeRange] = useState('7d')

  const fetchData = () => {
    dashboardApi.getStats().then((r) => setStats(r.data)).catch(() => {})
    statsApi.getOverview().then((r) => setOverview(r.data)).catch(() => {})
    dashboardApi.getRecentActivity().then((r) => setActivities(r.data)).catch(() => {})
  }

  const fetchTrend = () => {
    statsApi.getTrend(timeRange).then((r) => setTrendData(r.data)).catch(() => {})
    statsApi.getTokenUsage(timeRange).then((r) => setTokenTrend(r.data.token_trend || [])).catch(() => {})
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    fetchTrend()
  }, [timeRange])

  const pieData = overview && Object.keys(overview.by_agent).length > 0
    ? Object.entries(overview.by_agent).map(([name, value]) => ({ name, value }))
    : []

  const tokenAreaData = tokenTrend.flatMap((item) => [
    { date: item.date, type: 'Prompt', tokens: item.prompt_tokens },
    { date: item.date, type: 'Completion', tokens: item.completion_tokens },
  ])

  const columns = [
    { title: '时间', dataIndex: 'time', key: 'time', width: 100 },
    { title: 'Agent', dataIndex: 'content', key: 'content', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => {
        const map: Record<string, { color: string; text: string }> = {
          task: { color: 'green', text: '完成' },
          running: { color: 'blue', text: '运行中' },
          error: { color: 'red', text: '失败' },
          block: { color: 'orange', text: '拦截' },
          violation: { color: 'red', text: '违规' },
        }
        const item = map[type] || { color: 'default', text: type }
        return <Tag color={item.color}>{item.text}</Tag>
      },
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>监控总览</h2>
        <Select value={timeRange} onChange={setTimeRange} style={{ width: 140 }}>
          <Select.Option value="24h">最近24小时</Select.Option>
          <Select.Option value="7d">最近7天</Select.Option>
          <Select.Option value="30d">最近30天</Select.Option>
        </Select>
      </div>

      <Row gutter={[12, 12]}>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small">
            <Statistic
              title="活跃Agent"
              value={stats?.enabledSkills ?? 0}
              suffix={`/ ${stats?.totalSkills ?? 0}`}
              prefix={<RobotOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small">
            <Statistic
              title="总执行次数"
              value={overview?.total_executions ?? 0}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small">
            <Statistic
              title="平均响应"
              value={overview?.avg_duration_seconds ?? 0}
              suffix="s"
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#fa8c16' }}
              precision={1}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small">
            <Statistic
              title="成功率"
              value={overview?.success_rate ?? 100}
              suffix="%"
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: (overview?.success_rate ?? 100) >= 90 ? '#52c41a' : '#f5222d' }}
              precision={1}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small">
            <Statistic
              title="Token消耗"
              value={overview?.total_tokens ?? 0}
              prefix={<FireOutlined />}
              valueStyle={{ color: '#13c2c2' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card size="small">
            <Statistic
              title="估算费用"
              value={overview?.estimated_cost ?? 0}
              prefix={<DollarOutlined />}
              valueStyle={{ color: '#eb2f96' }}
              precision={4}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="执行次数趋势" size="small">
            {trendData && trendData.trend.length > 0 ? (
              <Line
                data={trendData.trend}
                xField="date"
                yField="count"
                height={240}
                smooth
                point={{ size: 3 }}
                color="#1890ff"
              />
            ) : (
              <Empty description="暂无执行数据" style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="Agent执行占比" size="small">
            {pieData.length > 0 ? (
              <Pie
                data={pieData}
                angleField="value"
                colorField="name"
                height={240}
                radius={0.8}
                innerRadius={0.5}
                label={{ type: 'outer', content: '{name} {percentage}' }}
              />
            ) : (
              <Empty description="暂无数据" style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }} />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="Token用量趋势" size="small">
            {tokenAreaData.some((d) => d.tokens > 0) ? (
              <Area
                data={tokenAreaData}
                xField="date"
                yField="tokens"
                seriesField="type"
                height={200}
              />
            ) : (
              <Empty description="暂无Token数据" style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="响应时间分布" size="small">
            {trendData && trendData.response_distribution.some((d) => d.count > 0) ? (
              <Column
                data={trendData.response_distribution}
                xField="range"
                yField="count"
                height={200}
                color="#722ed1"
                label={{ position: 'top' }}
              />
            ) : (
              <Empty description="暂无数据" style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <Card title="错误率趋势" size="small">
            {trendData && trendData.error_trend.length > 0 ? (
              <Line
                data={trendData.error_trend}
                xField="date"
                yField="rate"
                height={180}
                smooth
                color="#f5222d"
                yAxis={{ label: { formatter: (v: string) => `${v}%` } }}
              />
            ) : (
              <Empty description="暂无数据" style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }} />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="最近执行记录" size="small" style={{ marginTop: 16 }}>
        <Table
          dataSource={activities.map((a, i) => ({ ...a, key: i }))}
          columns={columns}
          pagination={{ pageSize: 8 }}
          size="small"
          locale={{ emptyText: '暂无执行记录。Agent触发后，活动将在此实时显示。' }}
        />
      </Card>
    </div>
  )
}
