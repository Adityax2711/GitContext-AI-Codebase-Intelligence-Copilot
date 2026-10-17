import React, { useState } from 'react'
import {
  FolderGit2,
  Sparkles,
  Play,
  Bug,
  RefreshCw,
  Cpu,
  Layers,
  ChevronDown,
  X,
  Check,
  Download,
} from 'lucide-react'
import type { GitHubUser, RepositoryInfo, SystemStatus } from '../types'
import { GitHubModal } from './GitHubModal'

interface NavbarProps {
  status: SystemStatus | null
  repositories: RepositoryInfo[]
  activeRepoPath: string
  onSelectRepo: (path: string) => Promise<void>
  onRunAllTests: () => void
  onQuickInvestigate: () => void
  isLoading: boolean
  githubUser: GitHubUser | null
  onUserUpdated: (user: GitHubUser | null) => void
  onRepoImported: (path: string) => Promise<void>
}

const GitHubIcon: React.FC<{ size?: number; color?: string }> = ({
  size = 15,
  color = 'currentColor',
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
    <path d="M9 18c-4.51 2-5-2-7-2" />
  </svg>
)

export const Navbar: React.FC<NavbarProps> = ({
  status,
  repositories,
  activeRepoPath,
  onSelectRepo,
  onRunAllTests,
  onQuickInvestigate,
  isLoading,
  githubUser,
  onUserUpdated,
  onRepoImported,
}) => {
  const [showRepoModal, setShowRepoModal] = useState(false)
  const [showGitHubModal, setShowGitHubModal] = useState(false)
  const [customPath, setCustomPath] = useState('')

  const activeRepoName =
    status?.active_repository?.name || activeRepoPath.split(/[\\/]/).pop() || 'Repository'

  const handleCustomRepoSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!customPath.trim()) return
    await onSelectRepo(customPath.trim())
    setShowRepoModal(false)
    setCustomPath('')
  }

  return (
    <>
      <header className="navbar">
        <div className="brand-section">
          <div className="brand-logo" title="GitContext AI Codebase Intelligence Copilot">
            <Sparkles size={18} color="#38bdf8" />
            <span>GitContext</span>
            <div className="ai-pulse-dot" title="Agent online" />
          </div>

          {/* Repo Selector Button */}
          <button
            className="repo-selector-badge"
            onClick={() => setShowRepoModal(true)}
            title="Click to switch or load another repository"
          >
            <FolderGit2 size={15} color="#6366f1" />
            <span style={{ fontWeight: 600 }}>{activeRepoName}</span>
            <ChevronDown size={14} color="#8b949e" />
          </button>

          {/* Index Status */}
          {status?.index && (
            <div className="status-pill" title={`Indexed at ${status.index.last_indexed_at || 'now'}`}>
              <Layers size={13} />
              <span>{status.index.total_chunks} chunks indexed</span>
            </div>
          )}

          {/* LLM Provider */}
          {status?.llm && (
            <div
              className="status-pill"
              style={{
                background: 'rgba(56, 189, 248, 0.08)',
                borderColor: 'rgba(56, 189, 248, 0.25)',
                color: '#38bdf8',
              }}
              title={`LLM Model: ${status.llm.model}`}
            >
              <Cpu size={13} />
              <span>{status.llm.provider.toUpperCase()}</span>
            </div>
          )}
        </div>

        <div className="nav-actions">
          {/* GitHub Account / Import Button */}
          <button
            className="btn-secondary"
            onClick={() => setShowGitHubModal(true)}
            title={githubUser ? `Logged in as @${githubUser.login}` : 'Import repository from GitHub'}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              borderColor: githubUser ? 'rgba(56, 189, 248, 0.4)' : undefined,
            }}
          >
            {githubUser ? (
              <>
                <img
                  src={githubUser.avatar_url}
                  alt={githubUser.login}
                  style={{ width: '16px', height: '16px', borderRadius: '50%' }}
                />
                <span style={{ color: '#38bdf8', fontWeight: 600 }}>@{githubUser.login}</span>
              </>
            ) : (
              <>
                <GitHubIcon size={14} color="#f0f6fc" />
                <span>Import GitHub</span>
              </>
            )}
          </button>

          <button
            className="btn-secondary"
            onClick={onQuickInvestigate}
            disabled={isLoading}
            title="Investigate synthetic zero-division defect"
          >
            <Bug size={14} color="#f43f5e" />
            <span>Investigate Defect</span>
          </button>

          <button
            className="btn-primary"
            onClick={onRunAllTests}
            disabled={isLoading}
            title="Execute pytest in sanitized isolated sandbox"
          >
            {isLoading ? <RefreshCw size={14} className="spin" /> : <Play size={14} />}
            <span>Run Tests</span>
          </button>
        </div>
      </header>

      {/* Repository Selection Modal */}
      {showRepoModal && (
        <div className="modal-overlay" onClick={() => setShowRepoModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FolderGit2 size={18} color="#6366f1" />
                <span>Select or Load Repository</span>
              </div>
              <button
                style={{ background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer' }}
                onClick={() => setShowRepoModal(false)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              {/* GitHub Import Callout */}
              <div
                style={{
                  padding: '12px',
                  borderRadius: '6px',
                  background: 'rgba(99, 102, 241, 0.1)',
                  border: '1px solid rgba(99, 102, 241, 0.25)',
                  marginBottom: '14px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <GitHubIcon size={20} color="#818cf8" />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px', color: '#f0f6fc' }}>
                      Import from GitHub
                    </div>
                    <div style={{ fontSize: '11px', color: '#8b949e' }}>
                      Clone public or private GitHub repositories & index with AI
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setShowRepoModal(false)
                    setShowGitHubModal(true)
                  }}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}
                >
                  <Download size={13} />
                  <span>Open GitHub</span>
                </button>
              </div>

              <p style={{ color: '#8b949e', fontSize: '12px', marginBottom: '10px' }}>
                Or select an active, fixture, or previously imported repository:
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px', maxHeight: '220px', overflowY: 'auto' }}>
                {repositories.map((repo) => {
                  const isActive = repo.path === activeRepoPath
                  return (
                    <div
                      key={repo.path}
                      onClick={async () => {
                        await onSelectRepo(repo.path)
                        setShowRepoModal(false)
                      }}
                      style={{
                        padding: '10px 12px',
                        borderRadius: '6px',
                        background: isActive ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                        border: `1px solid ${isActive ? '#6366f1' : 'rgba(255, 255, 255, 0.08)'}`,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontWeight: 600, fontSize: '13px', color: '#f0f6fc' }}>
                            {repo.name}
                          </span>
                          {repo.category === 'github' && (
                            <span
                              style={{
                                fontSize: '10px',
                                padding: '1px 6px',
                                borderRadius: '4px',
                                background: 'rgba(56, 189, 248, 0.15)',
                                color: '#38bdf8',
                              }}
                            >
                              GitHub
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '11px', color: '#6e7681', marginTop: '2px' }}>
                          {repo.path}
                        </div>
                      </div>
                      {isActive && <Check size={16} color="#38bdf8" />}
                    </div>
                  )
                })}
              </div>

              <form onSubmit={handleCustomRepoSubmit} style={{ display: 'flex', gap: '8px' }}>
                <input
                  type="text"
                  placeholder="Enter path to repository (e.g. C:\path\to\repo)..."
                  value={customPath}
                  onChange={(e) => setCustomPath(e.target.value)}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    borderRadius: '6px',
                    background: '#090c10',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    color: '#f0f6fc',
                    fontSize: '12px',
                    outline: 'none',
                  }}
                />
                <button type="submit" className="btn-primary">
                  Open
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* GitHub Modal */}
      <GitHubModal
        isOpen={showGitHubModal}
        onClose={() => setShowGitHubModal(false)}
        onRepoImported={onRepoImported}
        githubUser={githubUser}
        onUserUpdated={onUserUpdated}
      />
    </>
  )
}
