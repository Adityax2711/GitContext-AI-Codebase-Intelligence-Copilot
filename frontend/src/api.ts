import type {
  AgentRunResult,
  AuthResponse,
  AuthUser,
  FileReadResult,
  FileTreeNode,
  PatchProposal,
  RepositoryInfo,
  SystemStatus,
  TestExecutionSummary,
  URLValidationResult,
} from './types'

const API_BASE = '/api'
const TOKEN_KEY = 'gitcontext_auth_token'

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

function getHeaders(customHeaders: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...customHeaders }
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function handleResponse(res: Response, fallbackMessage: string): Promise<any> {
  if (!res.ok) {
    let errorDetail = ''
    try {
      const err = await res.json()
      if (err.detail) {
        if (typeof err.detail === 'string') {
          errorDetail = err.detail
        } else if (Array.isArray(err.detail)) {
          errorDetail = err.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ')
        } else {
          errorDetail = JSON.stringify(err.detail)
        }
      } else if (err.message) {
        errorDetail = err.message
      }
    } catch {
      const text = await res.text().catch(() => '')
      if (text) errorDetail = text.slice(0, 200)
    }

    const statusText = res.statusText ? ` ${res.statusText}` : ''
    throw new Error(errorDetail || `${fallbackMessage} (${res.status}${statusText})`)
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// System & Repository Endpoints
// ---------------------------------------------------------------------------
export async function fetchStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE}/status`, { headers: getHeaders() })
  return handleResponse(res, 'Status check failed')
}

export async function fetchRepositories(): Promise<RepositoryInfo[]> {
  const res = await fetch(`${API_BASE}/repositories`, { headers: getHeaders() })
  return handleResponse(res, 'Failed to list repositories')
}

export async function selectRepository(
  repositoryPath: string,
  reindex = false
): Promise<{ repository_name: string; repository_path: string; status: string }> {
  const res = await fetch(`${API_BASE}/repository/select`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ repository_path: repositoryPath, reindex }),
  })
  return handleResponse(res, 'Failed to select repository')
}

export async function fetchFileTree(): Promise<FileTreeNode[]> {
  const res = await fetch(`${API_BASE}/repository/tree`, { headers: getHeaders() })
  return handleResponse(res, 'Failed to fetch file tree')
}

export async function fetchFileContent(
  filePath: string,
  startLine?: number,
  endLine?: number
): Promise<FileReadResult> {
  const params = new URLSearchParams({ file_path: filePath })
  if (startLine) params.append('start_line', startLine.toString())
  if (endLine) params.append('end_line', endLine.toString())

  const res = await fetch(`${API_BASE}/repository/file?${params.toString()}`, { headers: getHeaders() })
  return handleResponse(res, 'Failed to load file')
}

// ---------------------------------------------------------------------------
// Copilot & Investigation Endpoints
// ---------------------------------------------------------------------------
export async function sendChatMessage(
  message: string,
  history: Array<{ role: string; content: string }> = []
): Promise<AgentRunResult> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message, history }),
  })
  return handleResponse(res, 'Chat request failed')
}

export async function runInvestigation(
  query: string,
  runTests = true,
  targetFile?: string,
  targetSymbol?: string
): Promise<AgentRunResult> {
  const res = await fetch(`${API_BASE}/investigate`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      query,
      run_tests: runTests,
      target_file: targetFile,
      target_symbol: targetSymbol,
    }),
  })
  return handleResponse(res, 'Bug investigation failed')
}

// ---------------------------------------------------------------------------
// Patch & Test Actions
// ---------------------------------------------------------------------------
export async function applyPatch(patchId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/patch/apply`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ patch_id: patchId }),
  })
  return handleResponse(res, 'Failed to apply patch')
}

export async function rejectPatch(patchId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/patch/reject`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ patch_id: patchId }),
  })
  return handleResponse(res, 'Failed to reject patch')
}

export async function verifyPatchInIsolation(
  patchId: string,
  testPath?: string
): Promise<{ status: string; passed: boolean; test_summary: TestExecutionSummary }> {
  const res = await fetch(`${API_BASE}/patch/verify`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ patch_id: patchId, test_path: testPath }),
  })
  return handleResponse(res, 'Patch sandbox verification failed')
}

export async function rollbackPatch(filePath: string): Promise<any> {
  const res = await fetch(`${API_BASE}/patch/rollback?file_path=${encodeURIComponent(filePath)}`, {
    method: 'POST',
    headers: getHeaders(),
  })
  return handleResponse(res, 'Failed to rollback file')
}

export async function runDirectTests(testPath?: string): Promise<TestExecutionSummary> {
  const res = await fetch(`${API_BASE}/test/run`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ test_path: testPath }),
  })
  return handleResponse(res, 'Test execution failed')
}

export async function fetchPatches(): Promise<PatchProposal[]> {
  const res = await fetch(`${API_BASE}/patches`, { headers: getHeaders() })
  return handleResponse(res, 'Failed to list patches')
}

// ---------------------------------------------------------------------------
// Authentication Endpoints
// ---------------------------------------------------------------------------
export async function registerUser(data: {
  email: string
  password: string
  name?: string
}): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  const json = await handleResponse(res, 'Registration failed')
  if (json.token) setAuthToken(json.token)
  return json
}

export async function loginEmailUser(data: {
  email: string
  password: string
}): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  const json = await handleResponse(res, 'Login failed')
  if (json.token) setAuthToken(json.token)
  return json
}

export async function logoutUser(): Promise<{ status: string }> {
  try {
    const res = await fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      headers: getHeaders(),
    })
    return await handleResponse(res, 'Logout failed')
  } finally {
    setAuthToken(null)
  }
}

export async function fetchCurrentUser(): Promise<{ authenticated: boolean; user: AuthUser | null }> {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: getHeaders() })
  return handleResponse(res, 'Failed to fetch current user profile')
}

export async function startGitHubOAuth(): Promise<{
  configured: boolean
  authorization_url?: string
  state?: string
  message?: string
}> {
  const res = await fetch(`${API_BASE}/auth/github/start`, { headers: getHeaders() })
  return handleResponse(res, 'Failed to start GitHub OAuth')
}

export async function linkGitHubToken(token: string): Promise<any> {
  const res = await fetch(`${API_BASE}/auth/github/link-token`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ token }),
  })
  return handleResponse(res, 'Failed to link GitHub account')
}

export async function disconnectGitHub(): Promise<any> {
  const res = await fetch(`${API_BASE}/auth/github/disconnect`, {
    method: 'POST',
    headers: getHeaders(),
  })
  return handleResponse(res, 'Failed to disconnect GitHub account')
}

// ---------------------------------------------------------------------------
// GitHub Integration & Import Endpoints
// ---------------------------------------------------------------------------
export async function validateGitHubUrl(url: string): Promise<URLValidationResult> {
  const res = await fetch(`${API_BASE}/github/validate-url`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ url }),
  })
  return handleResponse(res, 'Failed to validate repository URL')
}

export async function fetchGitHubUser(): Promise<{ authenticated: boolean; user: any | null }> {
  const res = await fetch(`${API_BASE}/github/user`, { headers: getHeaders() })
  return handleResponse(res, 'Failed to fetch GitHub user')
}

export async function loginGitHub(token: string): Promise<{ status: string; user: any }> {
  const res = await fetch(`${API_BASE}/github/login`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ token }),
  })
  return handleResponse(res, 'GitHub token verification failed')
}

export async function logoutGitHub(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/github/logout`, {
    method: 'POST',
    headers: getHeaders(),
  })
  return handleResponse(res, 'GitHub logout failed')
}

export async function fetchGitHubRepos(limit = 50): Promise<{ user: string; repositories: any[] }> {
  const res = await fetch(`${API_BASE}/github/repos?limit=${limit}`, { headers: getHeaders() })
  return handleResponse(res, 'Failed to list GitHub repositories')
}

export async function importGitHubRepo(data: {
  repository_url: string
  branch?: string
  token?: string
  force_reclone?: boolean
  reindex?: boolean
}): Promise<any> {
  const res = await fetch(`${API_BASE}/github/import`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(data),
  })
  return handleResponse(res, 'Failed to import repository from GitHub')
}
