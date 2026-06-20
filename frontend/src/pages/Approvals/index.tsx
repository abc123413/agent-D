import { useEffect, useState } from 'react'
import { Card, List, Tag, Button, Space, Empty, message, Input, Modal } from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons'
import { approvalsApi } from '@/services/api'

interface ApprovalTask {
  task_id: string
  skill_name: string
  input_text: string
  created_at: number
  metadata: Record<string, unknown>
}

export default function Approvals() {
  const [tasks, setTasks] = useState<ApprovalTask[]>([])
  const [rejectId, setRejectId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState<Record<string, boolean>>({})

  const loadTasks = () => {
    approvalsApi.list().then((r) => setTasks(r.data)).catch(() => {})
  }

  useEffect(() => {
    loadTasks()
    const interval = setInterval(loadTasks, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleApprove = async (taskId: string) => {
    setLoading((p) => ({ ...p, [taskId]: true }))
    try {
      await approvalsApi.approve(taskId)
      message.success('已批准，任务执行中')
      loadTasks()
    } catch {
      message.error('操作失败')
    }
    setLoading((p) => ({ ...p, [taskId]: false }))
  }

  const handleReject = async () => {
    if (!rejectId) return
    setLoading((p) => ({ ...p, [rejectId]: true }))
    try {
      await approvalsApi.reject(rejectId, reason)
      message.success('已拒绝')
      setRejectId(null)
      setReason('')
      loadTasks()
    } catch {
      message.error('操作失败')
    }
    setLoading((p) => ({ ...p, [rejectId]: false }))
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>审批中心</h2>
        <Tag color="orange">{tasks.length} 个待审批</Tag>
      </div>

      {tasks.length === 0 ? (
        <Card>
          <Empty description="暂无待审批任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </Card>
      ) : (
        <List
          grid={{ gutter: 16, xs: 1, sm: 1, lg: 2 }}
          dataSource={tasks}
          renderItem={(task) => (
            <List.Item>
              <Card
                size="small"
                title={
                  <Space>
                    <ExclamationCircleOutlined style={{ color: '#fa8c16' }} />
                    <span>{task.skill_name}</span>
                    <Tag color="orange">待审批</Tag>
                  </Space>
                }
                extra={
                  <span style={{ fontSize: 12, color: '#999' }}>
                    <ClockCircleOutlined /> {new Date(task.created_at * 1000).toLocaleString()}
                  </span>
                }
              >
                <div style={{ marginBottom: 12 }}>
                  <strong>输入内容:</strong>
                  <div style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4, maxHeight: 100, overflow: 'auto', fontSize: 13 }}>
                    {task.input_text || '(无)'}
                  </div>
                </div>
                <Space>
                  <Button
                    type="primary"
                    icon={<CheckCircleOutlined />}
                    loading={loading[task.task_id]}
                    onClick={() => handleApprove(task.task_id)}
                  >
                    批准执行
                  </Button>
                  <Button
                    danger
                    icon={<CloseCircleOutlined />}
                    onClick={() => setRejectId(task.task_id)}
                  >
                    拒绝
                  </Button>
                </Space>
              </Card>
            </List.Item>
          )}
        />
      )}

      <Modal
        title="拒绝原因"
        open={!!rejectId}
        onCancel={() => { setRejectId(null); setReason('') }}
        onOk={handleReject}
        okText="确认拒绝"
        okButtonProps={{ danger: true }}
      >
        <Input.TextArea
          rows={3}
          placeholder="请输入拒绝原因（可选）"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Modal>
    </div>
  )
}
