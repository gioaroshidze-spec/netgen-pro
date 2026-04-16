import { useState, useEffect } from 'react'

function App() {
  // --- STATE MANAGEMENT ---
  const [activeTab, setActiveTab] = useState('Configuration')
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
  const [editingId, setEditingId] = useState(null) // Tracks if we are editing an existing device
  const [formData, setFormData] = useState({
    hostname: '',
    ip_address: '',
    device_type: 'switch',
    os_type: 'cisco', // New OS field!
    username: 'admin'
  })

  const TABS = ['Configuration', 'Maintenance', 'Compare', 'Templates', 'Inventory', 'Event Logs']

  // --- DATA FETCHING ---
  const fetchNetworkStatus = () => {
    setIsRefreshing(true)
    fetch('http://127.0.0.1:8000/network-map/')
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
    
    const url = editingId ? `http://127.0.0.1:8000/device/${editingId}` : 'http://127.0.0.1:8000/device/'
    const method = editingId ? 'PUT' : 'POST'

    fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    })
    .then(res => res.json())
    .then(() => {
      setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin' })
      setEditingId(null)
      fetchNetworkStatus() 
      setIsSubmitting(false)
    })
    .catch(err => { console.error("Error saving device:", err); setIsSubmitting(false) })
  }

  const handleEditClick = (device) => {
    setEditingId(device.id)
    setFormData({
      hostname: device.hostname,
      ip_address: device.ip_address,
      device_type: device.device_type === 'router' ? 'router' : 'switch',
      os_type: device.os_type || 'cisco', // Fallback for old DB entries
      username: device.username || 'admin'
    })
    // Scroll to top of page so user sees the form
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDeleteDevice = (id) => {
    if(!window.confirm("Are you sure you want to delete this device?")) return;
    fetch(`http://127.0.0.1:8000/device/${id}`, { method: 'DELETE' })
    .then(() => fetchNetworkStatus())
    .catch(err => console.error("Error deleting device:", err))
  }

  const cancelEdit = () => {
    setEditingId(null)
    setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin' })
  }

  // --- SORTING & FILTERING LOGIC ---
  
  // 1. Connection Sidebar (Online First, then Alphanumeric)
  const sortConnections = (a, b) => {
    if (a.status === 'online' && b.status !== 'online') return -1;
    if (a.status !== 'online' && b.status === 'online') return 1;
    return a.hostname.localeCompare(b.hostname);
  };

  // 2. Target Dropdowns (Strictly Alphanumeric)
  const sortTargets = (a, b) => a.hostname.localeCompare(b.hostname);

  // Separate real database devices by type (Treating legacy entries as switches)
  const allSwitches = devices.filter(d => d.device_type !== 'router')
  const allRouters = devices.filter(d => d.device_type === 'router')

  // Sidebar Filtered Lists
  const switchConnections = allSwitches.filter(d => d.hostname.toLowerCase().includes(connectionSearch.toLowerCase())).sort(sortConnections)
  const routerConnections = allRouters.filter(d => d.hostname.toLowerCase().includes(connectionSearch.toLowerCase())).sort(sortConnections)
  
  const targetSwitches = allSwitches.filter(s => s.hostname.toLowerCase().includes(dropdownSearch.toLowerCase())).sort(sortTargets)
  const targetRouters = allRouters.filter(r => r.hostname.toLowerCase().includes(dropdownSearch.toLowerCase())).sort(sortTargets)
  
  const maxConnectionsToShow = activeTab === 'Configuration' ? 3 : 100

  const toggleSelection = (hostname, type) => {
    if (type === 'switch') {
      setSelectedSwitches(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname])
    } else {
      setSelectedRouters(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname])
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: '#1e1e1e', color: '#fff' }}>
      
      {/* ================= TOP NAVIGATION TABS ================= */}
      <div style={{ display: 'flex', backgroundColor: '#252526', borderBottom: '1px solid #333', padding: '0 20px' }}>
        <h2 style={{ marginRight: '40px', color: '#007acc' }}>NetGen Pro</h2>
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
          
          <div style={{ marginBottom: '30px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h3 style={{ margin: 0 }}>Connections</h3>
              <button onClick={fetchNetworkStatus} style={{ background: 'none', border: 'none', color: '#007acc', cursor: 'pointer' }}>{isRefreshing ? '↻...' : '↻ Refresh'}</button>
            </div>
            
            <input type="text" placeholder="Search connections..." value={connectionSearch} onChange={(e) => setConnectionSearch(e.target.value)} style={{ width: '100%', padding: '8px', marginBottom: '15px', backgroundColor: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }} />

            <h4 style={{ color: '#aaa', margin: '5px 0' }}>Switches</h4>
            {switchConnections.slice(0, maxConnectionsToShow).map(device => (
              <div key={device.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', backgroundColor: '#2d2d2d', marginBottom: '5px', borderRadius: '4px' }}>
                <span style={{ fontSize: '0.9rem' }}>{device.hostname}</span>
                <span style={{ height: '10px', width: '10px', borderRadius: '50%', backgroundColor: device.status === 'online' ? '#4caf50' : '#f44336', marginTop: '4px' }}></span>
              </div>
            ))}
            {switchConnections.length > maxConnectionsToShow && <div style={{ fontSize: '0.8rem', color: '#888', textAlign: 'center' }}>+ {switchConnections.length - maxConnectionsToShow} more...</div>}

            <h4 style={{ color: '#aaa', margin: '15px 0 5px 0' }}>Routers</h4>
            {routerConnections.length === 0 ? <div style={{ fontSize: '0.8rem', color: '#666', padding: '8px' }}>No routers configured</div> : routerConnections.slice(0, maxConnectionsToShow).map(device => (
              <div key={device.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', backgroundColor: '#2d2d2d', marginBottom: '5px', borderRadius: '4px' }}>
                <span style={{ fontSize: '0.9rem' }}>{device.hostname}</span>
                <span style={{ height: '10px', width: '10px', borderRadius: '50%', backgroundColor: device.status === 'online' ? '#4caf50' : '#f44336', marginTop: '4px' }}></span>
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
                {targetSwitches.length === 0 ? <div style={{ color: '#666', padding: '4px' }}>No switches found</div> : targetSwitches.map(s => (
                  <label key={s.id} style={{ display: 'flex', alignItems: 'center', padding: '6px', cursor: 'pointer', borderRadius: '4px', backgroundColor: selectedSwitches.includes(s.hostname) ? '#007acc44' : 'transparent' }}>
                    <input type="checkbox" checked={selectedSwitches.includes(s.hostname)} onChange={() => toggleSelection(s.hostname, 'switch')} style={{ marginRight: '10px', cursor: 'pointer' }} />
                    <span style={{ fontSize: '0.9rem' }}>{s.hostname}</span>
                  </label>
                ))}
              </div>
              
              <h4 style={{ color: '#aaa', margin: '5px 0', fontSize: '0.85rem' }}>Select Routers</h4>
              <div style={{ maxHeight: '120px', overflowY: 'auto', backgroundColor: '#2d2d2d', border: '1px solid #444', borderRadius: '4px', padding: '5px' }}>
                {targetRouters.length === 0 ? <div style={{ color: '#666', padding: '4px' }}>No routers found</div> : targetRouters.map(r => (
                  <label key={r.id} style={{ display: 'flex', alignItems: 'center', padding: '6px', cursor: 'pointer', borderRadius: '4px', backgroundColor: selectedRouters.includes(r.hostname) ? '#007acc44' : 'transparent' }}>
                    <input type="checkbox" checked={selectedRouters.includes(r.hostname)} onChange={() => toggleSelection(r.hostname, 'router')} style={{ marginRight: '10px', cursor: 'pointer' }} />
                    <span style={{ fontSize: '0.9rem' }}>{r.hostname}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ================= MAIN CONTENT AREA ================= */}
        <div style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
          
          {/* TAB: CONFIGURATION */}
          {activeTab === 'Configuration' && (
            <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
              <h2>AI Configuration Engine</h2>
              {/* AI Chat Box & Generation Code stays the same... */}
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

          {/* TAB: INVENTORY */}
          {activeTab === 'Inventory' && (
            <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
              <h2>Device Inventory Management</h2>
              
              {/* Add/Edit Device Form */}
              <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '30px' }}>
                <h3 style={{ marginTop: 0, marginBottom: '15px', color: editingId ? '#e6a23c' : '#fff' }}>
                  {editingId ? `Editing Device: ${formData.hostname}` : 'Add New Device'}
                </h3>
                <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <div style={{ flex: 1, minWidth: '150px' }}>
                    <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Hostname</label>
                    <input required type="text" value={formData.hostname} onChange={e => setFormData({...formData, hostname: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
                  </div>
                  <div style={{ flex: 1, minWidth: '150px' }}>
                    <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>IP Address</label>
                    <input required type="text" value={formData.ip_address} onChange={e => setFormData({...formData, ip_address: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
                  </div>
                  <div style={{ flex: 1, minWidth: '150px' }}>
                    <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Device Type</label>
                    <select value={formData.device_type} onChange={e => setFormData({...formData, device_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                      <option value="switch">Switch</option>
                      <option value="router">Router</option>
                    </select>
                  </div>
                  <div style={{ flex: 1, minWidth: '150px' }}>
                    <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>OS Type</label>
                    <select value={formData.os_type} onChange={e => setFormData({...formData, os_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                      <option value="cisco">Cisco</option>
                      <option value="hpe">HPE</option>
                      <option value="aruba">Aruba</option>
                      <option value="mikrotik">MikroTik</option>
                    </select>
                  </div>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    {editingId && <button type="button" onClick={cancelEdit} style={{ padding: '10px', backgroundColor: '#555', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', height: '39px' }}>Cancel</button>}
                    <button type="submit" disabled={isSubmitting} style={{ padding: '10px 20px', backgroundColor: editingId ? '#e6a23c' : '#007acc', color: editingId ? 'black' : 'white', border: 'none', borderRadius: '4px', cursor: isSubmitting ? 'wait' : 'pointer', fontWeight: 'bold', height: '39px' }}>
                      {isSubmitting ? 'Saving...' : (editingId ? 'Update Device' : '+ Add Device')}
                    </button>
                  </div>
                </form>
              </div>

              {/* Switches Table */}
              <h3 style={{ marginBottom: '10px', borderBottom: '1px solid #444', paddingBottom: '5px' }}>Switch Inventory</h3>
              <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflow: 'hidden', marginBottom: '30px' }}>
                <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                  <thead style={{ backgroundColor: '#333' }}>
                    <tr><th style={{ padding: '12px' }}>Hostname</th><th style={{ padding: '12px' }}>IP Address</th><th style={{ padding: '12px' }}>Device Type</th><th style={{ padding: '12px' }}>OS Type</th><th style={{ padding: '12px', textAlign: 'center' }}>Actions</th></tr>
                  </thead>
                  <tbody>
                    {allSwitches.length === 0 ? <tr><td colSpan="5" style={{ padding: '20px', textAlign: 'center', color: '#666' }}>No switches found.</td></tr> : allSwitches.map((device) => (
                      <tr key={device.id} style={{ borderBottom: '1px solid #444' }}>
                        <td style={{ padding: '12px', fontWeight: 'bold' }}>{device.hostname}</td><td style={{ padding: '12px', fontFamily: 'monospace', color: '#aaa' }}>{device.ip_address}</td><td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.device_type}</td><td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.os_type || 'Unknown'}</td>
                        <td style={{ padding: '12px', textAlign: 'center' }}>
                          <button onClick={() => handleEditClick(device)} style={{ padding: '4px 10px', backgroundColor: '#e6a23c22', color: '#e6a23c', border: '1px solid #e6a23c', borderRadius: '4px', cursor: 'pointer', marginRight: '5px' }}>Edit</button>
                          <button onClick={() => handleDeleteDevice(device.id)} style={{ padding: '4px 10px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer' }}>Delete</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Routers Table */}
              <h3 style={{ marginBottom: '10px', borderBottom: '1px solid #444', paddingBottom: '5px' }}>Router Inventory</h3>
              <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflow: 'hidden' }}>
                <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                  <thead style={{ backgroundColor: '#333' }}>
                    <tr><th style={{ padding: '12px' }}>Hostname</th><th style={{ padding: '12px' }}>IP Address</th><th style={{ padding: '12px' }}>Device Type</th><th style={{ padding: '12px' }}>OS Type</th><th style={{ padding: '12px', textAlign: 'center' }}>Actions</th></tr>
                  </thead>
                  <tbody>
                    {allRouters.length === 0 ? <tr><td colSpan="5" style={{ padding: '20px', textAlign: 'center', color: '#666' }}>No routers found.</td></tr> : allRouters.map((device) => (
                      <tr key={device.id} style={{ borderBottom: '1px solid #444' }}>
                        <td style={{ padding: '12px', fontWeight: 'bold' }}>{device.hostname}</td><td style={{ padding: '12px', fontFamily: 'monospace', color: '#aaa' }}>{device.ip_address}</td><td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.device_type}</td><td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.os_type || 'Unknown'}</td>
                        <td style={{ padding: '12px', textAlign: 'center' }}>
                          <button onClick={() => handleEditClick(device)} style={{ padding: '4px 10px', backgroundColor: '#e6a23c22', color: '#e6a23c', border: '1px solid #e6a23c', borderRadius: '4px', cursor: 'pointer', marginRight: '5px' }}>Edit</button>
                          <button onClick={() => handleDeleteDevice(device.id)} style={{ padding: '4px 10px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer' }}>Delete</button>
                        </td>
                      </tr>
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