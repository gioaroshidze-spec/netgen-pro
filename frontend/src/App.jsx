import React, { useState, useEffect, useCallback } from 'react';

// ==========================================
// --- COMPONENT IMPORTS ---
// ==========================================
import Inventory from './components/Inventory';
import Topology from './components/Topology';
import Dashboard from './components/Dashboard';
import Configuration from './components/Configuration';
import Maintenance from './components/Maintenance';
import Compare from './components/Compare';
import Templates from './components/Templates';
import CLI from './components/CLI';
import EventLogs from './components/EventLogs';
import Users from './components/Users';

export default function App() {
  // ==========================================
  // 1. GLOBAL STATE DEFINITIONS
  // ==========================================
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('token'));
  const [userRole, setUserRole] = useState(localStorage.getItem('role') || 'admin');
  const [activeTab, setActiveTab] = useState('Dashboard'); 
  
  // Data Sources
  const [devices, setDevices] = useState([]);
  const [orgData, setOrgData] = useState([]);
  const [archiveFiles, setArchiveFiles] = useState({});

  // Device Selection Sidebar States (Needed for Config, Maintenance, CLI modules)
  const [selectedSwitches, setSelectedSwitches] = useState([]);
  const [selectedRouters, setSelectedRouters] = useState([]);
  const [loadedTemplate, setLoadedTemplate] = useState(null);

  // Login Form States
  const [loginUser, setLoginUser] = useState('admin');
  const [loginPass, setLoginPass] = useState('');
  const [loginError, setLoginError] = useState('');

  // ==========================================
  // 2. DATA FETCH ENGINE (CALLBACKS)
  // ==========================================
  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    setIsAuthenticated(false);
    setDevices([]);
    setOrgData([]);
    setArchiveFiles({});
    setSelectedSwitches([]);
    setSelectedRouters([]);
    setLoadedTemplate(null);
  };

  const fetchNetworkStatus = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    
    fetch('http://127.0.0.1:8000/network-map/', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(res => res.ok ? res.json() : [])
    .then(data => setDevices(data))
    .catch(err => console.error("Failed to fetch devices:", err));
  }, []);

  const fetchOrgData = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    fetch('http://127.0.0.1:8000/organization/hierarchy', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(res => res.ok ? res.json() : [])
    .then(data => setOrgData(data))
    .catch(err => console.error("Failed to load org tree:", err));
  }, []);

  const fetchArchiveFiles = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    fetch('http://127.0.0.1:8000/archive/files', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(res => res.ok ? res.json() : {})
    .then(data => setArchiveFiles(data))
    .catch(err => console.error("Failed to load archive configs:", err));
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError('');
    const formData = new URLSearchParams();
    formData.append('username', loginUser);
    formData.append('password', loginPass);

    try {
      const res = await fetch('http://127.0.0.1:8000/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData
      });
      if (!res.ok) throw new Error("Invalid credentials");
      const data = await res.json();
      
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('role', 'admin'); 
      setUserRole('admin');
      setIsAuthenticated(true);
    } catch (err) {
      setLoginError("Login Failed. Verify backend /token endpoint and default credentials.");
    }
  };

  // ==========================================
  // 3. BACKGROUND SYNCHRONIZATION
  // ==========================================
  useEffect(() => {
    if (isAuthenticated) {
      fetchNetworkStatus();
      fetchOrgData(); 
      fetchArchiveFiles();
      
      const intervalId = setInterval(() => {
        fetchNetworkStatus();
        fetchArchiveFiles();
      }, 30000);
      return () => clearInterval(intervalId);
    }
  }, [isAuthenticated, fetchNetworkStatus, fetchOrgData, fetchArchiveFiles]);

  // Handle sidebar checkbox toggle
  const handleDeviceToggle = (hostname, type) => {
    if (type === 'switch') {
      setSelectedSwitches(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname]);
    } else {
      setSelectedRouters(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname]);
    }
  };

  // ==========================================
  // 4. ARCHITECTURAL RENDERING
  // ==========================================
  
  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', backgroundColor: '#1e1e1e', color: '#fff' }}>
        <form onSubmit={handleLogin} style={{ textAlign: 'center', padding: '40px', backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', width: '350px' }}>
          <h2 style={{ color: '#007acc', marginBottom: '20px' }}>VNMS Login</h2>
          {loginError && <div style={{ color: '#f44336', marginBottom: '15px', fontSize: '0.9rem' }}>{loginError}</div>}
          <input type="text" placeholder="Username" value={loginUser} onChange={e => setLoginUser(e.target.value)} required style={{ width: '100%', padding: '10px', marginBottom: '15px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px' }} />
          <input type="password" placeholder="Password" value={loginPass} onChange={e => setLoginPass(e.target.value)} required style={{ width: '100%', padding: '10px', marginBottom: '20px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px' }} />
          <button type="submit" style={{ width: '100%', padding: '12px', backgroundColor: '#007acc', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>Secure Login</button>
        </form>
      </div>
    );
  }

  const tabs = ['Dashboard', 'Configuration', 'Maintenance', 'Compare', 'Templates', 'CLI', 'Inventory', 'Event Logs', 'Topology', 'Users'];

  // Condition to check if left operations sidebar should show up
  const showOperationsSidebar = ['Configuration', 'Maintenance', 'CLI'].includes(activeTab);

  return (
    <div style={{ backgroundColor: '#1e1e1e', color: '#fff', minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      
      {/* TOP NAVIGATION BAR */}
      <nav style={{ display: 'flex', backgroundColor: '#252526', padding: '0 20px', borderBottom: '1px solid #333', alignItems: 'center', overflowX: 'auto', zIndex: 10 }}>
        <div style={{ fontWeight: 'bold', fontSize: '1.2rem', color: '#007acc', marginRight: '30px' }}>VNMS Pro</div>
        <div style={{ display: 'flex', flex: 1 }}>
          {tabs.map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{ padding: '15px 20px', backgroundColor: 'transparent', color: activeTab === tab ? '#fff' : '#aaa', border: 'none', borderBottom: activeTab === tab ? '3px solid #007acc' : '3px solid transparent', cursor: 'pointer', fontWeight: activeTab === tab ? 'bold' : 'normal', whiteSpace: 'nowrap' }}>{tab}</button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginLeft: '20px' }}>
          <span style={{ fontSize: '0.85rem', color: '#aaa' }}>Logged in as: <strong style={{ color: '#fff' }}>Admin</strong> <span style={{ color: '#4caf50', marginLeft: '5px', fontSize: '0.7rem' }}>{userRole.toUpperCase()}</span></span>
          <button onClick={handleLogout} style={{ padding: '6px 12px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 'bold' }}>Logout</button>
        </div>
      </nav>

      {/* BODY INTERACTION FRAME */}
      <div style={{ display: 'flex', flex: 1, height: 'calc(100vh - 50px)', position: 'relative' }}>
        
        {/* LEFT NODE ASSIGNMENT SIDEBAR */}
        {showOperationsSidebar && (
          <aside style={{ width: '260px', backgroundColor: '#252526', borderRight: '1px solid #333', padding: '20px', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
            <h3 style={{ margin: '0 0 15px 0', fontSize: '0.95rem', textTransform: 'uppercase', letterSpacing: '1px', color: '#888' }}>Target Selector</h3>
            
            <div style={{ marginBottom: '20px' }}>
              <strong style={{ color: '#007acc', display: 'block', marginBottom: '8px', fontSize: '0.9rem' }}>🔌 Switches</strong>
              {devices.filter(d => d.device_type === 'switch').map(dev => (
                <label key={dev.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0', cursor: 'pointer', color: '#ccc', fontSize: '0.85rem' }}>
                  <input type="checkbox" checked={selectedSwitches.includes(dev.hostname)} onChange={() => handleDeviceToggle(dev.hostname, 'switch')} />
                  <span style={{ color: dev.status === 'online' ? '#4caf50' : '#f44336' }}>●</span> {dev.hostname}
                </label>
              ))}
            </div>

            <div>
              <strong style={{ color: '#e6a23c', display: 'block', marginBottom: '8px', fontSize: '0.9rem' }}>🛰️ Routers</strong>
              {devices.filter(d => d.device_type === 'router').map(dev => (
                <label key={dev.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0', cursor: 'pointer', color: '#ccc', fontSize: '0.85rem' }}>
                  <input type="checkbox" checked={selectedRouters.includes(dev.hostname)} onChange={() => handleDeviceToggle(dev.hostname, 'router')} />
                  <span style={{ color: dev.status === 'online' ? '#4caf50' : '#f44336' }}>●</span> {dev.hostname}
                </label>
              ))}
            </div>
          </aside>
        )}

        {/* WORKSPACE AREA */}
        <main style={{ flex: 1, padding: '25px', overflowY: 'auto', backgroundColor: '#1e1e1e' }}>
          
          {activeTab === 'Dashboard' && <Dashboard devices={devices} setActiveTab={setActiveTab} userRole={userRole} />}
          
          {activeTab === 'Configuration' && (
            <Configuration 
              selectedSwitches={selectedSwitches} 
              selectedRouters={selectedRouters} 
              loadedTemplate={loadedTemplate} 
              setLoadedTemplate={setLoadedTemplate} 
              userRole={userRole} 
            />
          )}
          
          {activeTab === 'Maintenance' && <Maintenance devices={devices} archiveFiles={archiveFiles} userRole={userRole} />}
          {activeTab === 'Compare' && <Compare archiveFiles={archiveFiles} />}
          {activeTab === 'Templates' && <Templates setLoadedTemplate={setLoadedTemplate} setActiveTab={setActiveTab} />}
          {activeTab === 'CLI' && (
            <CLI 
              selectedSwitches={selectedSwitches} 
              selectedRouters={selectedRouters} 
              devices={devices} // <-- ADD This exact line
            />
          )}
          {activeTab === 'Event Logs' && <EventLogs />}
          {activeTab === 'Users' && <Users />}
          
          {activeTab === 'Inventory' && (
            <Inventory 
              devices={devices} 
              fetchNetworkStatus={fetchNetworkStatus} 
              userRole={userRole} 
              orgData={orgData} 
              fetchOrgData={fetchOrgData} 
            />
          )}

          {activeTab === 'Topology' && (
            <Topology 
              devices={devices} 
              userRole={userRole} 
              setActiveTab={setActiveTab} 
              fetchNetworkStatus={fetchNetworkStatus} 
              orgData={orgData} 
            />
          )}

        </main>
      </div>
    </div>
  );
}