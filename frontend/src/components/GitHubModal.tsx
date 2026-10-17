import React, { useState, useEffect } from 'react'
import {
  X,
  Search,
  Lock,
  Globe,
  Download,
  LogOut,
  Key,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  FolderGit2,
  Sparkles,
  User,
  Mail,
  ShieldCheck,
  Unlink,
} from 'lucide-react'
import type { AuthUser, GitHubRepoSummary, GitHubUser, URLValidationResult } from '../types'
import {
  disconnectGitHub,
  fetchGitHubRepos,
  importGitHubRepo,
  linkGitHubToken,
  loginEmailUser,
  loginGitHub,
  logoutGitHub,
  logoutUser,
  registerUser,
  startGitHubOAuth,
  validateGitHubUrl,
} from '../api'

interface GitHubModalProps {
  isOpen: boolean
  onClose: () => void
  onRepoImported: (repoPath: string) => Promise<void>
  githubUser: GitHubUser | null
  onUserUpdated: (user: GitHubUser | null) => void
  currentUser?: AuthUser | null
  onCurrentUserUpdated?: (user: AuthUser | null) => void
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
  currentUser,
  onCurrentUserUpdated,
}) => {
  const [activeTab, setActiveTab] = useState<'import' | 'my-repos' | 'auth'>('import')

  // Import form state
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('')
  const [customToken, setCustomToken] = useState('')
  const [isImporting, setIsImporting] = useState(false)
  const [importStatus, setImportStatus] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [urlValidation, setUrlValidation] = useState<URLValidationResult | null>(null)

  // Auth form state
  const [authMode, setAuthMode] = useState<'signin' | 'register'>('signin')
  const [emailInput, setEmailInput] = useState('')
  const [passwordInput, setPasswordInput] = useState('')
  const [nameInput, setNameInput] = useState('')
  const [isAuthLoading, setIsAuthLoading] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [authSuccess, setAuthSuccess] = useState<string | null>(null)

  // PAT Token connection state
  const [patInput, setPatInput] = useState('')
  const [isConnectingPat, setIsConnectingPat] = useState(false)
  const [patError, setPatError] = useState<string | null>(null)

  // User repositories state
  const [userRepos, setUserRepos] = useState<GitHubRepoSummary[]>([])
  const [repoFilter, setRepoFilter] = useState('')
  const [isLoadingRepos, setIsLoadingRepos] = useState(false)

  useEffect(() => {
    if (isOpen && (githubUser || currentUser?.github?.connected)) {
      loadUserRepos()
    }
  }, [isOpen, githubUser, currentUser])

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

  // Pre-validate repository URL as user types or pastes
  const handleUrlBlur = async () => {
    const trimmed = repoUrl.trim()
    if (!trimmed) {
      setUrlValidation(null)
      return
    }

    try {
      const res = await validateGitHubUrl(trimmed)
      setUrlValidation(res)
      if (!res.valid && res.error) {
        setImportError(res.error)
      } else {
        setImportError(null)
      }
    } catch {
      // Ignore background validation errors
    }
  }

  const handleImport = async (targetUrl?: string, targetBranch?: string) => {
    const urlToUse = (targetUrl || repoUrl).trim()
    if (!urlToUse) {
      setImportError('Please enter a GitHub repository URL or owner/repository identifier.')
      return
    }

    setIsImporting(true)
    setImportError(null)
    setImportStatus('Validating repository identifier...')

    // 1. Client-side / API URL pre-validation
    try {
      const check = await validateGitHubUrl(urlToUse)
      if (!check.valid) {
        setIsImporting(false)
        setImportStatus(null)
        setImportError(check.error || 'Invalid GitHub repository URL format.')
        return
      }
    } catch {
      // proceed to import attempt
    }

    // 2. Import and index
    try {
      setImportStatus('Connecting to GitHub & cloning repository files...')
      const res = await importGitHubRepo({
        repository_url: urlToUse,
        branch: (targetBranch || branch).trim() || undefined,
        token: customToken.trim() || undefined,
        reindex: true,
      })

      setImportStatus(
        `Indexed ${res.index?.total_files || 0} files and ${res.index?.total_chunks || 0} AST chunks successfully!`
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
      setImportError(e.message || 'Failed to import repository from GitHub.')
    }
  }

  // Email authentication handler
  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!emailInput.trim() || !passwordInput.trim()) return

    setIsAuthLoading(true)
    setAuthError(null)
    setAuthSuccess(null)

    try {
      if (authMode === 'register') {
        const res = await registerUser({
          email: emailInput.trim(),
          password: passwordInput,
          name: nameInput.trim() || undefined,
        })
        if (onCurrentUserUpdated) onCurrentUserUpdated(res.user)
        setAuthSuccess('Account created successfully!')
      } else {
        const res = await loginEmailUser({
          email: emailInput.trim(),
          password: passwordInput,
        })
        if (onCurrentUserUpdated) onCurrentUserUpdated(res.user)
        if (res.user.github?.login) {
          onUserUpdated({
            login: res.user.github.login,
            id: res.user.github.id || 0,
            avatar_url: res.user.github.avatar_url || '',
            html_url: `https://github.com/${res.user.github.login}`,
            public_repos: 0,
            total_private_repos: 0,
          })
        }
        setAuthSuccess('Signed in successfully!')
      }

      setEmailInput('')
      setPasswordInput('')
      setNameInput('')
      setTimeout(() => {
        setAuthSuccess(null)
        setActiveTab('import')
      }, 1000)
    } catch (e: any) {
      setAuthError(e.message || 'Authentication failed')
    } finally {
      setIsAuthLoading(false)
    }
  }

  // GitHub OAuth redirect handler
  const handleGitHubOAuth = async () => {
    setIsAuthLoading(true)
    setAuthError(null)
    try {
      const res = await startGitHubOAuth()
      if (res.configured && res.authorization_url) {
        window.location.href = res.authorization_url
      } else {
        setAuthError(
          res.message ||
            'GitHub OAuth is not configured on this server. Please enter a Personal Access Token below.'
        )
      }
    } catch (e: any) {
      setAuthError(e.message || 'Failed to initiate GitHub OAuth')
    } finally {
      setIsAuthLoading(false)
    }
  }

  // Personal Access Token link handler
  const handleConnectPat = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!patInput.trim()) return

    setIsConnectingPat(true)
    setPatError(null)

    try {
      const res = await linkGitHubToken(patInput.trim())
      if (res.user && onCurrentUserUpdated) {
        onCurrentUserUpdated(res.user)
      }
      const ghUser = await loginGitHub(patInput.trim())
      onUserUpdated(ghUser.user)
      setPatInput('')
      await loadUserRepos()
      setActiveTab('my-repos')
    } catch (e: any) {
      setPatError(e.message || 'Failed to connect GitHub token')
    } finally {
      setIsConnectingPat(false)
    }
  }

  // Disconnect GitHub handler
  const handleDisconnectGitHub = async () => {
    try {
      await disconnectGitHub()
      if (currentUser && onCurrentUserUpdated) {
        onCurrentUserUpdated({
          ...currentUser,
          github: { connected: false, login: null, avatar_url: null },
        })
      }
      onUserUpdated(null)
      setUserRepos([])
    } catch (e: any) {
      alert(e.message || 'Failed to disconnect GitHub')
    }
  }

  // Sign out handler
  const handleSignOut = async () => {
    try {
      await logoutUser()
      await logoutGitHub()
      if (onCurrentUserUpdated) onCurrentUserUpdated(null)
      onUserUpdated(null)
      setUserRepos([])
      setActiveTab('auth')
    } catch (e) {
      console.error('Sign out failed:', e)
    }
  }

  const filteredRepos = userRepos.filter(
    (r) =>
      r.full_name.toLowerCase().includes(repoFilter.toLowerCase()) ||
      (r.description && r.description.toLowerCase().includes(repoFilter.toLowerCase()))
  )

  const quickSamples = [
    { label: 'Pallets / Flask', url: 'https://github.com/pallets/flask', desc: 'Python WSGI microframework' },
    { label: 'Tiangolo / FastAPI', url: 'https://github.com/tiangolo/fastapi', desc: 'Modern async web framework' },
    { label: 'PSF / Requests', url: 'https://github.com/psf/requests', desc: 'Standard HTTP library' },
  ]

  if (!isOpen) return null

  const isGitHubConnected = Boolean(githubUser || currentUser?.github?.connected)
  const displayLogin = githubUser?.login || currentUser?.github?.login
  const displayAvatar = githubUser?.avatar_url || currentUser?.github?.avatar_url

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card github-modal-card"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '660px', width: '92%' }}
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
                Import repositories, manage authentication, and index into AI Copilot
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

        {/* User Account Banner */}
        <div
          style={{
            padding: '10px 16px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          {currentUser?.email ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
              <Mail size={14} color="#6366f1" />
              <span style={{ color: '#f0f6fc', fontWeight: 500 }}>{currentUser.email}</span>
              {isGitHubConnected && displayLogin && (
                <span
                  style={{
                    background: 'rgba(56, 189, 248, 0.12)',
                    border: '1px solid rgba(56, 189, 248, 0.25)',
                    color: '#38bdf8',
                    padding: '2px 8px',
                    borderRadius: '12px',
                    fontSize: '11px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <GitHubIcon size={11} color="#38bdf8" />
                  @{displayLogin}
                </span>
              )}
            </div>
          ) : isGitHubConnected && displayLogin ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
              {displayAvatar ? (
                <img
                  src={displayAvatar}
                  alt={displayLogin}
                  style={{ width: '20px', height: '20px', borderRadius: '50%' }}
                />
              ) : (
                <GitHubIcon size={14} color="#38bdf8" />
              )}
              <span style={{ color: '#f0f6fc', fontWeight: 600 }}>@{displayLogin}</span>
              <span
                style={{
                  background: 'rgba(35, 134, 54, 0.15)',
                  border: '1px solid rgba(35, 134, 54, 0.3)',
                  color: '#3fb950',
                  padding: '1px 6px',
                  borderRadius: '10px',
                  fontSize: '10px',
                }}
              >
                Connected
              </span>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#8b949e' }}>
              <Key size={14} color="#eab308" />
              <span>Sign in with Email or GitHub to browse private repositories</span>
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {currentUser || isGitHubConnected ? (
              <button
                onClick={handleSignOut}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#f85149',
                  fontSize: '11px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <LogOut size={12} />
                <span>Sign Out</span>
              </button>
            ) : (
              <button
                onClick={() => setActiveTab('auth')}
                style={{
                  background: 'rgba(99, 102, 241, 0.15)',
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                  color: '#818cf8',
                  padding: '4px 10px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                Sign In / Register
              </button>
            )}
          </div>
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

          <button
            onClick={() => setActiveTab('auth')}
            style={{
              padding: '10px 14px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === 'auth' ? '2px solid #6366f1' : '2px solid transparent',
              color: activeTab === 'auth' ? '#f0f6fc' : '#8b949e',
              fontWeight: activeTab === 'auth' ? 600 : 400,
              fontSize: '12px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <User size={14} />
            <span>Account & Identity</span>
          </button>
        </div>

        {/* Modal Content */}
        <div className="modal-body" style={{ padding: '16px', maxHeight: '440px', overflowY: 'auto' }}>
          {/* TAB 1: IMPORT BY URL */}
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
                    placeholder="https://github.com/owner/repository or owner/repo..."
                    value={repoUrl}
                    onChange={(e) => {
                      setRepoUrl(e.target.value)
                      if (importError) setImportError(null)
                    }}
                    onBlur={handleUrlBlur}
                    disabled={isImporting}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: '6px',
                      background: '#090c10',
                      border: importError
                        ? '1px solid #f85149'
                        : urlValidation?.valid
                        ? '1px solid #3fb950'
                        : '1px solid rgba(255, 255, 255, 0.15)',
                      color: '#f0f6fc',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  />
                </div>
                {urlValidation?.valid && (
                  <div style={{ fontSize: '11px', color: '#3fb950', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <CheckCircle2 size={12} />
                    <span>Valid repository target: {urlValidation.owner}/{urlValidation.repo}</span>
                  </div>
                )}
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
                  <span>{importStatus || 'Importing and indexing repository...'}</span>
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
                    alignItems: 'flex-start',
                    gap: '8px',
                    lineHeight: '1.4',
                  }}
                >
                  <AlertCircle size={15} style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <div style={{ fontWeight: 600 }}>Import Failed:</div>
                    <div>{importError}</div>
                  </div>
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
                      onClick={() => {
                        setRepoUrl(sample.url)
                        setImportError(null)
                      }}
                      type="button"
                      style={{
                        padding: '6px 10px',
                        borderRadius: '6px',
                        background: 'rgba(255, 255, 255, 0.04)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        color: '#f0f6fc',
                        fontSize: '11px',
                        cursor: 'pointer',
                      }}
                    >
                      {sample.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: MY REPOSITORIES */}
          {activeTab === 'my-repos' && (
            <div>
              {!isGitHubConnected ? (
                <div style={{ textAlign: 'center', padding: '30px 16px' }}>
                  <GitHubIcon size={32} color="#8b949e" />
                  <div style={{ marginTop: '12px', fontSize: '14px', fontWeight: 600, color: '#f0f6fc' }}>
                    Connect GitHub to browse repositories
                  </div>
                  <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '4px', maxWidth: '380px', margin: '6px auto 16px' }}>
                    Sign in with GitHub or provide a Personal Access Token to browse and import your public and private repositories.
                  </div>
                  <button
                    onClick={() => setActiveTab('auth')}
                    style={{
                      background: '#6366f1',
                      border: 'none',
                      color: '#ffffff',
                      padding: '8px 16px',
                      borderRadius: '6px',
                      fontSize: '12px',
                      cursor: 'pointer',
                      fontWeight: 600,
                    }}
                  >
                    Go to Authentication
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ position: 'relative' }}>
                    <Search
                      size={14}
                      color="#8b949e"
                      style={{ position: 'absolute', left: '10px', top: '10px' }}
                    />
                    <input
                      type="text"
                      placeholder="Search repositories by name..."
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
                    <div style={{ textAlign: 'center', padding: '24px', color: '#8b949e', fontSize: '12px' }}>
                      <RefreshCw size={16} className="spin" style={{ margin: '0 auto 8px' }} />
                      Loading repositories from GitHub...
                    </div>
                  ) : filteredRepos.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px', color: '#8b949e', fontSize: '12px' }}>
                      No matching repositories found.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '280px', overflowY: 'auto' }}>
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
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              {repo.private ? <Lock size={12} color="#eab308" /> : <Globe size={12} color="#8b949e" />}
                              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f0f6fc' }}>
                                {repo.full_name}
                              </span>
                            </div>
                            {repo.description && (
                              <div style={{ fontSize: '11px', color: '#8b949e', marginTop: '3px' }}>
                                {repo.description}
                              </div>
                            )}
                          </div>
                          <button
                            onClick={() => handleImport(repo.clone_url, repo.default_branch)}
                            disabled={isImporting}
                            style={{
                              padding: '5px 10px',
                              borderRadius: '5px',
                              background: 'rgba(99, 102, 241, 0.15)',
                              border: '1px solid rgba(99, 102, 241, 0.3)',
                              color: '#818cf8',
                              fontSize: '11px',
                              fontWeight: 500,
                              cursor: 'pointer',
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

          {/* TAB 3: ACCOUNT & IDENTITY */}
          {activeTab === 'auth' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* If user is already logged in with email */}
              {currentUser?.email ? (
                <div
                  style={{
                    padding: '16px',
                    borderRadius: '8px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                    <ShieldCheck size={18} color="#3fb950" />
                    <span style={{ fontSize: '14px', fontWeight: 600, color: '#f0f6fc' }}>
                      Account Profile
                    </span>
                  </div>

                  <div style={{ fontSize: '12px', color: '#8b949e', marginBottom: '6px' }}>
                    Signed in as: <strong style={{ color: '#f0f6fc' }}>{currentUser.email}</strong>
                  </div>

                  <div style={{ marginTop: '14px', borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '14px' }}>
                    <div style={{ fontSize: '12px', fontWeight: 600, color: '#f0f6fc', marginBottom: '8px' }}>
                      GitHub Identity Connection
                    </div>
                    {isGitHubConnected && displayLogin ? (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '10px 12px',
                          borderRadius: '6px',
                          background: 'rgba(56, 189, 248, 0.06)',
                          border: '1px solid rgba(56, 189, 248, 0.2)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          {displayAvatar && (
                            <img
                              src={displayAvatar}
                              alt={displayLogin}
                              style={{ width: '28px', height: '28px', borderRadius: '50%' }}
                            />
                          )}
                          <div>
                            <div style={{ fontSize: '12px', fontWeight: 600, color: '#f0f6fc' }}>
                              @{displayLogin}
                            </div>
                            <div style={{ fontSize: '10px', color: '#38bdf8' }}>Linked GitHub Account</div>
                          </div>
                        </div>

                        <button
                          onClick={handleDisconnectGitHub}
                          style={{
                            padding: '4px 10px',
                            borderRadius: '5px',
                            background: 'rgba(248, 81, 73, 0.1)',
                            border: '1px solid rgba(248, 81, 73, 0.3)',
                            color: '#f85149',
                            fontSize: '11px',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <Unlink size={12} />
                          <span>Disconnect</span>
                        </button>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div style={{ fontSize: '11px', color: '#8b949e' }}>
                          Connect your GitHub account to access private repositories and push fixes.
                        </div>
                        <button
                          onClick={handleGitHubOAuth}
                          style={{
                            padding: '8px 14px',
                            borderRadius: '6px',
                            background: 'rgba(255, 255, 255, 0.08)',
                            border: '1px solid rgba(255, 255, 255, 0.15)',
                            color: '#f0f6fc',
                            fontSize: '12px',
                            cursor: 'pointer',
                            fontWeight: 500,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '8px',
                          }}
                        >
                          <GitHubIcon size={16} color="#f0f6fc" />
                          <span>Connect with GitHub OAuth</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                /* Email Registration & Login */
                <div>
                  <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
                    <button
                      onClick={() => setAuthMode('signin')}
                      style={{
                        flex: 1,
                        padding: '8px',
                        background: authMode === 'signin' ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255, 255, 255, 0.04)',
                        border: authMode === 'signin' ? '1px solid #6366f1' : '1px solid rgba(255, 255, 255, 0.08)',
                        color: authMode === 'signin' ? '#818cf8' : '#8b949e',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Sign In
                    </button>
                    <button
                      onClick={() => setAuthMode('register')}
                      style={{
                        flex: 1,
                        padding: '8px',
                        background: authMode === 'register' ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255, 255, 255, 0.04)',
                        border: authMode === 'register' ? '1px solid #6366f1' : '1px solid rgba(255, 255, 255, 0.08)',
                        color: authMode === 'register' ? '#818cf8' : '#8b949e',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Create Account
                    </button>
                  </div>

                  <form onSubmit={handleEmailAuth} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {authMode === 'register' && (
                      <div>
                        <label style={{ display: 'block', fontSize: '11px', color: '#8b949e', marginBottom: '4px' }}>
                          Display Name
                        </label>
                        <input
                          type="text"
                          placeholder="Your Name"
                          value={nameInput}
                          onChange={(e) => setNameInput(e.target.value)}
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
                    )}

                    <div>
                      <label style={{ display: 'block', fontSize: '11px', color: '#8b949e', marginBottom: '4px' }}>
                        Email Address
                      </label>
                      <input
                        type="email"
                        placeholder="developer@example.com"
                        value={emailInput}
                        onChange={(e) => setEmailInput(e.target.value)}
                        required
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
                        Password
                      </label>
                      <input
                        type="password"
                        placeholder="••••••••"
                        value={passwordInput}
                        onChange={(e) => setPasswordInput(e.target.value)}
                        required
                        minLength={6}
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

                    {authError && (
                      <div
                        style={{
                          padding: '8px 12px',
                          borderRadius: '6px',
                          background: 'rgba(248, 81, 73, 0.12)',
                          border: '1px solid rgba(248, 81, 73, 0.3)',
                          color: '#f85149',
                          fontSize: '11px',
                        }}
                      >
                        {authError}
                      </div>
                    )}

                    {authSuccess && (
                      <div
                        style={{
                          padding: '8px 12px',
                          borderRadius: '6px',
                          background: 'rgba(35, 134, 54, 0.15)',
                          border: '1px solid rgba(35, 134, 54, 0.3)',
                          color: '#3fb950',
                          fontSize: '11px',
                        }}
                      >
                        {authSuccess}
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={isAuthLoading}
                      style={{
                        padding: '9px',
                        borderRadius: '6px',
                        background: '#6366f1',
                        border: 'none',
                        color: '#ffffff',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        marginTop: '4px',
                      }}
                    >
                      {isAuthLoading ? 'Processing...' : authMode === 'register' ? 'Create Account' : 'Sign In with Email'}
                    </button>
                  </form>

                  {/* GitHub OAuth Button */}
                  <div style={{ marginTop: '14px', borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '14px' }}>
                    <button
                      onClick={handleGitHubOAuth}
                      style={{
                        width: '100%',
                        padding: '9px',
                        borderRadius: '6px',
                        background: 'rgba(255, 255, 255, 0.08)',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        color: '#f0f6fc',
                        fontSize: '12px',
                        fontWeight: 500,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px',
                      }}
                    >
                      <GitHubIcon size={16} color="#f0f6fc" />
                      <span>Continue with GitHub</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Personal Access Token alternative */}
              <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '14px' }}>
                <div style={{ fontSize: '11px', fontWeight: 600, color: '#8b949e', marginBottom: '8px' }}>
                  Connect with Personal Access Token (for Private Repos or Local Dev)
                </div>
                <form onSubmit={handleConnectPat} style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="password"
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    value={patInput}
                    onChange={(e) => setPatInput(e.target.value)}
                    style={{
                      flex: 1,
                      padding: '7px 10px',
                      borderRadius: '6px',
                      background: '#090c10',
                      border: '1px solid rgba(255, 255, 255, 0.12)',
                      color: '#f0f6fc',
                      fontSize: '12px',
                      outline: 'none',
                    }}
                  />
                  <button
                    type="submit"
                    disabled={isConnectingPat || !patInput.trim()}
                    style={{
                      padding: '7px 14px',
                      borderRadius: '6px',
                      background: 'rgba(255, 255, 255, 0.08)',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      color: '#f0f6fc',
                      fontSize: '11px',
                      fontWeight: 500,
                      cursor: 'pointer',
                    }}
                  >
                    {isConnectingPat ? 'Verifying...' : 'Connect'}
                  </button>
                </form>
                {patError && (
                  <div style={{ fontSize: '11px', color: '#f85149', marginTop: '6px' }}>{patError}</div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '12px 16px',
            background: 'rgba(0, 0, 0, 0.25)',
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
          }}
        >
          <button
            onClick={onClose}
            disabled={isImporting}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              background: 'transparent',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              color: '#8b949e',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          {activeTab === 'import' && (
            <button
              onClick={() => handleImport()}
              disabled={isImporting || !repoUrl.trim()}
              style={{
                padding: '6px 16px',
                borderRadius: '6px',
                background: isImporting ? '#4338ca' : '#6366f1',
                border: 'none',
                color: '#ffffff',
                fontSize: '12px',
                fontWeight: 600,
                cursor: isImporting || !repoUrl.trim() ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              {isImporting ? (
                <>
                  <RefreshCw size={14} className="spin" />
                  <span>Importing...</span>
                </>
              ) : (
                <>
                  <Sparkles size={14} />
                  <span>Import & Index with AI</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
