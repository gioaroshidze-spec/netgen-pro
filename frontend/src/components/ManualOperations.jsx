import React, { useState } from 'react';

// --- DYNAMIC API ROUTING ---
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const API_URL = `${API_BASE}/device/`;

export default function ManualOperations({ devices }) {
  // Global Backup Destinations
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

  const getTimestamp = () => {
    const now = new Date();
    return `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
  };

  const handleSingleBackup = () => {
    if (!maintSingleDevice) return alert("Please select a device from the dropdown first.");
    if (!backupDestLocal && !backupDestArchive) return alert("Please select at least one backup destination.");
    const targetDevice = devices.find(d => d.hostname === maintSingleDevice);
    if (!targetDevice) return;
    setIsBackingUp(true);
    
    fetch(`${API_BASE}/backup-device/${targetDevice.id}`, { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify({ save_nvram: false, save_flash: false, download_local: backupDestLocal, save_archive: backupDestArchive, prefix: maintBackupName })
    })
    .then(async (res) => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Backup failed"); }
      return res.json();
    })
    .then(data => {
      if (backupDestLocal && data.config) {
        const blob = new Blob([data.config], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = data.filename; 
        document.body.appendChild(a); a.click(); window.URL.revokeObjectURL(url); a.remove();
      } else if (!backupDestLocal) { 
        alert(data.message || `Backup successfully saved on ${data.hostname}`); 
      }
      setIsBackingUp(false); setMaintBackupName('');
    })
    .catch(err => { console.error(err); alert(`Failed to backup: ${err.message}`); setIsBackingUp(false); });
  };

  const handleBulkBackup = () => {
    const selectedHostnames = [...maintBackupSwitches, ...maintBackupRouters];
    if (selectedHostnames.length === 0) return alert("Please select at least one device to backup.");
    if (!backupDestLocal && !backupDestArchive) return alert("Please select at least one backup destination.");
    const targetIds = selectedHostnames.map(h => devices.find(d => d.hostname === h).id);
    setIsBulkBackingUp(true);
    
    fetch(`${API_URL.replace('/device/', '/bulk-backup/')}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify({ device_ids: targetIds, options: { save_nvram: false, save_flash: false, download_local: backupDestLocal, save_archive: backupDestArchive, prefix: maintBackupPrefix } })
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Bulk backup failed"); }
      
      // If returning a ZIP, we check for a custom header if available, otherwise just blob it.
      if (backupDestLocal) {
        const backupStatus = res.headers.get('X-Backup-Status');
        if (backupStatus === 'Partial-Failure') {
          alert("Bulk backup finished with some errors. The downloaded ZIP contains error logs for the failed devices.");
        }
        return res.blob();
      }
      return res.json();
    }) 
    .then(data => {
      if (backupDestLocal) {
        const url = window.URL.createObjectURL(data);
        const a = document.createElement('a'); a.href = url;
        a.download = `${maintBackupPrefix ? maintBackupPrefix : 'Bulk'}_Archive_${getTimestamp()}.zip`;
        document.body.appendChild(a); a.click(); window.URL.revokeObjectURL(url); a.remove();
      } else { 
        // Show the actual backend JSON message which respects the has_failures flag
        alert(data.message || "Bulk backup completed."); 
      }
      setIsBulkBackingUp(false); setMaintBackupSwitches([]); setMaintBackupRouters([]); setMaintBackupPrefix('');
    })
    .catch(err => { console.error(err); alert(`Error: ${err.message}`); setIsBulkBackingUp(false); });
  };


  const sortTargets = (a, b) => a.hostname.localeCompare(b.hostname, undefined, { numeric: true });
  const allSwitches = devices.filter(d => d.device_type !== 'router');
  const allRouters = devices.filter(d => d.device_type === 'router');
  const backupFilteredSwitches = allSwitches.filter(s => s.hostname.toLowerCase().includes(maintBackupSearch.toLowerCase())).sort(sortTargets);
  const backupFilteredRouters = allRouters.filter(r => r.hostname.toLowerCase().includes(maintBackupSearch.toLowerCase())).sort(sortTargets);
  const toggleSelection = (hostname, list, setList) => {
    setList(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname]);
  };

  return (
    <div style={{ display: 'flex', gap: '30px', alignItems: 'flex-start' }}>
      {/* --- LEFT PANEL: BACKUP --- */}
      <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
        <h3 style={{ marginTop: 0, color: '#007acc', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Backup Operations</h3>
        
        <div style={{ marginBottom: '20px', backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', border: '1px solid #444' }}>
          <h4 style={{ color: '#fff', margin: '0 0 10px 0', fontSize: '0.9rem' }}>Destination Options</h4>
          <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontSize: '0.85rem' }}>
              <input type="checkbox" checked={backupDestLocal} onChange={(e) => setBackupDestLocal(e.target.checked)} style={{ marginRight: '8px' }} /> Download to Computer
            </label>
            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontSize: '0.85rem' }}>
              <input type="checkbox" checked={backupDestArchive} onChange={(e) => setBackupDestArchive(e.target.checked)} style={{ marginRight: '8px' }} /> Save to Server Archive
            </label>
          </div>
          <p style={{ marginBottom: 0, color: '#aaa', fontSize: '0.82rem' }}>Backups are controller/archive-only and do not modify startup configuration or device flash.</p>
        </div>

        <div style={{ marginBottom: '30px' }}>
          <h4 style={{ color: '#fff', marginBottom: '10px' }}>1. Single Backup</h4>
          <select value={maintSingleDevice} onChange={e => setMaintSingleDevice(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', marginBottom: '10px' }}>
            <option value="" disabled>-- Select a Device --</option>
            <optgroup label="Switches">{allSwitches.sort(sortTargets).map(s => <option key={s.id} value={s.hostname}>{s.hostname}</option>)}</optgroup>
            <optgroup label="Routers">{allRouters.sort(sortTargets).map(r => <option key={r.id} value={r.hostname}>{r.hostname}</option>)}</optgroup>
          </select>
          <input type="text" placeholder="Prefix (e.g., Pre-Maintenance)" value={maintBackupName} onChange={e => setMaintBackupName(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', marginBottom: '15px' }} disabled={!backupDestLocal && !backupDestArchive} />
          <button onClick={handleSingleBackup} disabled={isBackingUp} style={{ width: '100%', padding: '10px', backgroundColor: isBackingUp ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: isBackingUp ? 'wait' : 'pointer', fontWeight: 'bold' }}>{isBackingUp ? 'Executing Backup...' : 'Run Single Backup'}</button>
        </div>

        <div style={{ borderTop: '1px dashed #444', paddingTop: '20px' }}>
          <h4 style={{ color: '#fff', marginBottom: '10px' }}>2. Bulk Backup</h4>
          <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
            <input type="text" placeholder="Search devices..." value={maintBackupSearch} onChange={(e) => setMaintBackupSearch(e.target.value)} style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e', border: '1px solid #444', color: 'white', borderRadius: '4px' }} />
            <input type="text" placeholder="Prefix (e.g., Weekly)" value={maintBackupPrefix} onChange={(e) => setMaintBackupPrefix(e.target.value)} style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e', border: '1px solid #444', color: 'white', borderRadius: '4px' }} disabled={!backupDestLocal && !backupDestArchive} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '15px' }}>
            <div style={{ backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: '4px', overflow: 'hidden' }}>
              <div onClick={() => setIsBackupSwitchesOpen(!isBackupSwitchesOpen)} style={{ padding: '10px 15px', backgroundColor: '#2a2a2a', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: isBackupSwitchesOpen ? '1px solid #444' : 'none' }}>
                <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#ccc' }}>Switches ({maintBackupSwitches.length} selected)</span><span style={{ fontSize: '0.8rem', color: '#888' }}>{isBackupSwitchesOpen ? '▼' : '▶'}</span>
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
                <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#ccc' }}>Routers ({maintBackupRouters.length} selected)</span><span style={{ fontSize: '0.8rem', color: '#888' }}>{isBackupRoutersOpen ? '▼' : '▶'}</span>
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
          <button onClick={handleBulkBackup} disabled={isBulkBackingUp} style={{ width: '100%', padding: '10px', backgroundColor: isBulkBackingUp ? '#555' : '#007acc', color: 'white', border: '1px solid #555', borderRadius: '4px', cursor: isBulkBackingUp ? 'wait' : 'pointer', fontWeight: 'bold' }}>{isBulkBackingUp ? 'Executing Bulk Backup...' : 'Run Bulk Backup'}</button>
        </div>
      </div>

      <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
        <h3 style={{ marginTop: 0, color: '#e6a23c', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Restore Operations</h3>
        <strong style={{ color: '#e6a23c' }}>Automated Restore Unsupported</strong>
        <p>Automated restore is not qualified for the current platform profiles. Central backup and archive files remain available for comparison and vendor-approved manual procedures.</p>
        <p style={{ color: '#aaa' }}>Use the controlled rollback workflow in Configuration to prepare and verify a manual restore.</p>
      </div>
    </div>
  );
}