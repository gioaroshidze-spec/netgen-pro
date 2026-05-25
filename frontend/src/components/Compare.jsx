import { useState } from 'react';

export default function Compare({ archiveFiles }) {
  const [diffHtml, setDiffHtml] = useState('');
  const [isComparing, setIsComparing] = useState(false);

  // Left Side (File 1)
  const [comp1Mode, setComp1Mode] = useState('archive');
  const [comp1Os, setComp1Os] = useState('');
  const [comp1Dev, setComp1Dev] = useState('');
  const [comp1Host, setComp1Host] = useState('');
  const [comp1File, setComp1File] = useState('');
  const [comp1Upload, setComp1Upload] = useState(null);

  // Right Side (File 2)
  const [comp2Mode, setComp2Mode] = useState('archive');
  const [comp2Os, setComp2Os] = useState('');
  const [comp2Dev, setComp2Dev] = useState('');
  const [comp2Host, setComp2Host] = useState('');
  const [comp2File, setComp2File] = useState('');
  const [comp2Upload, setComp2Upload] = useState(null);

  const handleCompare = () => {
    if (comp1Mode === 'archive' && !comp1File) return alert("Please select File 1 from the archive.");
    if (comp1Mode === 'upload' && !comp1Upload) return alert("Please upload File 1.");
    if (comp2Mode === 'archive' && !comp2File) return alert("Please select File 2 from the archive.");
    if (comp2Mode === 'upload' && !comp2Upload) return alert("Please upload File 2.");

    setIsComparing(true);
    setDiffHtml('');
    
    const formData = new FormData();
    if (comp1Mode === 'archive') formData.append('archive_file1', comp1File);
    if (comp1Mode === 'upload') formData.append('upload_file1', comp1Upload);
    if (comp2Mode === 'archive') formData.append('archive_file2', comp2File);
    if (comp2Mode === 'upload') formData.append('upload_file2', comp2Upload);

    fetch('http://127.0.0.1:8000/compare/', {
      method: 'POST',
      headers: { 
        'Authorization': `Bearer ${localStorage.getItem('token')}` // <-- TOKEN INJECTED
      },
      body: formData
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Comparison failed"); }
      return res.json();
    })
    .then(data => {
      setDiffHtml(data.html);
      setIsComparing(false);
    })
    .catch(err => { console.error(err); alert(err.message); setIsComparing(false); });
  };

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
      <h2 style={{ marginBottom: '20px' }}>Configuration Drift & Compare</h2>
      
      <div style={{ display: 'flex', gap: '20px', alignItems: 'stretch' }}>
        {/* --- LEFT SIDE: FILE 1 --- */}
        <div style={{ flex: 1, backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333' }}>
          <h3 style={{ marginTop: 0, color: '#4caf50', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Baseline (File 1)</h3>
          
          <div style={{ display: 'flex', gap: '15px', marginBottom: '20px' }}>
            <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
              <input type="radio" checked={comp1Mode === 'archive'} onChange={() => setComp1Mode('archive')} style={{ marginRight: '8px' }}/> Select from Archive
            </label>
            <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
              <input type="radio" checked={comp1Mode === 'upload'} onChange={() => setComp1Mode('upload')} style={{ marginRight: '8px' }}/> Upload Local File
            </label>
          </div>

          {comp1Mode === 'archive' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <select value={comp1Os} onChange={e => {setComp1Os(e.target.value); setComp1Dev(''); setComp1Host(''); setComp1File('')}} style={{ padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="">-- Select OS Type --</option>
                {Object.keys(archiveFiles).map(os => <option key={os} value={os}>{os}</option>)}
              </select>
              <select value={comp1Dev} onChange={e => {setComp1Dev(e.target.value); setComp1Host(''); setComp1File('')}} disabled={!comp1Os} style={{ padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="">-- Select Device Type --</option>
                {comp1Os && archiveFiles[comp1Os] && Object.keys(archiveFiles[comp1Os]).map(dt => <option key={dt} value={dt}>{dt}</option>)}
              </select>
              <select value={comp1Host} onChange={e => {setComp1Host(e.target.value); setComp1File('')}} disabled={!comp1Dev} style={{ padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="">-- Select Hostname --</option>
                {comp1Dev && archiveFiles[comp1Os][comp1Dev] && Object.keys(archiveFiles[comp1Os][comp1Dev]).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map(h => <option key={h} value={h}>{h}</option>)}
              </select>
              <select value={comp1File} onChange={e => setComp1File(e.target.value)} disabled={!comp1Host} style={{ padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #4caf50', borderRadius: '4px' }}>
                <option value="">-- Select Backup Version --</option>
                {comp1Host && archiveFiles[comp1Os][comp1Dev][comp1Host].map(f => <option key={f} value={f}>{f.replace('.txt', '')}</option>)}
              </select>
            </div>
          ) : (
            <input type="file" onChange={e => setComp1Upload(e.target.files[0])} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', border: '1px dashed #4caf50', borderRadius: '4px', color: '#ccc' }} />
          )}
        </div>

        {/* --- MIDDLE: COMPARE BUTTON --- */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <button onClick={handleCompare} disabled={isComparing} style={{ padding: '15px 25px', backgroundColor: '#007acc', color: 'white', border: 'none', borderRadius: '50px', cursor: isComparing ? 'wait' : 'pointer', fontWeight: 'bold', fontSize: '1.1rem', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>
            {isComparing ? '⏳' : 'Compare ➔'}
          </button>
        </div>

        {/* --- RIGHT SIDE: FILE 2 --- */}
        <div style={{ flex: 1, backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333' }}>
          <h3 style={{ marginTop: 0, color: '#007acc', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Target (File 2)</h3>
          
          <div style={{ display: 'flex', gap: '15px', marginBottom: '20px' }}>
            <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
              <input type="radio" checked={comp2Mode === 'archive'} onChange={() => setComp2Mode('archive')} style={{ marginRight: '8px' }}/> Select from Archive
            </label>
            <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
              <input type="radio" checked={comp2Mode === 'upload'} onChange={() => setComp2Mode('upload')} style={{ marginRight: '8px' }}/> Upload Local File
            </label>
          </div>

          {comp2Mode === 'archive' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <select value={comp2Os} onChange={e => {setComp2Os(e.target.value); setComp2Dev(''); setComp2Host(''); setComp2File('')}} style={{ padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="">-- Select OS Type --</option>
                {Object.keys(archiveFiles).map(os => <option key={os} value={os}>{os}</option>)}
              </select>
              <select value={comp2Dev} onChange={e => {setComp2Dev(e.target.value); setComp2Host(''); setComp2File('')}} disabled={!comp2Os} style={{ padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="">-- Select Device Type --</option>
                {comp2Os && archiveFiles[comp2Os] && Object.keys(archiveFiles[comp2Os]).map(dt => <option key={dt} value={dt}>{dt}</option>)}
              </select>
              <select value={comp2Host} onChange={e => {setComp2Host(e.target.value); setComp2File('')}} disabled={!comp2Dev} style={{ padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="">-- Select Hostname --</option>
                {comp2Dev && archiveFiles[comp2Os][comp2Dev] && Object.keys(archiveFiles[comp2Os][comp2Dev]).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map(h => <option key={h} value={h}>{h}</option>)}
              </select>
              <select value={comp2File} onChange={e => setComp2File(e.target.value)} disabled={!comp2Host} style={{ padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #007acc', borderRadius: '4px' }}>
                <option value="">-- Select Backup Version --</option>
                {comp2Host && archiveFiles[comp2Os][comp2Dev][comp2Host].map(f => <option key={f} value={f}>{f.replace('.txt', '')}</option>)}
              </select>
            </div>
          ) : (
            <input type="file" onChange={e => setComp2Upload(e.target.files[0])} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', border: '1px dashed #007acc', borderRadius: '4px', color: '#ccc' }} />
          )}
        </div>
      </div>

      {/* Diff Output Window */}
      {diffHtml && (
        <div style={{ marginTop: '30px', backgroundColor: '#1e1e1e', color: '#fff', padding: '20px', borderRadius: '8px', border: '1px solid #444', overflowX: 'auto' }}
             dangerouslySetInnerHTML={{ __html: diffHtml }} 
        />
      )}
    </div>
  );
}