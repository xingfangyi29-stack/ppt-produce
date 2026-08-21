import React, { useCallback, useState } from 'react'

function formatBytes(bytes: number) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

export default function Upload() {
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const onFile = useCallback((f: File) => {
    setMessage(null)
    setError(null)
    if (!f.name.toLowerCase().endsWith('.pptx')) {
      setFile(null)
      setError('Only .pptx files are accepted. Please select a valid PowerPoint file.')
      return
    }
    setFile(f)
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const dt = e.dataTransfer
    if (dt.files && dt.files.length) {
      onFile(dt.files[0])
    }
  }, [onFile])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const onSelectFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length) {
      onFile(e.target.files[0])
    }
  }, [onFile])

  const upload = useCallback(async () => {
    setError(null)
    setMessage(null)
    if (!file) {
      setError('No file selected. Please choose a .pptx file.')
      return
    }
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('file', file, file.name)
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: fd
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || 'Upload failed')
      }
      const data = await res.json()
      if (data.success) {
        setMessage(`Uploaded ${data.filename} (${formatBytes(data.size)})`)
        setFile(null)
      } else {
        setError('Upload failed: unexpected response from server.')
      }
    } catch (err: any) {
      setError(err.message || 'Upload failed')
    } finally {
      setLoading(false)
    }
  }, [file])

  return (
    <div className="upload-card">
      <h2>Upload Engagement Survey PPTX</h2>
      <div
        className="dropzone"
        onDrop={onDrop}
        onDragOver={onDragOver}
        role="button"
        tabIndex={0}
      >
        <p>Drag & drop your .pptx file here, or</p>
        <label className="file-label">
          <input type="file" accept=".pptx" onChange={onSelectFile} />
          <span className="choose">Browse files</span>
        </label>
      </div>

      <div className="file-info">
        {file ? (
          <>
            <div><strong>Selected file:</strong> {file.name}</div>
            <div><strong>Size:</strong> {formatBytes(file.size)}</div>
          </>
        ) : (
          <div className="muted">No file selected</div>
        )}
      </div>

      <div className="actions">
        <button className="primary" onClick={upload} disabled={!file || loading}>
          {loading ? 'Uploading...' : 'Analyse Survey'}
        </button>
      </div>

      {error && <div className="error">{error}</div>}
      {message && <div className="message">{message}</div>}

      <div className="note muted">
        Files are stored temporarily on the server for analysis and are not publicly accessible.
      </div>
    </div>
  )
}
