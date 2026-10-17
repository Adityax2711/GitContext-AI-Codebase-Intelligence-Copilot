import React, { useState } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  File,
  Search,
  RefreshCw,
} from 'lucide-react'
import type { FileTreeNode } from '../types'

interface FileExplorerProps {
  tree: FileTreeNode[]
  selectedFilePath: string | null
  onSelectFile: (filePath: string) => void
  onRefresh: () => void
  isLoading?: boolean
}

export const FileExplorer: React.FC<FileExplorerProps> = ({
  tree,
  selectedFilePath,
  onSelectFile,
  onRefresh,
  isLoading,
}) => {
  const [filterQuery, setFilterQuery] = useState('')
  const [expandedPaths, setExpandedPaths] = useState<Record<string, boolean>>({
    '': true,
    'src': true,
    'tests': true,
  })

  const toggleExpand = (path: string) => {
    setExpandedPaths((prev) => ({
      ...prev,
      [path]: !prev[path],
    }))
  }

  const getFileIcon = (node: FileTreeNode) => {
    if (node.type === 'directory') {
      return expandedPaths[node.path] ? (
        <FolderOpen size={15} color="#6366f1" />
      ) : (
        <Folder size={15} color="#6366f1" />
      )
    }
    const ext = node.extension || ''
    if (['py', 'js', 'ts', 'tsx', 'jsx'].includes(ext)) {
      return <FileCode size={15} color="#38bdf8" />
    }
    if (['md', 'txt', 'rst'].includes(ext)) {
      return <FileText size={15} color="#10b981" />
    }
    return <File size={15} color="#8b949e" />
  }

  const filterTree = (nodes: FileTreeNode[], query: string): FileTreeNode[] => {
    if (!query) return nodes
    const lower = query.toLowerCase()

    return nodes.reduce<FileTreeNode[]>((acc, node) => {
      if (node.type === 'file') {
        if (node.name.toLowerCase().includes(lower)) {
          acc.push(node)
        }
      } else if (node.type === 'directory' && node.children) {
        const matchingChildren = filterTree(node.children, query)
        if (matchingChildren.length > 0 || node.name.toLowerCase().includes(lower)) {
          acc.push({
            ...node,
            children: matchingChildren,
          })
        }
      }
      return acc
    }, [])
  }

  const renderNodes = (nodes: FileTreeNode[], depth = 0) => {
    return nodes.map((node) => {
      const isDir = node.type === 'directory'
      const isExpanded = expandedPaths[node.path] ?? (depth < 1)
      const isSelected = selectedFilePath === node.path

      return (
        <div key={node.path} style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            className={`tree-node ${isSelected ? 'active' : ''}`}
            style={{ paddingLeft: `${depth * 14 + 8}px` }}
            onClick={() => {
              if (isDir) {
                toggleExpand(node.path)
              } else {
                onSelectFile(node.path)
              }
            }}
            title={node.path}
          >
            {isDir ? (
              isExpanded ? (
                <ChevronDown size={14} color="#8b949e" />
              ) : (
                <ChevronRight size={14} color="#8b949e" />
              )
            ) : (
              <span style={{ width: '14px' }} />
            )}
            {getFileIcon(node)}
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {node.name}
            </span>
          </div>

          {isDir && isExpanded && node.children && renderNodes(node.children, depth + 1)}
        </div>
      )
    })
  }

  const filtered = filterTree(tree, filterQuery)

  return (
    <aside className="sidebar-files">
      <div className="sidebar-header">
        <span>Files</span>
        <button
          onClick={onRefresh}
          style={{ background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer' }}
          title="Refresh file tree"
        >
          <RefreshCw size={13} className={isLoading ? 'spin' : ''} />
        </button>
      </div>

      <div className="file-search-box">
        <Search size={13} color="#8b949e" />
        <input
          type="text"
          placeholder="Filter files..."
          value={filterQuery}
          onChange={(e) => setFilterQuery(e.target.value)}
        />
      </div>

      <div className="file-tree-container">
        {filtered.length > 0 ? (
          renderNodes(filtered)
        ) : (
          <div style={{ padding: '16px', color: '#6e7681', fontSize: '12px', textAlign: 'center' }}>
            No matching files
          </div>
        )}
      </div>
    </aside>
  )
}
