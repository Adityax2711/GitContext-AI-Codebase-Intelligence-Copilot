import React, { useState, useEffect } from 'react'
import {
  X,
  Search,
  ExternalLink,
  Lock,
  Globe,
  Star,
  GitBranch,
  Download,
  LogOut,
  Key,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  FolderGit2,
  Sparkles,
} from 'lucide-react'
import type { GitHubRepoSummary, GitHubUser } from '../types'
import {
  fetchGitHubRepos,
  importGitHubRepo,
  loginGitHub,
  logoutGitHub,
} from '../api'

interface GitHubModalProps {
  isOpen: boolean
  onClose: () => void
  onRepoImported: (repoPath: string) => Promise<void>
  githubUser: GitHubUser | null
  onUserUpdated: (user: GitHubUser | null) => void
}

const GitHubIcon: React.FC<{ size?: number; color?: string }> = ({
  size = 18,
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

export const GitHubModal: React.FC<GitHubModalProps> = ({
  isOpen,
  onClose,
  onRepoImported,
  githubUser,
  onUserUpdated,
}) => {
  const [activeTab, setActiveTab] = useState<'import' | 'my-repos'>('import')

  // Import form state
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('')
  const [customToken, setCustomToken] = useState('')
  const [isImporting, setIsImporting] = useState(false)
  const [importStatus, setImportStatus] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  // Login form state
  const [patInput, setPatInput] = useState('')
  const [isLoggingIn, setIsLoggingIn] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)

  // User repositories state
  const [userRepos, setUserRepos] = useState<GitHubRepoSummary[]>([])
  const [repoFilter, setRepoFilter] = useState('')
  const [isLoadingRepos, setIsLoadingRepos] = useState(false)

  useEffect(() => {
    if (isOpen && githubUser) {
      loadUserRepos()
    }
  }, [isOpen, githubUser])

  const loadUserRepos = async () => {
    setIsLoadingRepos(true)
    try {
      const res = await fetchGitHubRepos()
      setUserRepos(res.repositories || [])
    } catch (e) {
      console.error('Failed to load user repositories:', e)
    } finally {
      setIsLoadingRepos(false)
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!patInput.trim()) return

    setIsLoggingIn(true)
    setLoginError(null)

    try {
      const res = await loginGitHub(patInput.trim())
      onUserUpdated(res.user)
      setPatInput('')
      await loadUserRepos()
      setActiveTab('my-repos')
    } catch (e: any) {
      setLoginError(e.message || 'GitHub authentication failed')
    } finally {
      setIsLoggingIn(false)
    }
  }

  const handleLogout = async () => {
    try {
      await logoutGitHub()
      onUserUpdated(null)
      setUserRepos([])
      setActiveTab('import')
    } catch (e) {
      console.error('Logout failed:', e)
    }
  }

  const handleImport = async (targetUrl?: string, targetBranch?: string) => {
    const urlToUse = (targetUrl || repoUrl).trim()
    if (!urlToUse) {
      setImportError('Please enter a GitHub repository URL or owner/repo identifier.')
      return
    }

    setIsImporting(true)
    setImportError(null)
    setImportStatus('Connecting to GitHub and cloning repository...')

    try {
      setImportStatus('Downloading repository files & parsing AST...')
      const res = await importGitHubRepo({
        repository_url: urlToUse,
        branch: (targetBranch || branch).trim() || undefined,
        token: customToken.trim() || undefined,
        reindex: true,
      })

      setImportStatus(
        `Indexed ${res.index?.total_files || 0} files and ${res.index?.total_chunks || 0} chunks successfully!`
      )

      await onRepoImported(res.repository_path)
      setTimeout(() => {
        setIsImporting(false)
        setImportStatus(null)
        onClose()
      }, 1200)
    } catch (e: any) {
      setIsImporting(false)
      setImportStatus(null)
      setImportError(e.message || 'Failed to import repository')
    }
  }

  const filteredRepos = userRepos.filter(
    (r) =>
      r.full_name.toLowerCase().includes(repoFilter.toLowerCase()) ||
      (r.description && r.description.toLowerCase().includes(repoFilter.toLowerCase()))
  )

  const quickSamples = [
    { label: 'Pallets / Flask', url: 'pallets/flask', desc: 'Python WSGI microframework' },
    { label: 'Tiangolo / FastAPI', url: 'tiangolo/fastapi', desc: 'High performance API framework' },
    { label: 'PSF / Requests', url: 'psf/requests', desc: 'Standard HTTP library' },
  ]

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card github-modal-card"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '640px', width: '92%' }}
      >
        {/* Modal Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'rgba(255, 255, 255, 0.08)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <GitHubIcon size={18} color="#f0f6fc" />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: '15px', color: '#f0f6fc' }}>
                GitHub Repository Workspace
              </div>
              <div style={{ fontSize: '11px', color: '#8b949e' }}>
                Import public or private repos & index into AI Copilot
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* User Status Bar */}
        <div
          style={{
            padding: '10px 16px',
            background: githubUser ? 'rgba(56, 189, 248, 0.06)' : 'rgba(255, 255, 255, 0.02)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          {githubUser ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <img
                src={githubUser.avatar_url}
                alt={githubUser.login}
                style={{ width: '24px', height: '24px', borderRadius: '50%' }}
              />
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#f0f6fc' }}>
                @{githubUser.login}
              </span>
              <span
                style={{
                  fontSize: '11px',
                  padding: '2px 8px',
                  borderRadius: '10px',
                  background: 'rgba(63, 185, 80, 0.15)',
                  color: '#3fb950',
                  border: '1px solid rgba(63, 185, 80, 0.3)',
                }}
              >
                Connected
              </span>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#8b949e' }}>
              <Key size={14} color="#eab308" />
              <span>Connect GitHub account to browse private repositories</span>
            </div>
          )}

          {githubUser ? (
            <button
              onClick={handleLogout}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#f85149',
                fontSize: '12px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <LogOut size={13} />
              <span>Sign Out</span>
            </button>
          ) : (
            <button
              onClick={() => setActiveTab('my-repos')}
              style={{
                background: 'rgba(255, 255, 255, 0.06)',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                color: '#f0f6fc',
                padding: '4px 10px',
                borderRadius: '6px',
                fontSize: '11px',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              Sign In
            </button>
          )}
        </div>

        {/* Navigation Tabs */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            padding: '0 16px',
            background: 'rgba(0, 0, 0, 0.15)',
          }}
        >
          <button
            onClick={() => setActiveTab('import')}
            style={{
              padding: '10px 14px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === 'import' ? '2px solid #6366f1' : '2px solid transparent',
              color: activeTab === 'import' ? '#f0f6fc' : '#8b949e',
              fontWeight: activeTab === 'import' ? 600 : 400,
              fontSize: '12px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Download size={14} />
            <span>Import by URL</span>
          </button>

          <button
            onClick={() => setActiveTab('my-repos')}
            style={{
              padding: '10px 14px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === 'my-repos' ? '2px solid #6366f1' : '2px solid transparent',
              color: activeTab === 'my-repos' ? '#f0f6fc' : '#8b949e',
              fontWeight: activeTab === 'my-repos' ? 600 : 400,
              fontSize: '12px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <FolderGit2 size={14} />
            <span>My Repositories {userRepos.length > 0 && `(${userRepos.length})`}</span>
          </button>
        </div>

        {/* Modal Content */}
        <div className="modal-body" style={{ padding: '16px', maxHeight: '420px', overflowY: 'auto' }}>
          {activeTab === 'import' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label
                  style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#f0f6fc', marginBottom: '6px' }}
                >
                  GitHub Repository URL or Identifier
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type="text"
                    placeholder="https://github.com/owner/repo or owner/repo..."
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    disabled={isImporting}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: '6px',
                      background: '#090c10',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      color: '#f0f6fc',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', color: '#8b949e', marginBottom: '4px' }}>
                    Branch / Tag (optional)
                  </label>
                  <input
                    type="text"
                    placeholder="main, master, dev..."
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    disabled={isImporting}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      background: '#090c10',
                      border: '1px solid rgba(255, 255, 255, 0.12)',
                      color: '#f0f6fc',
                      fontSize: '12px',
                      outline: 'none',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '11px', color: '#8b949e', marginBottom: '4px' }}>
                    Private Token (optional if logged in)
                  </label>
                  <input
                    type="password"
                    placeholder="ghp_..."
                    value={customToken}
                    onChange={(e) => setCustomToken(e.target.value)}
                    disabled={isImporting}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      background: '#090c10',
                      border: '1px solid rgba(255, 255, 255, 0.12)',
                      color: '#f0f6fc',
                      fontSize: '12px',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              {/* Status / Feedback */}
              {isImporting && (
                <div
                  style={{
                    padding: '10px 14px',
                    borderRadius: '6px',
                    background: 'rgba(99, 102, 241, 0.12)',
                    border: '1px solid rgba(99, 102, 241, 0.3)',
                    color: '#818cf8',
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                  }}
                >
                  <RefreshCw size={14} className="spin" />
                  <span>{importStatus || 'Importing repository...'}</span>
                </div>
              )}

              {importError && (
                <div
                  style={{
                    padding: '10px 14px',
                    borderRadius: '6px',
                    background: 'rgba(248, 81, 73, 0.12)',
                    border: '1px solid rgba(248, 81, 73, 0.3)',
                    color: '#f85149',
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <AlertCircle size={15} />
                  <span>{importError}</span>
                </div>
              )}

              {/* Quick Presets */}
              <div style={{ marginTop: '4px' }}>
                <span style={{ fontSize: '11px', color: '#8b949e', display: 'block', marginBottom: '6px' }}>
                  Or try a sample open-source repository:
                </span>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {quickSamples.map((sample) => (
                    <button
                      key={sample.url}
                      onClick={() => setRepoUrl(sample.url)}
                      type="button"
                      style={{
                        padding: '6px 10px',
                        borderRadius: '6px',
                        background: 'rgba(255, 255, 255, 0.04)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        color: '#c9d1d9',
                        fontSize: '11px',
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{sample.label}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => handleImport()}
                  disabled={isImporting || !repoUrl.trim()}
                  style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                >
                  {isImporting ? <RefreshCw size={14} className="spin" /> : <Sparkles size={14} />}
                  <span>Import & Index with AI</span>
                </button>
              </div>
            </div>
          )}

          {activeTab === 'my-repos' && (
            <div>
              {!githubUser ? (
                /* Login Card */
                <div
                  style={{
                    padding: '18px',
                    borderRadius: '8px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                    <Key size={18} color="#eab308" />
                    <span style={{ fontWeight: 600, fontSize: '14px', color: '#f0f6fc' }}>
                      Sign in with GitHub Personal Access Token
                    </span>
                  </div>

                  <p style={{ color: '#8b949e', fontSize: '12px', lineHeight: 1.5, marginBottom: '14px' }}>
                    Generate a token in your GitHub Settings with <code>repo</code> and <code>read:user</code> scopes to browse and import your repositories directly.
                  </p>

                  <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <input
                      type="password"
                      placeholder="Paste token: ghp_xxxxxxxxxxxxxxxxxxxx"
                      value={patInput}
                      onChange={(e) => setPatInput(e.target.value)}
                      disabled={isLoggingIn}
                      style={{
                        padding: '10px 12px',
                        borderRadius: '6px',
                        background: '#090c10',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        color: '#f0f6fc',
                        fontSize: '13px',
                        outline: 'none',
                      }}
                    />

                    {loginError && (
                      <div
                        style={{
                          padding: '8px 12px',
                          borderRadius: '6px',
                          background: 'rgba(248, 81, 73, 0.15)',
                          color: '#f85149',
                          fontSize: '12px',
                        }}
                      >
                        {loginError}
                      </div>
                    )}

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <a
                        href="https://github.com/settings/tokens/new?scopes=repo,read:user&description=GitContext+AI+Copilot"
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          fontSize: '11px',
                          color: '#58a6ff',
                          textDecoration: 'none',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <span>Generate Token on GitHub</span>
                        <ExternalLink size={11} />
                      </a>

                      <button
                        type="submit"
                        className="btn-primary"
                        disabled={isLoggingIn || !patInput.trim()}
                        style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                      >
                        {isLoggingIn ? <RefreshCw size={13} className="spin" /> : <CheckCircle2 size={13} />}
                        <span>Connect GitHub</span>
                      </button>
                    </div>
                  </form>
                </div>
              ) : (
                /* Repositories List */
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ position: 'relative' }}>
                    <Search
                      size={14}
                      color="#8b949e"
                      style={{ position: 'absolute', left: '10px', top: '10px' }}
                    />
                    <input
                      type="text"
                      placeholder="Filter your repositories..."
                      value={repoFilter}
                      onChange={(e) => setRepoFilter(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '8px 10px 8px 32px',
                        borderRadius: '6px',
                        background: '#090c10',
                        border: '1px solid rgba(255, 255, 255, 0.12)',
                        color: '#f0f6fc',
                        fontSize: '12px',
                        outline: 'none',
                      }}
                    />
                  </div>

                  {isLoadingRepos ? (
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: '30px',
                        color: '#8b949e',
                        gap: '8px',
                      }}
                    >
                      <RefreshCw size={16} className="spin" />
                      <span>Fetching repositories from GitHub...</span>
                    </div>
                  ) : filteredRepos.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px', color: '#8b949e', fontSize: '12px' }}>
                      No matching repositories found.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {filteredRepos.map((repo) => (
                        <div
                          key={repo.full_name}
                          style={{
                            padding: '10px 12px',
                            borderRadius: '6px',
                            background: 'rgba(255, 255, 255, 0.03)',
                            border: '1px solid rgba(255, 255, 255, 0.08)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                          }}
                        >
                          <div style={{ maxWidth: '75%' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              {repo.private ? <Lock size={12} color="#eab308" /> : <Globe size={12} color="#38bdf8" />}
                              <span style={{ fontWeight: 600, fontSize: '13px', color: '#f0f6fc' }}>
                                {repo.full_name}
                              </span>
                              {repo.stars > 0 && (
                                <span
                                  style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '2px',
                                    fontSize: '11px',
                                    color: '#8b949e',
                                  }}
                                >
                                  <Star size={10} color="#eab308" />
                                  {repo.stars}
                                </span>
                              )}
                            </div>
                            {repo.description && (
                              <div
                                style={{
                                  fontSize: '11px',
                                  color: '#8b949e',
                                  marginTop: '2px',
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                }}
                              >
                                {repo.description}
                              </div>
                            )}
                            <div style={{ display: 'flex', gap: '10px', marginTop: '4px', fontSize: '10px', color: '#6e7681' }}>
                              {repo.language && <span>{repo.language}</span>}
                              <span style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                                <GitBranch size={10} />
                                {repo.default_branch}
                              </span>
                            </div>
                          </div>

                          <button
                            onClick={() => handleImport(repo.clone_url, repo.default_branch)}
                            disabled={isImporting}
                            className="btn-secondary"
                            style={{
                              padding: '5px 10px',
                              fontSize: '11px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <Download size={12} />
                            <span>Import</span>
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
