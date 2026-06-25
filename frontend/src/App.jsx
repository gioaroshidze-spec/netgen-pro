import { useState, useEffect } from 'react'
import Inventory from './components/Inventory'
import Compare from './components/Compare'
import Maintenance from './components/Maintenance'
import Configuration from './components/Configuration'
import EventLogs from './components/EventLogs'
import Templates from './components/Templates'
import CLI, { TerminalWindow } from './components/CLI' // <-- IMPORTED TERMINAL WINDOW
import Login from './components/Login'
import Users from './components/Users'
import Dashboard from './components/Dashboard'
import Topology from './components/Topology' 

const MAP_URL = 'http://127.0.0.1:8000/network-map/'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!localStorage.getItem('token'))
  const userRole = localStorage.getItem('role') || 'viewer'
  const currentUsername = localStorage.getItem('username')

  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('vnmsActiveTab') || 'Dashboard')
  
  useEffect(() => {
    if (isAuthenticated) localStorage.setItem('vnmsActiveTab', activeTab)
  }, [activeTab, isAuthenticated])
  
  const [loadedTemplate, setLoadedTemplate] = useState(null)
  const [devices, setDevices] = useState([])
  const [orgData, setOrgData] = useState([]) 
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [archiveFiles, setArchiveFiles] = useState({})
  
  const [selectedSwitches, setSelectedSwitches] = useState([])
  const [selectedRouters, setSelectedRouters] = useState([])
  const [connectionSearch, setConnectionSearch] = useState('')
  const [dropdownSearch, setDropdownSearch] = useState('')

  const TABS = ['Dashboard', 'Configuration', 'Maintenance', 'Compare', 'Templates', 'CLI', 'Inventory', 'Event Logs', 'Topology']
  if (currentUsername === 'admin') TABS.push('Users')

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('role')
    setIsAuthenticated(false)
  }

  const fetchNetworkStatus = () => {
    setIsRefreshing(true)
    fetch(MAP_URL, { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
      .then(res => {
        if (res.status === 401) { handleLogout(); throw new Error("Unauthorized"); }
        if (!res.ok) throw new Error("Failed to fetch network map");
        return res.json();
      })
      .then(data => { setDevices(data); setIsRefreshing(false) })
      .catch(err => { console.error(err); setIsRefreshing(false) })
  }

  const fetchOrgData = () => {
    fetch('http://127.0.0.1:8000/organization/hierarchy', { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
    .then(res => {
      if (res.status === 401) { handleLogout(); throw new Error("Unauthorized"); }
      if (!res.ok) throw new Error("Failed to fetch org tree");
      return res.json();
    })
    .then(data => setOrgData(data))
    .catch(err => console.error(err))
  }

  const fetchArchiveFiles = () => {
    fetch('http://127.0.0.1:8000/archive/files', { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
    .then(res => {
      if (res.status === 401) { handleLogout(); throw new Error("Unauthorized"); }
      if (!res.ok) throw new Error("Failed to fetch archives");
      return res.json();
    })
    .then(data => setArchiveFiles(data))
    .catch(err => console.error("Failed to load archive:", err))
  }

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchNetworkStatus();
    fetchOrgData(); 
    fetchArchiveFiles(); 
    const intervalId = setInterval(() => {
      fetchNetworkStatus();
      fetchArchiveFiles(); 
    }, 30000)
    return () => clearInterval(intervalId)
  }, [isAuthenticated])

  if (!isAuthenticated) {
    return <Login onLoginSuccess={() => setIsAuthenticated(true)} />
  }

  // =================================================================
  // --- THE FIX: INTERCEPT POPUP CLI REQUESTS ---
  // =================================================================
  const urlParams = new URLSearchParams(window.location.search);
  const cliTargetId = urlParams.get('cli');

  if (cliTargetId && devices.length > 0) {
    const targetDev = devices.find(d => d.id.toString() === cliTargetId);
    if (targetDev) {
      return (
        <div style={{ height: '100vh', width: '100vw', backgroundColor: '#000', boxSizing: 'border-box' }}>
          <TerminalWindow device={targetDev} isActive={true} onClose={() => window.close()} />
        </div>
      );
    }
  }
  // =================================================================

  const sortConnections = (a, b) => {
    if (a.status === 'online' && b.status !== 'online') return -1;
    if (a.status !== 'online' && b.status === 'online') return 1;
    return a.hostname.localeCompare(b.hostname, undefined, { numeric: true });
  };
  const sortTargets = (a, b) => a.hostname.localeCompare(b.hostname, undefined, { numeric: true });

  const allSwitches = devices.filter(d => d.device_type !== 'router')
  const allRouters = devices.filter(d => d.device_type === 'router')
  const switchConnections = allSwitches.filter(d => d.hostname.toLowerCase().includes(connectionSearch.toLowerCase())).sort(sortConnections)
  const routerConnections = allRouters.filter(d => d.hostname.toLowerCase().includes(connectionSearch.toLowerCase())).sort(sortConnections)
  const maxConnectionsToShow = activeTab === 'Configuration' ? 3 : 100

  const toggleSelection = (hostname, list, setList) => {
    setList(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname])
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: '#1e1e1e', color: '#fff' }}>
      <div style={{ display: 'flex', backgroundColor: '#252526', borderBottom: '1px solid #333', padding: '0 20px', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <h2 onClick={() => setActiveTab('Configuration')} style={{ marginRight: '40px', color: '#007acc', letterSpacing: '1px', cursor: 'pointer' }}>VNMS</h2>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <span style={{ fontSize: '0.9rem', color: '#aaa' }}>
            Logged in as: <strong style={{ color: '#fff', textTransform: 'capitalize' }}>{localStorage.getItem('username')}</strong> 
            <span style={{ marginLeft: '8px', padding: '2px 6px', backgroundColor: userRole === 'admin' ? '#4caf5022' : '#007acc22', color: userRole === 'admin' ? '#4caf50' : '#007acc', borderRadius: '4px', fontSize: '0.75rem', textTransform: 'uppercase' }}>{userRole}</span>
          </span>
          <button onClick={handleLogout} style={{ padding: '6px 12px', backgroundColor: 'transparent', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>Logout</button>
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{ width: '320px', backgroundColor: '#252526', padding: '1.5rem', borderRight: '1px solid #333', overflowY: 'auto', position: 'sticky', top: '0', height: '100vh'}}>
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

        <div style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
          {activeTab === 'Dashboard' && <Dashboard devices={devices} setActiveTab={setActiveTab} userRole={userRole} />}
          {activeTab === 'Maintenance' && <Maintenance devices={devices} archiveFiles={archiveFiles} userRole={userRole} />}
          {activeTab === 'Compare' && <Compare archiveFiles={archiveFiles} />}
          {activeTab === 'Templates' && <Templates setActiveTab={setActiveTab} setLoadedTemplate={setLoadedTemplate} />}
          {activeTab === 'Configuration' && <Configuration selectedSwitches={selectedSwitches} selectedRouters={selectedRouters} loadedTemplate={loadedTemplate} setLoadedTemplate={setLoadedTemplate} userRole={userRole} />}
          {activeTab === 'CLI' && <CLI devices={devices} />}
          {activeTab === 'Inventory' && <Inventory devices={devices} fetchNetworkStatus={fetchNetworkStatus} userRole={userRole} orgData={orgData} fetchOrgData={fetchOrgData} />}
          {activeTab === 'Event Logs' && <EventLogs />}
          {activeTab === 'Users' && <Users />}
          {activeTab === 'Topology' && <Topology devices={devices} userRole={userRole} setActiveTab={setActiveTab} fetchNetworkStatus={fetchNetworkStatus} orgData={orgData} />}
        </div>
      </div>
    </div>
  )
}

export default App