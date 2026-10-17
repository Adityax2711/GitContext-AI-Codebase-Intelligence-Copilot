export interface FileTreeNode {
  name: string
  path: string
  type: 'file' | 'directory'
  extension?: string
  size?: number
  children?: FileTreeNode[]
}

export interface FileLine {
  line_number: number
  text: string
}

export interface FileReadResult {
  file_path: string
  start_line: number
  end_line: number
  total_lines: number
  content: string
  lines: FileLine[]
}

export interface Citation {
  source_index: number
  file_path: string
  symbol_or_heading: string
  start_line: number
  end_line: number
  programming_language: string
  raw_reference: string
}

export interface BugFinding {
  bug_id: string
  title: string
  description?: string
  category?: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  severity_justification?: string
  confidence: 'high' | 'medium' | 'low'
  confidence_rationale?: string
  evidence_type?: string
  file_path: string
  start_line?: number
  end_line?: number
  line?: number
  code_excerpt?: string
  expected_behavior?: string
  observed_behavior?: string
  likely_root_cause?: string
  root_cause?: string
  reproduction_steps?: string[]
  suggested_fix_direction?: string
  verification_status?: 'suspected' | 'reproduced' | 'not_reproduced'
  status?: string
}

export interface TestFailureItem {
  test_name: string
  file_path: string
  line_number?: number
  error_type: string
  error_message: string
  suspected_source_file?: string
  suspected_source_line?: number
  suspected_source_symbol?: string
  stack_trace_snippet?: string
}

export interface TestExecutionSummary {
  executed: boolean
  framework?: string
  total_tests: number
  passed_tests: number
  failed_tests: number
  errors?: number
  timed_out?: boolean
  failures?: TestFailureItem[]
  status?: string
  raw_output?: string
}

export interface PatchProposal {
  patch_id: string
  file_path: string
  title: string
  explanation: string
  diff: string
  original_content?: string
  modified_content?: string
  status: 'pending' | 'verified' | 'applied' | 'rejected' | 'reverted'
  created_at?: number
  test_verification?: TestExecutionSummary
}

export interface AgentStep {
  step_index: number
  thought: string
  action?: string | null
  action_input?: Record<string, any> | null
  observation?: Record<string, any> | null
  timestamp?: number
}

export interface AgentRunResult {
  query: string
  final_answer: string
  steps: AgentStep[]
  citations: Citation[]
  findings?: BugFinding[]
  proposed_patch?: PatchProposal | null
  test_results?: TestExecutionSummary | null
  total_tool_calls: number
  completed: boolean
  error?: string | null
}

export interface RepositoryInfo {
  name: string
  path: string
  is_active: boolean
  category: string
}

export interface SystemStatus {
  status: string
  active_repository: {
    name: string
    path: string
    is_dir: boolean
  }
  index: {
    total_chunks: number
    repository_indexed?: string
    last_indexed_at?: string
  }
  llm: {
    provider: string
    model: string
  }
}
