import { useState, useEffect } from 'react'

// --- CENTRALIZED API URL ---
const API_URL = 'http://127.0.0.1:8000/device/' 
const MAP_URL = 'http://127.0.0.1:8000/network-map/'

function App() {
  // --- STATE MANAGEMENT ---
  const [activeTab, setActiveTab] = useState('Maintenance')
  const [devices, setDevices] = useState([])
  const [isRefreshing, setIsRefreshing] = useState(false)
  
  // Configuration Tab States
  const [aiPrompt, setAiPrompt] = useState('')
  const [selectedSwitches, setSelectedSwitches] = useState([])
  const [selectedRouters, setSelectedRouters] = useState([])
  
  // Sidebar Search States
  const [connectionSearch, setConnectionSearch] = useState('')
  const [dropdownSearch, setDropdownSearch] = useState('')

  // Inventory Tab States
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [formData, setFormData] = useState({
    hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin'
  })

  // --- MAINTENANCE TAB STATES ---
  // Global Backup Destinations (Applies to Single & Bulk)
  const [backupDestNVRAM, setBackupDestNVRAM] = useState(false)
  const [backupDestFlash, setBackupDestFlash] = useState(false)
  const [backupDestLocal, setBackupDestLocal] = useState(true)

  // Single Download
  const [maintSingleDevice, setMaintSingleDevice] = useState('')
  const [maintBackupName, setMaintBackupName] = useState('')
  const [isBackingUp, setIsBackingUp] = useState(false)

  // Bulk Backup
  const [maintBackupSearch, setMaintBackupSearch] = useState('') 
  const [maintBackupPrefix, setMaintBackupPrefix] = useState('') 
  const [maintBackupSwitches, setMaintBackupSwitches] = useState([])
  const [maintBackupRouters, setMaintBackupRouters] = useState([])
  const [isBackupSwitchesOpen, setIsBackupSwitchesOpen] = useState(false)
  const [isBackupRoutersOpen, setIsBackupRoutersOpen] = useState(false) 
  const [isBulkBackingUp, setIsBulkBackingUp] = useState(false)
  
  // Restore
  const [maintRestoreSearch, setMaintRestoreSearch] = useState('') 
  const [maintRestoreFile, setMaintRestoreFile] = useState(null)
  const [maintRestoreSwitches, setMaintRestoreSwitches] = useState([])
  const [maintRestoreRouters, setMaintRestoreRouters] = useState([])
  const [isRestoreSwitchesOpen, setIsRestoreSwitchesOpen] = useState(false)
  const [isRestoreRoutersOpen, setIsRestoreRoutersOpen] = useState(false)
  const [isRestoring, setIsRestoring] = useState(false)

  const TABS = ['Configuration', 'Maintenance', 'Compare', 'Templates', 'Inventory', 'Event Logs']

  // --- HELPER: TIMESTAMP GENERATOR ---
  const getTimestamp = () => {
    const now = new Date()
    const yyyy = now.getFullYear()
    const mm = String(now.getMonth() + 1).padStart(2, '0')
    const dd = String(now.getDate()).padStart(2, '0')
    const hh = String(now.getHours()).padStart(2, '0')
    const min = String(now.getMinutes()).padStart(2, '0')
    const ss = String(now.getSeconds()).padStart(2, '0')
    return `${yyyy}${mm}${dd}_${hh}${min}${ss}`
  }

  // --- DATA FETCHING ---
  const fetchNetworkStatus = () => {
    setIsRefreshing(true)
    fetch(MAP_URL)
      .then(res => res.json())
      .then(data => { setDevices(data); setIsRefreshing(false) })
      .catch(err => { console.error(err); setIsRefreshing(false) })
  }

  useEffect(() => {
    fetchNetworkStatus()
    const intervalId = setInterval(fetchNetworkStatus, 30000)
    return () => clearInterval(intervalId)
  }, [])

  // --- INVENTORY CRUD FUNCTIONS ---
  const handleSubmit = (e) => {
    e.preventDefault()
    setIsSubmitting(true)
    const url = editingId ? `${API_URL}${editingId}` : API_URL
    const method = editingId ? 'PUT' : 'POST'

    fetch(url, {
      method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData)
    }).then(() => {
      setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin' })
      setEditingId(null)
      fetchNetworkStatus() 
      setIsSubmitting(false)
    }).catch(err => { console.error(err); setIsSubmitting(false) })
  }

  const handleDeleteDevice = (id) => {
    if(!window.confirm("Are you sure you want to delete this device?")) return;
    fetch(`${API_URL}${id}`, { method: 'DELETE' }).then(() => fetchNetworkStatus())
  }

  // --- MAINTENANCE API FUNCTIONS ---
  const handleSingleBackup = () => {
    if (!maintSingleDevice) return alert("Please select a device from the dropdown first.");
    if (!backupDestNVRAM && !backupDestFlash && !backupDestLocal) return alert("Please select at least one backup destination.");
    const targetDevice = devices.find(d => d.hostname === maintSingleDevice);
    if (!targetDevice) return;

    setIsBackingUp(true);
    fetch(`http://127.0.0.1:8000/backup-device/${targetDevice.id}`, { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ save_nvram: backupDestNVRAM, save_flash: backupDestFlash, download_local: backupDestLocal })
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
        // Strictly Format: Prefix_Hostname_YYYYMMDD_HHMMSS.txt
        const prefix = maintBackupName ? maintBackupName : 'Single';
        a.download = `${prefix}_${data.hostname}_${getTimestamp()}.txt`;
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
  }

  const handleBulkBackup = () => {
    const selectedHostnames = [...maintBackupSwitches, ...maintBackupRouters];
    if (selectedHostnames.length === 0) return alert("Please select at least one device to backup.");
    if (!backupDestNVRAM && !backupDestFlash && !backupDestLocal) return alert("Please select at least one backup destination.");
    
    const targetIds = selectedHostnames.map(h => devices.find(d => d.hostname === h).id);
    setIsBulkBackingUp(true);
    
    fetch(`${API_URL.replace('/device/', '/bulk-backup/')}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        device_ids: targetIds,
        options: { save_nvram: backupDestNVRAM, save_flash: backupDestFlash, download_local: backupDestLocal }
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
  }

  const handleRestore = () => {
    if (!maintRestoreFile) return alert("Please upload a configuration file first.");
    const selectedHostnames = [...maintRestoreSwitches, ...maintRestoreRouters];
    if (selectedHostnames.length === 0) return alert("Please select target devices.");
    if (!window.confirm(`WARNING: This will overwrite the configuration on ${selectedHostnames.length} device(s). Proceed?`)) return;

    const targetIds = selectedHostnames.map(h => devices.find(d => d.hostname === h).id);
    setIsRestoring(true);

    const reader = new FileReader();
    reader.onload = (e) => {
      const fileContent = e.target.result;
      fetch(`${API_URL.replace('/device/', '/restore-devices/')}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_ids: targetIds, config_content: fileContent })
      })
      .then(res => res.json())
      .then(data => {
        alert("Restore process completed! Check your browser console for detailed logs.");
        console.log("RESTORE RESULTS:", data.details);
        setIsRestoring(false);
        setMaintRestoreFile(null);
        setMaintRestoreSwitches([]);
        setMaintRestoreRouters([]);
      })
      .catch(err => { console.error(err); alert("Restore failed."); setIsRestoring(false); });
    };
    reader.readAsText(maintRestoreFile);
  }

  // --- SORTING & FILTERING LOGIC ---
  const sortConnections = (a, b) => {
    if (a.status === 'online' && b.status !== 'online') return -1;
    if (a.status !== 'online' && b.status === 'online') return 1;
    return a.hostname.localeCompare(b.hostname);
  };
  const sortTargets = (a, b) => a.hostname.localeCompare(b.hostname);

  const allSwitches = devices.filter(d => d.device_type !== 'router')
  const allRouters = devices.filter(d => d.device_type === 'router')

  const switchConnections = allSwitches.filter(d => d.hostname.toLowerCase().includes(connectionSearch.toLowerCase())).sort(sortConnections)
  const routerConnections = allRouters.filter(d => d.hostname.toLowerCase().includes(connectionSearch.toLowerCase())).sort(sortConnections)
  
  const maxConnectionsToShow = activeTab === 'Configuration' ? 3 : 100

  const backupFilteredSwitches = allSwitches.filter(s => s.hostname.toLowerCase().includes(maintBackupSearch.toLowerCase())).sort(sortTargets)
  const backupFilteredRouters = allRouters.filter(r => r.hostname.toLowerCase().includes(maintBackupSearch.toLowerCase())).sort(sortTargets)

  const restoreFilteredSwitches = allSwitches.filter(s => s.hostname.toLowerCase().includes(maintRestoreSearch.toLowerCase())).sort(sortTargets)
  const restoreFilteredRouters = allRouters.filter(r => r.hostname.toLowerCase().includes(maintRestoreSearch.toLowerCase())).sort(sortTargets)

  const toggleSelection = (hostname, list, setList) => {
    setList(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname])
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: '#1e1e1e', color: '#fff' }}>
      
      {/* ================= TOP NAVIGATION TABS ================= */}
      <div style={{ display: 'flex', backgroundColor: '#252526', borderBottom: '1px solid #333', padding: '0 20px', alignItems: 'center' }}>
        <h2 style={{ marginRight: '40px', color: '#007acc', letterSpacing: '1px' }}>VNMS</h2>
        <div style={{ display: 'flex', gap: '2px' }}>
          {TABS.map(tab => (
            <button 
              key={tab} onClick={() => setActiveTab(tab)}
              style={{ padding: '15px 25px', backgroundColor: activeTab === tab ? '#1e1e1e' : 'transparent', color: activeTab === tab ? '#fff' : '#aaa', border: 'none', borderTop: activeTab === tab ? '3px solid #007acc' : '3px solid transparent', cursor: 'pointer', fontWeight: activeTab === tab ? 'bold' : 'normal', fontSize: '1rem' }}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        
        {/* ================= DYNAMIC SIDEBAR ================= */}
        <div style={{ width: '320px', backgroundColor: '#252526', padding: '1.5rem', borderRight: '1px solid #333', overflowY: 'auto' }}>
          {/* Sidebar Content Stays the Same */}
          <div style={{ marginBottom: '30px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h3 style={{ margin: 0 }}>Connections</h3>
              <button onClick={fetchNetworkStatus} style={{ background: 'none', border: 'none', color: '#007acc', cursor: 'pointer' }}>{isRefreshing ? '↻...' : '↻ Refresh'}</button>
            </div>
            <input type="text" placeholder="Search connections..." value={connectionSearch} onChange={(e) => setConnectionSearch(e.target.value)} style={{ width: '100%', padding: '8px', marginBottom: '15px', backgroundColor: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }} />

            <h4 style={{ color: '#aaa', margin: '5px 0' }}>Switches</h4>
            {switchConnections.slice(0, maxConnectionsToShow).map(device => (
              <div key={device.id} style={{ display: 'flex', alignItems: 'center', padding: '8px', backgroundColor: '#2d2d2d', marginBottom: '5px', borderRadius: '4px' }}>
                <span style={{ fontSize: '0.9rem', flex: 1 }}>{device.hostname}</span>
                <span style={{ color: '#888', fontSize: '0.8rem', marginRight: '10px', fontFamily: 'monospace' }}>{device.ip_address}</span>
                <span style={{ height: '10px', width: '10px', borderRadius: '50%', backgroundColor: device.status === 'online' ? '#4caf50' : '#f44336' }}></span>
              </div>
            ))}
            {switchConnections.length > maxConnectionsToShow && <div style={{ fontSize: '0.8rem', color: '#888', textAlign: 'center' }}>+ {switchConnections.length - maxConnectionsToShow} more...</div>}

            <h4 style={{ color: '#aaa', margin: '15px 0 5px 0' }}>Routers</h4>
            {routerConnections.length === 0 ? <div style={{ fontSize: '0.8rem', color: '#666', padding: '8px' }}>No routers configured</div> : routerConnections.slice(0, maxConnectionsToShow).map(device => (
              <div key={device.id} style={{ display: 'flex', alignItems: 'center', padding: '8px', backgroundColor: '#2d2d2d', marginBottom: '5px', borderRadius: '4px' }}>
                <span style={{ fontSize: '0.9rem', flex: 1 }}>{device.hostname}</span>
                <span style={{ color: '#888', fontSize: '0.8rem', marginRight: '10px', fontFamily: 'monospace' }}>{device.ip_address}</span>
                <span style={{ height: '10px', width: '10px', borderRadius: '50%', backgroundColor: device.status === 'online' ? '#4caf50' : '#f44336' }}></span>
              </div>
            ))}
            {routerConnections.length > maxConnectionsToShow && <div style={{ fontSize: '0.8rem', color: '#888', textAlign: 'center' }}>+ {routerConnections.length - maxConnectionsToShow} more...</div>}
          </div>

          {activeTab === 'Configuration' && (
            <div style={{ borderTop: '1px solid #444', paddingTop: '20px' }}>
              <h3 style={{ margin: '0 0 10px 0' }}>Target Devices</h3>
              <input type="text" placeholder="Search targets..." value={dropdownSearch} onChange={(e) => setDropdownSearch(e.target.value)} style={{ width: '100%', padding: '8px', marginBottom: '15px', backgroundColor: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }} />
              
              <h4 style={{ color: '#aaa', margin: '5px 0', fontSize: '0.85rem' }}>Select Switches</h4>
              <div style={{ maxHeight: '120px', overflowY: 'auto', backgroundColor: '#2d2d2d', border: '1px solid #444', borderRadius: '4px', padding: '5px', marginBottom: '15px' }}>
                {allSwitches.filter(s => s.hostname.toLowerCase().includes(dropdownSearch.toLowerCase())).sort(sortTargets).map(s => (
                  <label key={s.id} style={{ display: 'flex', alignItems: 'center', padding: '6px', cursor: 'pointer', borderRadius: '4px', backgroundColor: selectedSwitches.includes(s.hostname) ? '#007acc44' : 'transparent' }}>
                    <input type="checkbox" checked={selectedSwitches.includes(s.hostname)} onChange={() => toggleSelection(s.hostname, selectedSwitches, setSelectedSwitches)} style={{ marginRight: '10px', cursor: 'pointer' }} />
                    <span style={{ fontSize: '0.9rem' }}>{s.hostname}</span>
                  </label>
                ))}
              </div>
              
              <h4 style={{ color: '#aaa', margin: '5px 0', fontSize: '0.85rem' }}>Select Routers</h4>
              <div style={{ maxHeight: '120px', overflowY: 'auto', backgroundColor: '#2d2d2d', border: '1px solid #444', borderRadius: '4px', padding: '5px' }}>
                {allRouters.filter(r => r.hostname.toLowerCase().includes(dropdownSearch.toLowerCase())).sort(sortTargets).map(r => (
                  <label key={r.id} style={{ display: 'flex', alignItems: 'center', padding: '6px', cursor: 'pointer', borderRadius: '4px', backgroundColor: selectedRouters.includes(r.hostname) ? '#007acc44' : 'transparent' }}>
                    <input type="checkbox" checked={selectedRouters.includes(r.hostname)} onChange={() => toggleSelection(r.hostname, selectedRouters, setSelectedRouters)} style={{ marginRight: '10px', cursor: 'pointer' }} />
                    <span style={{ fontSize: '0.9rem' }}>{r.hostname}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ================= MAIN CONTENT AREA ================= */}
        <div style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
          
          {/* TAB: MAINTENANCE */}
          {activeTab === 'Maintenance' && (
            <div style={{ maxWidth: '1200px', margin: '0 auto', height: '100%' }}>
              <h2 style={{ marginBottom: '20px' }}>Configuration Maintenance</h2>
              
              <div style={{ display: 'flex', gap: '30px', alignItems: 'flex-start' }}>
                
                {/* --- LEFT PANEL: BACKUP --- */}
                <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
                  <h3 style={{ marginTop: 0, color: '#007acc', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Backup Operations</h3>
                  
                  {/* NEW: Universal Backup Options */}
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
                    </div>
                  </div>

                  {/* Single Backup Section */}
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

                    <input type="text" placeholder="Prefix (e.g., Pre-Maintenance)" value={maintBackupName} onChange={e => setMaintBackupName(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', marginBottom: '15px' }} disabled={!backupDestLocal} />
                    
                    <button onClick={handleSingleBackup} disabled={isBackingUp} style={{ width: '100%', padding: '10px', backgroundColor: isBackingUp ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: isBackingUp ? 'wait' : 'pointer', fontWeight: 'bold' }}>
                      {isBackingUp ? 'Executing Backup...' : 'Run Single Backup'}
                    </button>
                  </div>

                  {/* Bulk Backup Section */}
                  <div style={{ borderTop: '1px dashed #444', paddingTop: '20px' }}>
                    <h4 style={{ color: '#fff', marginBottom: '10px' }}>2. Bulk Backup</h4>
                    <p style={{ fontSize: '0.85rem', color: '#aaa', marginTop: 0 }}>Pull and store configurations for multiple devices.</p>
                    
                    <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
                      <input type="text" placeholder="Search devices..." value={maintBackupSearch} onChange={(e) => setMaintBackupSearch(e.target.value)} style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e', border: '1px solid #444', color: 'white', borderRadius: '4px' }} />
                      <input type="text" placeholder="Prefix (e.g., Weekly)" value={maintBackupPrefix} onChange={(e) => setMaintBackupPrefix(e.target.value)} style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e', border: '1px solid #444', color: 'white', borderRadius: '4px' }} disabled={!backupDestLocal} />
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
                    <button onClick={handleBulkBackup} disabled={isBulkBackingUp} style={{ width: '100%', padding: '10px', backgroundColor: isBulkBackingUp ? '#555' : '#007acc', color: '#fff', border: '1px solid #555', borderRadius: '4px', cursor: isBulkBackingUp ? 'wait' : 'pointer', fontWeight: 'bold' }}>
                      {isBulkBackingUp ? 'Executing Bulk Backup...' : 'Run Bulk Backup'}
                    </button>
                  </div>
                </div>

                {/* --- RIGHT PANEL: RESTORE --- */}
                <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
                  <h3 style={{ marginTop: 0, color: '#e6a23c', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Restore Operations</h3>
                  <div style={{ marginBottom: '20px' }}>
                    <h4 style={{ color: '#fff', marginBottom: '10px' }}>1. Upload Configuration File</h4>
                    <p style={{ fontSize: '0.85rem', color: '#aaa', marginTop: 0 }}>Select a previously downloaded `.cfg` or `.txt` file.</p>
                    <input type="file" onChange={e => setMaintRestoreFile(e.target.files[0])} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', border: '1px dashed #555', borderRadius: '4px', color: '#ccc' }} />
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
                  <button onClick={handleRestore} disabled={isRestoring} style={{ width: '100%', padding: '12px', backgroundColor: isRestoring ? '#555' : '#e6a23c', color: isRestoring ? '#ccc' : 'black', border: 'none', borderRadius: '4px', cursor: isRestoring ? 'wait' : 'pointer', fontWeight: 'bold', fontSize: '1rem' }}>
                    {isRestoring ? 'Pushing Configurations...' : 'Execute Restore'}
                  </button>
                </div>
                
              </div>
            </div>
          )}

          {/* ... OTHER TABS (Config, Inventory) ... */}
          {activeTab === 'Configuration' && (
             <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
             <h2>AI Configuration Engine</h2>
             <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
               <textarea placeholder="e.g., 'Configure VLAN 10 and 20...'" value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} style={{ width: '100%', height: '100px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', padding: '15px', borderRadius: '4px', resize: 'vertical' }} />
               <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '10px' }}><button style={{ padding: '10px 20px', backgroundColor: '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>Generate Logic</button></div>
             </div>
             <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
               <h3 style={{ marginTop: 0 }}>Generated Configuration</h3>
               <pre style={{ backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', color: '#d4d4d4', overflowX: 'auto', border: '1px solid #444', minHeight: '100px' }}>
                 {selectedSwitches.length > 0 || selectedRouters.length > 0 ? `! Ready to generate config for:\n! Switches: ${selectedSwitches.join(', ') || 'None'}\n! Routers: ${selectedRouters.join(', ') || 'None'}` : `! Please select target devices from the sidebar...`}
               </pre>
             </div>
           </div>
          )}

          {activeTab === 'Inventory' && (
             <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
             <h2>Device Inventory Management</h2>
             <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '30px' }}>
               <h3 style={{ marginTop: 0, marginBottom: '15px', color: editingId ? '#e6a23c' : '#fff' }}>{editingId ? `Editing Device: ${formData.hostname}` : 'Add New Device'}</h3>
               <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                 <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Hostname</label><input required type="text" value={formData.hostname} onChange={e => setFormData({...formData, hostname: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
                 <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>IP Address</label><input required type="text" value={formData.ip_address} onChange={e => setFormData({...formData, ip_address: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
                 <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Device Type</label><select value={formData.device_type} onChange={e => setFormData({...formData, device_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="switch">Switch</option><option value="router">Router</option></select></div>
                 <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>OS Type</label><select value={formData.os_type} onChange={e => setFormData({...formData, os_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="cisco">Cisco</option><option value="hpe">HPE</option><option value="aruba">Aruba</option><option value="mikrotik">MikroTik</option></select></div>
                 <div style={{ display: 'flex', gap: '10px' }}>
                   {editingId && <button type="button" onClick={() => { setEditingId(null); setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin' }) }} style={{ padding: '10px', backgroundColor: '#555', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', height: '39px' }}>Cancel</button>}
                   <button type="submit" disabled={isSubmitting} style={{ padding: '10px 20px', backgroundColor: editingId ? '#e6a23c' : '#007acc', color: editingId ? 'black' : 'white', border: 'none', borderRadius: '4px', cursor: isSubmitting ? 'wait' : 'pointer', fontWeight: 'bold', height: '39px' }}>{isSubmitting ? 'Saving...' : (editingId ? 'Update Device' : '+ Add Device')}</button>
                 </div>
               </form>
             </div>
             
             <h3 style={{ marginBottom: '10px', borderBottom: '1px solid #444', paddingBottom: '5px' }}>Switch Inventory</h3>
             <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflow: 'hidden', marginBottom: '30px' }}>
               <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                 <thead style={{ backgroundColor: '#333' }}><tr><th style={{ padding: '12px' }}>Hostname</th><th style={{ padding: '12px' }}>IP Address</th><th style={{ padding: '12px' }}>Device Type</th><th style={{ padding: '12px' }}>OS Type</th><th style={{ padding: '12px', textAlign: 'center' }}>Actions</th></tr></thead>
                 <tbody>
                   {allSwitches.length === 0 ? <tr><td colSpan="5" style={{ padding: '20px', textAlign: 'center', color: '#666' }}>No switches found.</td></tr> : allSwitches.map((device) => (
                     <tr key={device.id} style={{ borderBottom: '1px solid #444' }}><td style={{ padding: '12px', fontWeight: 'bold' }}>{device.hostname}</td><td style={{ padding: '12px', fontFamily: 'monospace', color: '#aaa' }}>{device.ip_address}</td><td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.device_type}</td><td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.os_type || 'Unknown'}</td><td style={{ padding: '12px', textAlign: 'center' }}><button onClick={() => { setEditingId(device.id); setFormData({ hostname: device.hostname, ip_address: device.ip_address, device_type: device.device_type, os_type: device.os_type || 'cisco', username: device.username || 'admin' }); window.scrollTo({ top: 0, behavior: 'smooth' }) }} style={{ padding: '4px 10px', backgroundColor: '#e6a23c22', color: '#e6a23c', border: '1px solid #e6a23c', borderRadius: '4px', cursor: 'pointer', marginRight: '5px' }}>Edit</button><button onClick={() => handleDeleteDevice(device.id)} style={{ padding: '4px 10px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer' }}>Delete</button></td></tr>
                   ))}
                 </tbody>
               </table>
             </div>
           </div>
          )}

        </div>
      </div>
    </div>
  )
}

export default App