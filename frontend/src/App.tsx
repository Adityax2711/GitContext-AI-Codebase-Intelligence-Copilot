import React, { useState, useEffect } from 'react'
import {
  Code2,
  FileDiff,
  Bug,
} from 'lucide-react'
import type {
  AuthUser,
  BugFinding,
  FileReadResult,
  FileTreeNode,
  GitHubUser,
  PatchProposal,
  RepositoryInfo,
  SystemStatus,
  TestExecutionSummary,
} from './types'
import {
  applyPatch,
  fetchCurrentUser,
  fetchFileContent,
  fetchFileTree,
  fetchGitHubUser,
  fetchPatches,
  fetchRepositories,
  fetchStatus,
  rejectPatch,
  rollbackPatch,
  runDirectTests,
  selectRepository,
  sendChatMessage,
  setAuthToken,
  verifyPatchInIsolation,
} from './api'
import { Navbar } from './components/Navbar'
import { FileExplorer } from './components/FileExplorer'
import { CodeViewer } from './components/CodeViewer'
import { DiffViewer } from './components/DiffViewer'
import { InvestigationPanel } from './components/InvestigationPanel'
import { CopilotChat } from './components/CopilotChat'

export const App: React.FC = () => {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [repositories, setRepositories] = useState<RepositoryInfo[]>([])
  const [activeRepoPath, setActiveRepoPath] = useState<string>('')
  const [fileTree, setFileTree] = useState<FileTreeNode[]>([])
  const [githubUser, setGithubUser] = useState<GitHubUser | null>(null)
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)

  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null)
  const [fileData, setFileData] = useState<FileReadResult | null>(null)
  const [highlightRange, setHighlightRange] = useState<[number, number] | null>(null)

  const [activeTab, setActiveTab] = useState<'code' | 'diff' | 'investigation'>('code')
  const [currentPatch, setCurrentPatch] = useState<PatchProposal | null>(null)
  const [testSummary, setTestSummary] = useState<TestExecutionSummary | null>(null)
  const [bugFindings, setBugFindings] = useState<BugFinding[]>([])

  const [messages, setMessages] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isTreeLoading, setIsTreeLoading] = useState(false)
  const [isFileLoading, setIsFileLoading] = useState(false)

  // Initial load
  useEffect(() => {
    initApp()
  }, [])

  const initApp = async () => {
    // 1. Check for OAuth callback token in query string
    try {
      const urlParams = new URLSearchParams(window.location.search)
      const queryToken = urlParams.get('auth_token')
      if (queryToken) {
        setAuthToken(queryToken)
        window.history.replaceState({}, document.title, window.location.pathname)
      }
    } catch {
      // ignore
    }

    try {
      // Fetch authenticated user profile
      try {
        const me = await fetchCurrentUser()
        if (me.authenticated && me.user) {
          setCurrentUser(me.user)
          if (me.user.github?.login) {
            setGithubUser({
              login: me.user.github.login,
              id: me.user.github.id || 0,
              avatar_url: me.user.github.avatar_url || '',
              html_url: `https://github.com/${me.user.github.login}`,
              public_repos: 0,
              total_private_repos: 0,
            })
          }
        }
      } catch (e) {
        // Unauthenticated is fine
      }

      const s = await fetchStatus()
      setStatus(s)
      setActiveRepoPath(s.active_repository.path)

      const repos = await fetchRepositories()
      setRepositories(repos)

      try {
        const gh = await fetchGitHubUser()
        if (gh.authenticated && gh.user) {
          setGithubUser(gh.user)
        }
      } catch (e) {
        // Unauthenticated GitHub is fine
      }

      await loadTree()

      // Also check if any patches already exist
      const patches = await fetchPatches()
      if (patches.length > 0) {
        setCurrentPatch(patches[patches.length - 1])
      }
    } catch (e) {
      console.error('Failed to initialize GitContext app:', e)
    }
  }

  const loadTree = async () => {
    setIsTreeLoading(true)
    try {
      const tree = await fetchFileTree()
      setFileTree(tree)

      // Auto-select first source file if none selected
      if (!selectedFilePath) {
        const findFirstFile = (nodes: FileTreeNode[]): string | null => {
          for (const n of nodes) {
            if (n.type === 'file' && (n.extension === 'py' || n.extension === 'md')) {
              return n.path
            }
            if (n.children) {
              const res = findFirstFile(n.children)
              if (res) return res
            }
          }
          return null
        }
        const first = findFirstFile(tree)
        if (first) {
          loadFile(first)
        }
      }
    } catch (e) {
      console.error('Failed to load file tree:', e)
    } finally {
      setIsTreeLoading(false)
    }
  }

  const loadFile = async (filePath: string, startLine?: number, endLine?: number) => {
    setIsFileLoading(true)
    setSelectedFilePath(filePath)
    try {
      const data = await fetchFileContent(filePath)
      setFileData(data)
      if (startLine && endLine) {
        setHighlightRange([startLine, endLine])
      } else {
        setHighlightRange(null)
      }
    } catch (e) {
      console.error('Failed to load file content:', e)
    } finally {
      setIsFileLoading(false)
    }
  }

  const handleSelectRepo = async (path: string) => {
    setIsLoading(true)
    try {
      const res = await selectRepository(path)
      setActiveRepoPath(res.repository_path)
      const s = await fetchStatus()
      setStatus(s)
      setFileData(null)
      setSelectedFilePath(null)
      setCurrentPatch(null)
      setBugFindings([])
      setTestSummary(null)
      await loadTree()
    } catch (e: any) {
      alert(`Error switching repository: ${e.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleRepoImported = async (repoPath: string) => {
    await handleSelectRepo(repoPath)
    try {
      const repos = await fetchRepositories()
      setRepositories(repos)
    } catch (e) {
      // Ignore
    }
  }

  const handleNavigateCitation = async (filePath: string, startLine: number, endLine: number) => {
    setActiveTab('code')
    await loadFile(filePath, startLine, endLine)
  }

  const handleSendMessage = async (text: string) => {
    const userMsg = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
    setMessages((prev) => [...prev, userMsg])
    setIsLoading(true)

    try {
      const history = messages.map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }))
      const res = await sendChatMessage(text, history)

      const assistantMsg = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: res.final_answer,
        steps: res.steps,
        citations: res.citations,
        proposedPatch: res.proposed_patch,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
      setMessages((prev) => [...prev, assistantMsg])

      // If patch was proposed, stage it and switch or highlight
      if (res.proposed_patch) {
        setCurrentPatch(res.proposed_patch as PatchProposal)
      }

      if (res.findings && res.findings.length > 0) {
        setBugFindings(res.findings as BugFinding[])
      }

      if (res.test_results) {
        setTestSummary(res.test_results as TestExecutionSummary)
      }
    } catch (e: any) {
      const errorMsg = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: `Error executing query: ${e.message}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
    }
  }

  const handleQuickInvestigate = async () => {
    setActiveTab('investigation')
    await handleSendMessage('Investigate zero division in divide_numbers and propose a fix')
  }

  const handleRunAllTests = async () => {
    setActiveTab('investigation')
    setIsLoading(true)
    try {
      const summary = await runDirectTests()
      setTestSummary(summary)
    } catch (e: any) {
      alert(`Error running tests: ${e.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleApplyPatch = async (patchId: string) => {
    setIsLoading(true)
    try {
      const res = await applyPatch(patchId)
      if (res.patch) {
        setCurrentPatch(res.patch)
      } else if (currentPatch) {
        setCurrentPatch({ ...currentPatch, status: 'applied' })
      }
      // Reload active file to show applied changes in viewer
      if (selectedFilePath) {
        await loadFile(selectedFilePath)
      }
    } catch (e: any) {
      alert(`Failed to apply patch: ${e.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleRejectPatch = async (patchId: string) => {
    setIsLoading(true)
    try {
      await rejectPatch(patchId)
      if (currentPatch) {
        setCurrentPatch({ ...currentPatch, status: 'rejected' })
      }
    } catch (e: any) {
      alert(`Failed to reject patch: ${e.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleVerifyPatch = async (patchId: string) => {
    setIsLoading(true)
    try {
      const res = await verifyPatchInIsolation(patchId)
      if (currentPatch) {
        setCurrentPatch({
          ...currentPatch,
          test_verification: res.test_summary,
          status: res.passed ? 'verified' : currentPatch.status,
        })
      }
      setTestSummary(res.test_summary)
    } catch (e: any) {
      alert(`Failed to verify patch: ${e.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleRollbackPatch = async (patchId: string) => {
    setIsLoading(true)
    try {
      await rollbackPatch(patchId)
      if (currentPatch) {
        setCurrentPatch({ ...currentPatch, status: 'reverted' })
      }
      if (selectedFilePath) {
        await loadFile(selectedFilePath)
      }
    } catch (e: any) {
      alert(`Failed to rollback patch: ${e.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="app-container">
      <Navbar
        status={status}
        repositories={repositories}
        activeRepoPath={activeRepoPath}
        onSelectRepo={handleSelectRepo}
        onRunAllTests={handleRunAllTests}
        onQuickInvestigate={handleQuickInvestigate}
        isLoading={isLoading}
        githubUser={githubUser}
        onUserUpdated={setGithubUser}
        currentUser={currentUser}
        onCurrentUserUpdated={setCurrentUser}
        onRepoImported={handleRepoImported}
      />

      <div className="main-workspace">
        {/* Left Sidebar: File Explorer */}
        <FileExplorer
          tree={fileTree}
          selectedFilePath={selectedFilePath}
          onSelectFile={(path) => loadFile(path)}
          onRefresh={loadTree}
          isLoading={isTreeLoading}
        />

        {/* Center Panel: Code Viewer, Diff Viewer, or Investigation */}
        <main className="center-panel">
          <div className="tabs-bar">
            <button
              className={`tab-btn ${activeTab === 'code' ? 'active' : ''}`}
              onClick={() => setActiveTab('code')}
            >
              <Code2 size={14} />
              <span>Code Viewer</span>
              {selectedFilePath && (
                <span className="tab-badge">{selectedFilePath.split('/').pop()}</span>
              )}
            </button>

            <button
              className={`tab-btn ${activeTab === 'diff' ? 'active' : ''}`}
              onClick={() => setActiveTab('diff')}
            >
              <FileDiff size={14} />
              <span>Proposed Changes</span>
              {currentPatch && (
                <span
                  className="tab-badge"
                  style={{
                    color: currentPatch.status === 'verified' ? '#3fb950' : '#a855f7',
                  }}
                >
                  {currentPatch.status.toUpperCase()}
                </span>
              )}
            </button>

            <button
              className={`tab-btn ${activeTab === 'investigation' ? 'active' : ''}`}
              onClick={() => setActiveTab('investigation')}
            >
              <Bug size={14} />
              <span>Investigation & Tests</span>
              {testSummary && testSummary.failed_tests > 0 && (
                <span className="tab-badge" style={{ color: '#f85149' }}>
                  {testSummary.failed_tests} FAILING
                </span>
              )}
            </button>
          </div>

          {activeTab === 'code' && (
            <CodeViewer
              fileData={fileData}
              highlightRange={highlightRange}
              isLoading={isFileLoading}
            />
          )}

          {activeTab === 'diff' && (
            <DiffViewer
              patch={currentPatch}
              onApplyPatch={handleApplyPatch}
              onRejectPatch={handleRejectPatch}
              onVerifyPatch={handleVerifyPatch}
              onRollbackPatch={handleRollbackPatch}
              isLoading={isLoading}
            />
          )}

          {activeTab === 'investigation' && (
            <InvestigationPanel
              findings={bugFindings}
              testSummary={testSummary}
              onNavigateCitation={handleNavigateCitation}
              isLoading={isLoading}
            />
          )}
        </main>

        {/* Right Sidebar: Copilot Chat Assistant */}
        <CopilotChat
          messages={messages}
          onSendMessage={handleSendMessage}
          onNavigateCitation={handleNavigateCitation}
          onInspectPatch={() => setActiveTab('diff')}
          onClearHistory={() => setMessages([])}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}

export default App
