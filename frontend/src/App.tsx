import React from 'react'
import Upload from './components/Upload'

export default function App(){
  return (
    <div style={{fontFamily:'Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial', padding:24, background:'#f4f6f8', minHeight:'100vh'}}>
      <div style={{maxWidth:880, margin:'0 auto'}}>
        <header style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:20}}>
          <div>
            <h1 style={{margin:0}}>Engagement Survey Discussion Assistant</h1>
            <div style={{color:'#666'}}>Generate a concise management discussion deck from your survey report</div>
          </div>
          <div style={{textAlign:'right', color:'#888'}}>HR Internal Tool</div>
        </header>

        <main>
          <Upload />
        </main>

        <footer style={{marginTop:40, color:'#999', fontSize:13}}>
          <div>Prototype — do not upload real PII in this dev environment.</div>
        </footer>
      </div>
    </div>
  )
}
