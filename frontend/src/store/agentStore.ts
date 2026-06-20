import { create } from 'zustand'
import type { Agent } from '@/types'

interface AgentState {
  agents: Agent[]
  loading: boolean
  setAgents: (agents: Agent[]) => void
  setLoading: (loading: boolean) => void
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  loading: false,
  setAgents: (agents) => set({ agents }),
  setLoading: (loading) => set({ loading }),
}))
