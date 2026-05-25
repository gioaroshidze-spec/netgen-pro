import React from 'react';

export default function Dashboard({ devices, setActiveTab, userRole }) {
  const username = localStorage.getItem('username') || 'Operator';
  
  // Calculate real-time network metrics from the devices array
  const onlineCount = devices.filter(d => d.status === 'online').length;
  const offlineCount = devices.filter(d => d.status === 'offline').length;
  const totalCount = devices.length;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', paddingBottom: '40px' }}>
      
      {/* Welcome Banner */}
      <div style={{ backgroundColor: '#007acc15', border: '1px solid #007acc', padding: '30px', borderRadius: '8px', marginBottom: '30px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: '0 0 10px 0', color: '#007acc' }}>Welcome back, <span style={{textTransform: 'capitalize'}}>{username}</span></h2>
          <div style={{ color: '#ccc', fontSize: '1.1rem' }}>VNMS (Veziri Network Management System) is online and ready.</div>
        </div>
        <div style={{ fontSize: '3.5rem' }}>🌐</div>
      </div>

      {/* Network Health Metrics */}
      <div style={{ display: 'flex', gap: '20px', marginBottom: '30px', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333', minWidth: '200px' }}>
          <div style={{ color: '#aaa', fontSize: '0.9rem', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '1px' }}>Managed Nodes</div>
          <div style={{ fontSize: '3rem', fontWeight: 'bold', color: '#fff' }}>{totalCount}</div>
        </div>
        
        <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333', minWidth: '200px', borderBottom: '4px solid #4caf50' }}>
          <div style={{ color: '#aaa', fontSize: '0.9rem', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '1px' }}>Nodes Online</div>
          <div style={{ fontSize: '3rem', fontWeight: 'bold', color: '#4caf50' }}>{onlineCount}</div>
        </div>
        
        <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333', minWidth: '200px', borderBottom: '4px solid #f44336' }}>
          <div style={{ color: '#aaa', fontSize: '0.9rem', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '1px' }}>Nodes Offline</div>
          <div style={{ fontSize: '3rem', fontWeight: 'bold', color: '#f44336' }}>{offlineCount}</div>
        </div>
      </div>

      {/* Quick Action Navigation */}
      <h3 style={{ marginBottom: '20px', color: '#fff', borderBottom: '1px solid #333', paddingBottom: '10px' }}>System Modules</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px' }}>
        
        <button onClick={() => setActiveTab('Configuration')} style={{ backgroundColor: '#252526', border: '1px solid #444', padding: '20px', borderRadius: '8px', color: '#fff', cursor: 'pointer', textAlign: 'left', transition: 'background-color 0.2s' }}>
          <div style={{ fontSize: '2rem', marginBottom: '15px' }}>⚡</div>
          <strong style={{ display: 'block', fontSize: '1.2rem', marginBottom: '8px' }}>AI Configuration</strong>
          <span style={{ color: '#aaa', fontSize: '0.9rem', lineHeight: '1.4', display: 'block' }}>Generate and deploy network changes via AI-driven JSON models and Ansible.</span>
        </button>
        
        <button onClick={() => setActiveTab('Maintenance')} style={{ backgroundColor: '#252526', border: '1px solid #444', padding: '20px', borderRadius: '8px', color: '#fff', cursor: 'pointer', textAlign: 'left', transition: 'background-color 0.2s' }}>
          <div style={{ fontSize: '2rem', marginBottom: '15px' }}>💾</div>
          <strong style={{ display: 'block', fontSize: '1.2rem', marginBottom: '8px' }}>Backup & Restore</strong>
          <span style={{ color: '#aaa', fontSize: '0.9rem', lineHeight: '1.4', display: 'block' }}>Manage bulk configuration archives and emergency rollback procedures.</span>
        </button>
        
        <button onClick={() => setActiveTab('CLI')} style={{ backgroundColor: '#252526', border: '1px solid #444', padding: '20px', borderRadius: '8px', color: '#fff', cursor: 'pointer', textAlign: 'left', transition: 'background-color 0.2s' }}>
          <div style={{ fontSize: '2rem', marginBottom: '15px' }}>💻</div>
          <strong style={{ display: 'block', fontSize: '1.2rem', marginBottom: '8px' }}>Secure Web CLI</strong>
          <span style={{ color: '#aaa', fontSize: '0.9rem', lineHeight: '1.4', display: 'block' }}>Establish direct SSH interactive terminal sessions to inventory devices.</span>
        </button>
        
        <button onClick={() => setActiveTab('Event Logs')} style={{ backgroundColor: '#252526', border: '1px solid #444', padding: '20px', borderRadius: '8px', color: '#fff', cursor: 'pointer', textAlign: 'left', transition: 'background-color 0.2s' }}>
          <div style={{ fontSize: '2rem', marginBottom: '15px' }}>📋</div>
          <strong style={{ display: 'block', fontSize: '1.2rem', marginBottom: '8px' }}>System Audit Logs</strong>
          <span style={{ color: '#aaa', fontSize: '0.9rem', lineHeight: '1.4', display: 'block' }}>Review all platform events, playbook executions, and config diffs.</span>
        </button>

      </div>
    </div>
  );
}