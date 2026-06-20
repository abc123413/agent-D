import axios from 'axios'
import type { AgentCreateForm } from '@/types'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !err.config.url?.includes('/auth/')) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export const dashboardApi = {
  getStats: () => api.get('/dashboard/stats'),
  getRecentActivity: () => api.get('/dashboard/recent-activity'),
}

export const statsApi = {
  getOverview: () => api.get('/stats/overview'),
  getTrend: (range: string) => api.get(`/stats/trend?range=${range}`),
  getTokenUsage: (range: string) => api.get(`/stats/token-usage?range=${range}`),
}

export const tasksApi = {
  list: () => api.get('/tasks'),
  getTrace: (taskId: string) => api.get(`/tasks/${taskId}/trace`),
}

export const agentsApi = {
  list: () => api.get('/skills'),
  get: (name: string) => api.get(`/skills/${name}`),
  create: (data: AgentCreateForm) => api.post('/agents/create', data),
  delete: (name: string) => api.delete(`/skills/${name}`),
  reload: (name: string) => api.post(`/skills/${name}/reload`),
  reloadAll: () => api.post('/skills/reload-all'),
  getActivity: (name: string) => api.get(`/agents/${name}/activity`),
  getDeployInfo: (name: string) => api.get(`/agents/${name}/deploy-info`),
  getTools: (name: string) => api.get(`/skills/${name}/tools`),
  test: (name: string, input_text: string) => api.post(`/agents/${name}/test`, { input_text }),
  getVersions: (name: string) => api.get(`/agents/${name}/versions`),
  getVersion: (name: string, ts: string) => api.get(`/agents/${name}/versions/${ts}`),
  rollback: (name: string, ts: string) => api.post(`/agents/${name}/versions/${ts}/rollback`),
}

export const webhookApi = {
  getTasks: () => api.get('/webhook/tasks'),
  test: () => api.post('/webhook/test'),
  testTicket: () => api.post('/webhook/ticket-test'),
}

export const configApi = {
  list: () => api.get('/config'),
  get: (filename: string) => api.get(`/config/${encodeURIComponent(filename)}`),
  update: (filename: string, content: string) =>
    api.put(`/config/${encodeURIComponent(filename)}`, { content }),
}

export const policyApi = {
  getRules: () => api.get('/policy/rules'),
  reload: () => api.post('/policy/reload'),
  getViolations: () => api.get('/policy/violations'),
}

export const approvalsApi = {
  list: () => api.get('/approvals'),
  approve: (taskId: string) => api.post(`/approvals/${taskId}/approve`),
  reject: (taskId: string, reason: string) => api.post(`/approvals/${taskId}/reject`, { reason }),
}

export const cronApi = {
  list: () => api.get('/cron'),
  create: (agent_name: string, cron_expr: string, input_text: string) =>
    api.post('/cron', { agent_name, cron_expr, input_text }),
  delete: (jobId: string) => api.delete(`/cron/${jobId}`),
  toggle: (jobId: string) => api.put(`/cron/${jobId}/toggle`),
}

export const alertsApi = {
  getRules: () => api.get('/alerts/rules'),
  createRule: (data: { name: string; metric: string; operator: string; threshold: number; channel: string; channel_config?: Record<string, unknown> }) =>
    api.post('/alerts/rules', data),
  deleteRule: (ruleId: string) => api.delete(`/alerts/rules/${ruleId}`),
  getHistory: () => api.get('/alerts/history'),
}

export const toolsApi = {
  list: () => api.get('/tools'),
}

export default api
