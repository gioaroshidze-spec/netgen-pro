import { useState, useEffect } from 'react'

function App() {
  // --- STATE MANAGEMENT ---
  const [activeTab, setActiveTab] = useState('Configuration')
  const [devices, setDevices] = useState([])
  const [isRefreshing, setIsRefreshing] = useState(false)
  
  // Configuration Tab States
  const [aiPrompt, setAiPrompt] = useState('')
  const [selectedDevices, setSelectedDevices] = useState([])
  const [generatedLogic, setGeneratedLogic] = useState(null)
  
  // Sidebar Search States
  const [connectionSearch, setConnectionSearch] = useState('')
  const [dropdownSearch, setDropdownSearch] = useState('')

  const TABS = ['Configuration', 'Maintenance', 'Compare', 'Templates', 'Inventory', 'Event Logs']

  // --- MOCK DATA FETCH (Replace with real API later) ---
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

  // --- FILTERING LOGIC ---
  // For now, assuming everything is a switch. We will segregate by type later!
  const switches = devices.filter(d => d.hostname.toLowerCase().includes(connectionSearch.toLowerCase()))
  const routers = [] // Placeholder for when we add routers

  // Logic to determine how many devices to show in the connection list
  const maxConnectionsToShow = activeTab === 'Configuration' ? 3 : 100

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: '#1e1e1e', color: '#fff' }}>
      
      {/* ================= TOP NAVIGATION TABS ================= */}
      <div style={{ display: 'flex', backgroundColor: '#252526', borderBottom: '1px solid #333', padding: '0 20px' }}>
        <h2 style={{ marginRight: '40px', color: '#007acc' }}>NetGen Pro</h2>
        <div style={{ display: 'flex', gap: '2px' }}>
          {TABS.map(tab => (
            <button 
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '15px 25px',
                backgroundColor: activeTab === tab ? '#1e1e1e' : 'transparent',
                color: activeTab === tab ? '#fff' : '#aaa',
                border: 'none',
                borderTop: activeTab === tab ? '3px solid #007acc' : '3px solid transparent',
                cursor: 'pointer',
                fontWeight: activeTab === tab ? 'bold' : 'normal',
                fontSize: '1rem'
              }}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        
        {/* ================= DYNAMIC SIDEBAR ================= */}
        <div style={{ width: '320px', backgroundColor: '#252526', padding: '1.5rem', borderRight: '1px solid #333', overflowY: 'auto' }}>
          
          {/* 1. Connection Status Section */}
          <div style={{ marginBottom: '30px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h3 style={{ margin: 0 }}>Connections</h3>
              <button onClick={fetchNetworkStatus} style={{ background: 'none', border: 'none', color: '#007acc', cursor: 'pointer' }}>
                {isRefreshing ? '↻...' : '↻ Refresh'}
              </button>
            </div>
            
            <input 
              type="text" 
              placeholder="Search connections..." 
              value={connectionSearch}
              onChange={(e) => setConnectionSearch(e.target.value)}
              style={{ width: '100%', padding: '8px', marginBottom: '15px', backgroundColor: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }}
            />

            <h4 style={{ color: '#aaa', margin: '5px 0' }}>Switches</h4>
            {switches.slice(0, maxConnectionsToShow).map(device => (
              <div key={device.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px', backgroundColor: '#2d2d2d', marginBottom: '5px', borderRadius: '4px' }}>
                <span style={{ fontSize: '0.9rem' }}>{device.hostname}</span>
                <span style={{ height: '10px', width: '10px', borderRadius: '50%', backgroundColor: device.status === 'online' ? '#4caf50' : '#f44336', marginTop: '4px' }}></span>
              </div>
            ))}
            {switches.length > maxConnectionsToShow && <div style={{ fontSize: '0.8rem', color: '#888', textAlign: 'center' }}>+ {switches.length - maxConnectionsToShow} more...</div>}
          </div>

          {/* 2. Device Selection Dropdowns (ONLY ON CONFIG TAB) */}
          {activeTab === 'Configuration' && (
            <div style={{ borderTop: '1px solid #444', paddingTop: '20px' }}>
              <h3 style={{ margin: '0 0 10px 0' }}>Target Devices</h3>
              <input 
                type="text" 
                placeholder="Search targets..." 
                value={dropdownSearch}
                onChange={(e) => setDropdownSearch(e.target.value)}
                style={{ width: '100%', padding: '8px', marginBottom: '15px', backgroundColor: '#333', border: '1px solid #444', color: 'white', borderRadius: '4px' }}
              />
              
              {/* Dummy Dropdowns for UI Mockup */}
              <select multiple style={{ width: '100%', height: '100px', backgroundColor: '#2d2d2d', color: '#fff', border: '1px solid #444', padding: '5px', borderRadius: '4px', marginBottom: '10px' }}>
                <option disabled>-- Select Switches --</option>
                {switches.map(s => <option key={s.id} value={s.hostname}>{s.hostname}</option>)}
              </select>
              
              <select multiple style={{ width: '100%', height: '80px', backgroundColor: '#2d2d2d', color: '#fff', border: '1px solid #444', padding: '5px', borderRadius: '4px' }}>
                <option disabled>-- Select Routers --</option>
                <option disabled style={{ color: '#666' }}>(No routers in DB)</option>
              </select>
            </div>
          )}
        </div>

        {/* ================= MAIN CONTENT AREA ================= */}
        <div style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
          
          {activeTab === 'Configuration' ? (
            <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
              <h2>AI Configuration Engine</h2>
              
              {/* AI Chat Box */}
              <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
                <textarea 
                  placeholder="e.g., 'Configure VLAN 10 and 20 on the selected switches and set the management IP to 192.168.1.5'"
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  style={{ width: '100%', height: '100px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', padding: '15px', borderRadius: '4px', resize: 'vertical' }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '10px' }}>
                  <button style={{ padding: '10px 20px', backgroundColor: '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>
                    Generate Logic
                  </button>
                </div>
              </div>

              {/* Generated Commands Box */}
              <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
                <h3 style={{ marginTop: 0 }}>Generated Configuration</h3>
                <pre style={{ backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', color: '#d4d4d4', overflowX: 'auto', border: '1px solid #444' }}>
                  ! Commands will appear here, segregated by device...
                </pre>
              </div>

              {/* Action Buttons & Terminal */}
              <div style={{ display: 'flex', gap: '15px', marginBottom: '20px' }}>
                <button style={{ padding: '12px 24px', backgroundColor: '#e6a23c', color: 'black', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', flex: 1 }}>
                  Simulate Changes (Dry Run)
                </button>
                <button style={{ padding: '12px 24px', backgroundColor: '#4caf50', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', flex: 1 }}>
                  Push Configuration
                </button>
              </div>

              {/* Terminal Output Window */}
              <div style={{ backgroundColor: '#000', padding: '20px', borderRadius: '8px', border: '1px solid #333', height: '200px', overflowY: 'auto' }}>
                <div style={{ color: '#aaa', fontFamily: 'monospace' }}>&gt; Terminal output and Ansible logs will appear here...</div>
              </div>

            </div>
          ) : (
            <div>
              <h2>{activeTab}</h2>
              <p style={{ color: '#aaa' }}>This module is currently under construction.</p>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

export default App