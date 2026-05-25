import { useState } from 'react';

const API_URL = 'http://127.0.0.1:8000/device/';

export default function Maintenance({ devices, archiveFiles, userRole }) {
  // Global Backup Destinations
  const [backupDestNVRAM, setBackupDestNVRAM] = useState(false);
  const [backupDestFlash, setBackupDestFlash] = useState(false);
  const [backupDestLocal, setBackupDestLocal] = useState(true);
  const [backupDestArchive, setBackupDestArchive] = useState(true);

  // Single Backup
  const [maintSingleDevice, setMaintSingleDevice] = useState('');
  const [maintBackupName, setMaintBackupName] = useState('');
  const [isBackingUp, setIsBackingUp] = useState(false);

  // Bulk Backup
  const [maintBackupSearch, setMaintBackupSearch] = useState('');
  const [maintBackupPrefix, setMaintBackupPrefix] = useState('');
  const [maintBackupSwitches, setMaintBackupSwitches] = useState([]);
  const [maintBackupRouters, setMaintBackupRouters] = useState([]);
  const [isBackupSwitchesOpen, setIsBackupSwitchesOpen] = useState(false);
  const [isBackupRoutersOpen, setIsBackupRoutersOpen] = useState(false);
  const [isBulkBackingUp, setIsBulkBackingUp] = useState(false);

  // Restore
  const [maintRestoreSearch, setMaintRestoreSearch] = useState('');
  const [maintRestoreSwitches, setMaintRestoreSwitches] = useState([]);
  const [maintRestoreRouters, setMaintRestoreRouters] = useState([]);
  const [isRestoreSwitchesOpen, setIsRestoreSwitchesOpen] = useState(false);
  const [isRestoreRoutersOpen, setIsRestoreRoutersOpen] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);

  const [maintRestoreMode, setMaintRestoreMode] = useState('archive');
  const [maintRestoreOs, setMaintRestoreOs] = useState('');
  const [maintRestoreHost, setMaintRestoreHost] = useState('');
  const [maintRestoreFile, setMaintRestoreFile] = useState('');
  const [maintRestoreUpload, setMaintRestoreUpload] = useState(null);

  const getTimestamp = () => {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const hh = String(now.getHours()).padStart(2, '0');
    const min = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    return `${yyyy}${mm}${dd}_${hh}${min}${ss}`;
  };

  const handleSingleBackup = () => {
    if (!maintSingleDevice) return alert("Please select a device from the dropdown first.");
    if (!backupDestNVRAM && !backupDestFlash && !backupDestLocal && !backupDestArchive) return alert("Please select at least one backup destination.");
    
    const targetDevice = devices.find(d => d.hostname === maintSingleDevice);
    if (!targetDevice) return;

    setIsBackingUp(true);
    fetch(`http://127.0.0.1:8000/backup-device/${targetDevice.id}`, { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        save_nvram: backupDestNVRAM,
        save_flash: backupDestFlash,
        download_local: backupDestLocal,
        save_archive: backupDestArchive,
        prefix: maintBackupName
      })
    })
    .then(async (res) => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Backup failed"); }
      return res.json();
    })
    .then(data => {
      if (backupDestLocal && data.config) {
        const blob = new Blob([data.config], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = data.filename; 
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
      } else if (!backupDestLocal) {
        alert(`Backup successfully saved on ${data.hostname}`);
      }
      setIsBackingUp(false);
      setMaintBackupName('');
    })
    .catch(err => { console.error(err); alert(`Failed to backup: ${err.message}`); setIsBackingUp(false); });
  };

  const handleBulkBackup = () => {
    const selectedHostnames = [...maintBackupSwitches, ...maintBackupRouters];
    if (selectedHostnames.length === 0) return alert("Please select at least one device to backup.");
    if (!backupDestNVRAM && !backupDestFlash && !backupDestLocal && !backupDestArchive) return alert("Please select at least one backup destination.");
    
    const targetIds = selectedHostnames.map(h => devices.find(d => d.hostname === h).id);
    setIsBulkBackingUp(true);
    
    fetch(`${API_URL.replace('/device/', '/bulk-backup/')}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        device_ids: targetIds,
        options: {
          save_nvram: backupDestNVRAM,
          save_flash: backupDestFlash,
          download_local: backupDestLocal,
          save_archive: backupDestArchive,
          prefix: maintBackupPrefix
        }
      })
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Bulk backup failed"); }
      if (backupDestLocal) return res.blob();
      return res.json();
    }) 
    .then(data => {
      if (backupDestLocal) {
        const url = window.URL.createObjectURL(data);
        const a = document.createElement('a');
        a.href = url;
        const prefix = maintBackupPrefix ? maintBackupPrefix : 'Bulk';
        a.download = `${prefix}_Archive_${getTimestamp()}.zip`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
      } else {
        alert("Bulk backup successfully saved on target devices.");
      }
      setIsBulkBackingUp(false);
      setMaintBackupSwitches([]);
      setMaintBackupRouters([]);
      setMaintBackupPrefix('');
    })
    .catch(err => { console.error(err); alert(`Error: ${err.message}`); setIsBulkBackingUp(false); });
  };

  const handleRestore = () => {
    if (maintRestoreMode === 'archive' && !maintRestoreFile) return alert("Please select a file from the archive.");
    if (maintRestoreMode === 'upload' && !maintRestoreUpload) return alert("Please upload a configuration file first.");
    
    const selectedHostnames = [...maintRestoreSwitches, ...maintRestoreRouters];
    if (selectedHostnames.length === 0) return alert("Please select target devices.");
    if (!window.confirm(`WARNING: This will overwrite the configuration on ${selectedHostnames.length} device(s). Proceed?`)) return;

    const targetIds = selectedHostnames.map(h => devices.find(d => d.hostname === h).id);
    setIsRestoring(true);

    const formData = new FormData();
    if (maintRestoreMode === 'upload') formData.append("file", maintRestoreUpload);
    if (maintRestoreMode === 'archive') formData.append("archive_file", maintRestoreFile);
    formData.append("device_ids", JSON.stringify(targetIds));

    fetch(`${API_URL.replace('/device/', '/restore-devices/')}`, {
      method: 'POST',
      body: formData 
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Restore failed"); }
      return res.json();
    })
    .then(data => {
      alert("Restore process completed! Check your browser console for detailed logs.");
      console.log("RESTORE LOGS:\n", data.logs);
      setIsRestoring(false);
      setMaintRestoreFile(null);
      setMaintRestoreSwitches([]);
      setMaintRestoreRouters([]);
    })
    .catch(err => { console.error(err); alert("Restore failed. Check console."); setIsRestoring(false); });
  };

  const sortTargets = (a, b) => a.hostname.localeCompare(b.hostname, undefined, { numeric: true });
  const allSwitches = devices.filter(d => d.device_type !== 'router');
  const allRouters = devices.filter(d => d.device_type === 'router');
  const backupFilteredSwitches = allSwitches.filter(s => s.hostname.toLowerCase().includes(maintBackupSearch.toLowerCase())).sort(sortTargets);
  const backupFilteredRouters = allRouters.filter(r => r.hostname.toLowerCase().includes(maintBackupSearch.toLowerCase())).sort(sortTargets);
  const restoreFilteredSwitches = allSwitches.filter(s => s.hostname.toLowerCase().includes(maintRestoreSearch.toLowerCase())).sort(sortTargets);
  const restoreFilteredRouters = allRouters.filter(r => r.hostname.toLowerCase().includes(maintRestoreSearch.toLowerCase())).sort(sortTargets);

  const toggleSelection = (hostname, list, setList) => {
    setList(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname]);
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', height: '100%' }}>
      <h2 style={{ marginBottom: '20px' }}>Configuration Maintenance</h2>
      
      <div style={{ display: 'flex', gap: '30px', alignItems: 'flex-start' }}>
        {/* --- LEFT PANEL: BACKUP --- */}
        <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
          <h3 style={{ marginTop: 0, color: '#007acc', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Backup Operations</h3>
          
          <div style={{ marginBottom: '20px', backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', border: '1px solid #444' }}>
            <h4 style={{ color: '#fff', margin: '0 0 10px 0', fontSize: '0.9rem' }}>Destination Options</h4>
            <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontSize: '0.85rem' }}>
                <input type="checkbox" checked={backupDestNVRAM} onChange={(e) => setBackupDestNVRAM(e.target.checked)} style={{ marginRight: '8px' }} /> Save to NVRAM (write mem)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontSize: '0.85rem' }}>
                <input type="checkbox" checked={backupDestFlash} onChange={(e) => setBackupDestFlash(e.target.checked)} style={{ marginRight: '8px' }} /> Save to Local Flash
              </label>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontSize: '0.85rem' }}>
                <input type="checkbox" checked={backupDestLocal} onChange={(e) => setBackupDestLocal(e.target.checked)} style={{ marginRight: '8px' }} /> Download to Computer
              </label>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontSize: '0.85rem' }}>
                <input type="checkbox" checked={backupDestArchive} onChange={(e) => setBackupDestArchive(e.target.checked)} style={{ marginRight: '8px' }} /> Save to Server Archive
              </label>
            </div>
          </div>

          <div style={{ marginBottom: '30px' }}>
            <h4 style={{ color: '#fff', marginBottom: '10px' }}>1. Single Backup</h4>
            <p style={{ fontSize: '0.85rem', color: '#aaa', marginTop: 0 }}>Pull and store configuration for a single device.</p>
            
            <select value={maintSingleDevice} onChange={e => setMaintSingleDevice(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', marginBottom: '10px' }}>
              <option value="" disabled>-- Select a Device --</option>
              <optgroup label="Switches">
                {allSwitches.sort(sortTargets).map(s => <option key={s.id} value={s.hostname}>{s.hostname}</option>)}
              </optgroup>
              <optgroup label="Routers">
                {allRouters.sort(sortTargets).map(r => <option key={r.id} value={r.hostname}>{r.hostname}</option>)}
              </optgroup>
            </select>

            <input type="text" placeholder="Prefix (e.g., Pre-Maintenance)" value={maintBackupName} onChange={e => setMaintBackupName(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', marginBottom: '15px' }} disabled={!backupDestLocal && !backupDestArchive} />
            
            <button 
              onClick={handleSingleBackup} 
              disabled={isBackingUp || userRole !== 'admin'} 
              title={userRole !== 'admin' ? "Administrator access required" : ""}
              style={{ width: '100%', padding: '10px', backgroundColor: (isBackingUp || userRole !== 'admin') ? '#555' : '#007acc', color: (userRole !== 'admin') ? '#aaa' : 'white', border: 'none', borderRadius: '4px', cursor: (isBackingUp || userRole !== 'admin') ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}
            >
              {isBackingUp ? 'Executing Backup...' : 'Run Single Backup'}
            </button>
          </div>

          <div style={{ borderTop: '1px dashed #444', paddingTop: '20px' }}>
            <h4 style={{ color: '#fff', marginBottom: '10px' }}>2. Bulk Backup</h4>
            <p style={{ fontSize: '0.85rem', color: '#aaa', marginTop: 0 }}>Pull and store configurations for multiple devices.</p>
            
            <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
              <input type="text" placeholder="Search devices..." value={maintBackupSearch} onChange={(e) => setMaintBackupSearch(e.target.value)} style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e', border: '1px solid #444', color: 'white', borderRadius: '4px' }} />
              <input type="text" placeholder="Prefix (e.g., Weekly)" value={maintBackupPrefix} onChange={(e) => setMaintBackupPrefix(e.target.value)} style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e', border: '1px solid #444', color: 'white', borderRadius: '4px' }} disabled={!backupDestLocal && !backupDestArchive} />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '15px' }}>
              <div style={{ backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: '4px', overflow: 'hidden' }}>
                <div onClick={() => setIsBackupSwitchesOpen(!isBackupSwitchesOpen)} style={{ padding: '10px 15px', backgroundColor: '#2a2a2a', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: isBackupSwitchesOpen ? '1px solid #444' : 'none' }}>
                  <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#ccc' }}>Switches ({maintBackupSwitches.length} selected)</span>
                  <span style={{ fontSize: '0.8rem', color: '#888' }}>{isBackupSwitchesOpen ? '▼' : '▶'}</span>
                </div>
                {isBackupSwitchesOpen && (
                  <div style={{ maxHeight: '150px', overflowY: 'auto', padding: '10px' }}>
                    {backupFilteredSwitches.map(s => (
                      <label key={s.id} style={{ display: 'flex', alignItems: 'center', padding: '6px', cursor: 'pointer', borderRadius: '4px', backgroundColor: maintBackupSwitches.includes(s.hostname) ? '#007acc22' : 'transparent' }}>
                        <input type="checkbox" checked={maintBackupSwitches.includes(s.hostname)} onChange={() => toggleSelection(s.hostname, maintBackupSwitches, setMaintBackupSwitches)} style={{ marginRight: '10px' }} />
                        <span style={{ fontSize: '0.85rem' }}>{s.hostname}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <div style={{ backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: '4px', overflow: 'hidden' }}>
                <div onClick={() => setIsBackupRoutersOpen(!isBackupRoutersOpen)} style={{ padding: '10px 15px', backgroundColor: '#2a2a2a', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: isBackupRoutersOpen ? '1px solid #444' : 'none' }}>
                  <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#ccc' }}>Routers ({maintBackupRouters.length} selected)</span>
                  <span style={{ fontSize: '0.8rem', color: '#888' }}>{isBackupRoutersOpen ? '▼' : '▶'}</span>
                </div>
                {isBackupRoutersOpen && (
                  <div style={{ maxHeight: '150px', overflowY: 'auto', padding: '10px' }}>
                    {backupFilteredRouters.map(r => (
                      <label key={r.id} style={{ display: 'flex', alignItems: 'center', padding: '6px', cursor: 'pointer', borderRadius: '4px', backgroundColor: maintBackupRouters.includes(r.hostname) ? '#007acc22' : 'transparent' }}>
                        <input type="checkbox" checked={maintBackupRouters.includes(r.hostname)} onChange={() => toggleSelection(r.hostname, maintBackupRouters, setMaintBackupRouters)} style={{ marginRight: '10px' }} />
                        <span style={{ fontSize: '0.85rem' }}>{r.hostname}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
            
            <button 
              onClick={handleBulkBackup} 
              disabled={isBulkBackingUp || userRole !== 'admin'} 
              title={userRole !== 'admin' ? "Administrator access required" : ""}
              style={{ width: '100%', padding: '10px', backgroundColor: (isBulkBackingUp || userRole !== 'admin') ? '#555' : '#007acc', color: (userRole !== 'admin') ? '#aaa' : '#fff', border: '1px solid #555', borderRadius: '4px', cursor: (isBulkBackingUp || userRole !== 'admin') ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}
            >
              {isBulkBackingUp ? 'Executing Bulk Backup...' : 'Run Bulk Backup'}
            </button>

          </div>
        </div>

        {/* --- RIGHT PANEL: RESTORE --- */}
        <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
          <h3 style={{ marginTop: 0, color: '#e6a23c', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Restore Operations</h3>
            <div style={{ marginBottom: '20px' }}>
              <h4 style={{ color: '#fff', marginBottom: '10px' }}>1. Select Configuration Version</h4>
              <div style={{ display: 'flex', gap: '15px', marginBottom: '10px' }}>
                <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', color: '#ccc', fontSize: '0.9rem' }}>
                  <input type="radio" checked={maintRestoreMode === 'archive'} onChange={() => setMaintRestoreMode('archive')} style={{ marginRight: '8px' }}/> Server Archive
                </label>
                <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', color: '#ccc', fontSize: '0.9rem' }}>
                  <input type="radio" checked={maintRestoreMode === 'upload'} onChange={() => setMaintRestoreMode('upload')} style={{ marginRight: '8px' }}/> Local Upload
                </label>
              </div>

              {maintRestoreMode === 'archive' ? (
               <div style={{ display: 'flex', gap: '10px' }}>
                  <select value={maintRestoreOs} onChange={e => {setMaintRestoreOs(e.target.value); setMaintRestoreHost(''); setMaintRestoreFile('')}} style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #555', borderRadius: '4px', textTransform: 'capitalize' }}>
                    <option value="">-- OS --</option>
                    {Object.keys(archiveFiles).map(os => <option key={os} value={os}>{os}</option>)}
                  </select>
                  
                  <select value={maintRestoreHost} onChange={e => {setMaintRestoreHost(e.target.value); setMaintRestoreFile('')}} disabled={!maintRestoreOs} style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #555', borderRadius: '4px' }}>
                    <option value="">-- Device --</option>
                    {maintRestoreOs && archiveFiles[maintRestoreOs] && Object.entries(archiveFiles[maintRestoreOs]).map(([devType, hostsObj]) => (
                       <optgroup key={devType} label={devType === 'switch' ? 'Switches' : devType === 'router' ? 'Routers' : devType.toUpperCase()}>
                           {Object.keys(hostsObj).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map(host => (
                               <option key={host} value={host}>{host}</option>
                           ))}
                       </optgroup>
                    ))}
                  </select>
                  
                  <select value={maintRestoreFile} onChange={e => setMaintRestoreFile(e.target.value)} disabled={!maintRestoreHost} style={{ flex: 2, padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #e6a23c', borderRadius: '4px' }}>
                    <option value="">-- Select File from Archive --</option>
                    {maintRestoreOs && maintRestoreHost && 
                      Object.values(archiveFiles[maintRestoreOs])
                        .find(hostsObj => hostsObj[maintRestoreHost])?.[maintRestoreHost]
                        ?.sort().reverse().map(f => <option key={f} value={f}>{f.replace('.txt', '')}</option>)
                    }
                  </select>
               </div>
            ) : (
              <input type="file" onChange={e => setMaintRestoreUpload(e.target.files[0])} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', border: '1px dashed #555', borderRadius: '4px', color: '#ccc' }} />
            )}
            </div>
          <div style={{ marginBottom: '25px' }}>
            <h4 style={{ color: '#fff', marginBottom: '10px' }}>2. Select Target Devices</h4>
            <p style={{ fontSize: '0.85rem', color: '#aaa', marginTop: 0 }}>Choose which devices will receive this configuration.</p>
            <input type="text" placeholder="Search devices to restore..." value={maintRestoreSearch} onChange={(e) => setMaintRestoreSearch(e.target.value)} style={{ width: '100%', padding: '10px', marginBottom: '15px', backgroundColor: '#1e1e1e', border: '1px solid #444', color: 'white', borderRadius: '4px' }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: '4px', overflow: 'hidden' }}>
                <div onClick={() => setIsRestoreSwitchesOpen(!isRestoreSwitchesOpen)} style={{ padding: '10px 15px', backgroundColor: '#2a2a2a', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: isRestoreSwitchesOpen ? '1px solid #444' : 'none' }}>
                  <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#ccc' }}>Switches ({maintRestoreSwitches.length} selected)</span>
                  <span style={{ fontSize: '0.8rem', color: '#888' }}>{isRestoreSwitchesOpen ? '▼' : '▶'}</span>
                </div>
                {isRestoreSwitchesOpen && (
                  <div style={{ maxHeight: '150px', overflowY: 'auto', padding: '10px' }}>
                    {restoreFilteredSwitches.map(s => (
                      <label key={s.id} style={{ display: 'flex', alignItems: 'center', padding: '6px', cursor: 'pointer', borderRadius: '4px', backgroundColor: maintRestoreSwitches.includes(s.hostname) ? '#007acc22' : 'transparent' }}>
                        <input type="checkbox" checked={maintRestoreSwitches.includes(s.hostname)} onChange={() => toggleSelection(s.hostname, maintRestoreSwitches, setMaintRestoreSwitches)} style={{ marginRight: '10px' }} />
                        <span style={{ fontSize: '0.85rem' }}>{s.hostname}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
              <div style={{ backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: '4px', overflow: 'hidden' }}>
                <div onClick={() => setIsRestoreRoutersOpen(!isRestoreRoutersOpen)} style={{ padding: '10px 15px', backgroundColor: '#2a2a2a', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: isRestoreRoutersOpen ? '1px solid #444' : 'none' }}>
                  <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#ccc' }}>Routers ({maintRestoreRouters.length} selected)</span>
                  <span style={{ fontSize: '0.8rem', color: '#888' }}>{isRestoreRoutersOpen ? '▼' : '▶'}</span>
                </div>
                {isRestoreRoutersOpen && (
                  <div style={{ maxHeight: '150px', overflowY: 'auto', padding: '10px' }}>
                    {restoreFilteredRouters.map(r => (
                      <label key={r.id} style={{ display: 'flex', alignItems: 'center', padding: '6px', cursor: 'pointer', borderRadius: '4px', backgroundColor: maintRestoreRouters.includes(r.hostname) ? '#007acc22' : 'transparent' }}>
                        <input type="checkbox" checked={maintRestoreRouters.includes(r.hostname)} onChange={() => toggleSelection(r.hostname, maintRestoreRouters, setMaintRestoreRouters)} style={{ marginRight: '10px' }} />
                        <span style={{ fontSize: '0.85rem' }}>{r.hostname}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
          <div style={{ padding: '15px', backgroundColor: '#f4433611', border: '1px solid #f4433655', borderRadius: '4px', marginBottom: '15px' }}>
            <span style={{ color: '#f44336', fontWeight: 'bold', fontSize: '0.9rem' }}>⚠️ Warning:</span>
            <span style={{ color: '#aaa', fontSize: '0.85rem', marginLeft: '5px' }}>Restoring a configuration will overwrite the current running-config on the selected targets.</span>
          </div>
          
          <button 
            onClick={handleRestore} 
            disabled={isRestoring || userRole !== 'admin'} 
            title={userRole !== 'admin' ? "Administrator access required" : ""}
            style={{ width: '100%', padding: '12px', backgroundColor: (isRestoring || userRole !== 'admin') ? '#555' : '#e6a23c', color: (isRestoring || userRole !== 'admin') ? '#aaa' : 'black', border: 'none', borderRadius: '4px', cursor: (isRestoring || userRole !== 'admin') ? 'not-allowed' : 'pointer', fontWeight: 'bold', fontSize: '1rem' }}
          >
            {isRestoring ? 'Pushing Configurations...' : 'Execute Restore'}
          </button>

        </div>
        
      </div>
    </div>
  );
}