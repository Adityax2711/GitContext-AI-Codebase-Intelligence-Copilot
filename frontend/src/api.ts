import type {
  AgentRunResult,
  FileReadResult,
  FileTreeNode,
  PatchProposal,
  RepositoryInfo,
  SystemStatus,
  TestExecutionSummary,
} from './types'

const API_BASE = '/api'

export async function fetchStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE}/status`)
  if (!res.ok) throw new Error(`Status check failed: ${res.statusText}`)
  return res.json()
}

export async function fetchRepositories(): Promise<RepositoryInfo[]> {
  const res = await fetch(`${API_BASE}/repositories`)
  if (!res.ok) throw new Error(`Failed to list repositories: ${res.statusText}`)
  return res.json()
}

export async function selectRepository(
  repositoryPath: string,
  reindex = false
): Promise<{ repository_name: string; repository_path: string; status: string }> {
  const res = await fetch(`${API_BASE}/repository/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repository_path: repositoryPath, reindex }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to select repository: ${res.statusText}`)
  }
  return res.json()
}

export async function fetchFileTree(): Promise<FileTreeNode[]> {
  const res = await fetch(`${API_BASE}/repository/tree`)
  if (!res.ok) throw new Error(`Failed to fetch file tree: ${res.statusText}`)
  return res.json()
}

export async function fetchFileContent(
  filePath: string,
  startLine?: number,
  endLine?: number
): Promise<FileReadResult> {
  const params = new URLSearchParams({ file_path: filePath })
  if (startLine) params.append('start_line', startLine.toString())
  if (endLine) params.append('end_line', endLine.toString())

  const res = await fetch(`${API_BASE}/repository/file?${params.toString()}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to load file: ${res.statusText}`)
  }
  return res.json()
}

export async function sendChatMessage(
  message: string,
  history: Array<{ role: 'user' | 'assistant'; content: string }>
): Promise<AgentRunResult> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Chat request failed: ${res.statusText}`)
  }
  return res.json()
}

export async function investigateBug(
  query: string,
  targetFile?: string,
  targetSymbol?: string,
  runTests = true
): Promise<any> {
  const res = await fetch(`${API_BASE}/investigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      target_file: targetFile,
      target_symbol: targetSymbol,
      run_tests: runTests,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Investigation failed: ${res.statusText}`)
  }
  return res.json()
}

export async function applyPatch(patchId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/patch/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patch_id: patchId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to apply patch: ${res.statusText}`)
  }
  return res.json()
}

export async function rejectPatch(patchId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/patch/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patch_id: patchId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to reject patch: ${res.statusText}`)
  }
  return res.json()
}

export async function verifyPatchInIsolation(patchId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/patch/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patch_id: patchId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to verify patch: ${res.statusText}`)
  }
  return res.json()
}

export async function rollbackPatch(patchId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/patch/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patch_id: patchId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to rollback patch: ${res.statusText}`)
  }
  return res.json()
}

export async function fetchPatches(): Promise<PatchProposal[]> {
  const res = await fetch(`${API_BASE}/patches`)
  if (!res.ok) throw new Error(`Failed to list patches: ${res.statusText}`)
  return res.json()
}

export async function runDirectTests(testPath?: string): Promise<TestExecutionSummary> {
  const res = await fetch(`${API_BASE}/test/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ test_path: testPath }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to execute tests: ${res.statusText}`)
  }
  return res.json()
}
