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
} from 'lucide-react'
import type { RepositoryInfo, SystemStatus } from '../types'

interface NavbarProps {
  status: SystemStatus | null
  repositories: RepositoryInfo[]
  activeRepoPath: string
  onSelectRepo: (path: string) => Promise<void>
  onRunAllTests: () => void
  onQuickInvestigate: () => void
  isLoading: boolean
}

export const Navbar: React.FC<NavbarProps> = ({
  status,
  repositories,
  activeRepoPath,
  onSelectRepo,
  onRunAllTests,
  onQuickInvestigate,
  isLoading,
}) => {
  const [showRepoModal, setShowRepoModal] = useState(false)
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
              <p style={{ color: '#8b949e', fontSize: '12px', marginBottom: '12px' }}>
                Choose a repository from detected fixtures or enter an absolute local path:
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
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
                        <div style={{ fontWeight: 600, fontSize: '13px', color: '#f0f6fc' }}>
                          {repo.name}
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
    </>
  )
}
