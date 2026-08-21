import React, {useEffect, useState} from 'react'

export default function App(){
  const [status, setStatus] = useState<string>('loading')

  useEffect(()=>{
    fetch('/api/health')
      .then(r=>r.json())
      .then(data=>setStatus(data.status))
      .catch(()=>setStatus('unreachable'))
  },[])

  return (
    <div style={{fontFamily:'system-ui, sans-serif', padding:20}}>
      <h1>PPT Produce — Frontend</h1>
      <p>Backend status: <strong>{status}</strong></p>
      <p>This is a minimal skeleton. Implement upload / review / export flows next.</p>
    </div>
  )
}
