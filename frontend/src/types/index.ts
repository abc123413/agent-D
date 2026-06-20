export interface Agent {
  id: string
  name: string
  description: string
  enabled: boolean
  version: string
  requires_approval: boolean
}

export interface AgentDetail {
  name: string
  display_name: string
  version: string
  description: string
  enabled: boolean
  prompt: string
  input_schema: Record<string, unknown>[]
  output_schema: Record<string, unknown>[]
  security: Record<string, unknown>
  metadata: Record<string, unknown>
}

export interface AgentActivity {
  task_id: string
  skill_name: string
  status: string
  input_text: string
  output_text: string
  created_at: number
  completed_at: number
  error: string
  trace: TraceStep[]
  prompt_tokens: number
  completion_tokens: number
}

export interface TraceStep {
  step_type: 'llm' | 'tool'
  name: string
  input: string
  output: string
  start_time: number
  end_time: number
  tokens: { prompt_tokens?: number; completion_tokens?: number }
}

export interface TraceDetail {
  task_id: string
  skill_name: string
  status: string
  trace: TraceStep[]
  prompt_tokens: number
  completion_tokens: number
  duration: number
}

export interface DeployInfo {
  agent_name: string
  display_name: string
  type: string
  tools: string[]
  deploy_info: {
    host: string
    secret: string
    webhook_url?: string
    webhook_urls?: Record<string, string>
    supported_platforms?: string[]
    trigger_events?: string[]
    setup_guide: string
  }
}

export interface StatsOverview {
  total_executions: number
  completed: number
  failed: number
  blocked: number
  success_rate: number
  avg_duration_seconds: number
  by_agent: Record<string, number>
  total_tokens: number
  total_prompt_tokens: number
  total_completion_tokens: number
  estimated_cost: number
}

export interface DashboardStats {
  activeAgents: number
  totalSkills: number
  enabledSkills: number
  todayChats: number
  completedToday: number
  failedToday: number
  blockedToday: number
  violations: number
}

export interface Activity {
  time: string
  content: string
  color: string
  type: string
}

export interface PolicyRules {
  skill_permissions: Record<string, {
    allowed_actions: string[]
    blocked_actions: string[]
    requires_approval: boolean
  }>
  sensitive_patterns: { pattern: string; description: string; action: string }[]
  blocked_outputs: string[]
}

export interface Violation {
  rule_name: string
  level: string
  content: string
  action_taken: string
  timestamp: number
  skill_name: string
}

export interface ConfigFile {
  filename: string
  title: string
}

export interface WebhookTask {
  key: string
  status: string
  event: Record<string, unknown>
  result?: Record<string, unknown>
  error?: string
}

export interface AgentCreateForm {
  name: string
  display_name: string
  agent_type: string
  description: string
  version: string
  tools: string[]
  webhook_config: Record<string, unknown>
  rules_config: Record<string, unknown>
}
