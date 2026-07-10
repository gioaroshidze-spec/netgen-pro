import React, { useState, useEffect } from 'react';

// --- DYNAMIC API ROUTING ---
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export default function Dashboard({ devices, setActiveTab, userRole }) {
  const [jobs, setJobs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch Jobs Data on Mount
  useEffect(() => {
    fetch(`${API_BASE}/jobs/`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    .then(res => res.ok ? res.json() : [])
    .then(data => {
      setJobs(data);
      setIsLoading(false);
    })
    .catch(err => {
      console.error("Failed to load scheduled jobs:", err);
      setIsLoading(false);
    });
  }, []);

  const totalDevices = devices.length;
  const onlineCount = devices.filter(d => d.status === 'online').length;
  const offlineCount = devices.filter(d => d.status !== 'online').length;

  const totalJobs = jobs.length;
  const activeJobsCount = jobs.filter(j => j.is_active).length;
  const disabledJobsCount = jobs.filter(j => !j.is_active).length;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ backgroundColor: '#252526', padding: '30px', borderRadius: '8px', border: '1px solid #007acc', marginBottom: '30px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: '0 0 10px 0', color: '#007acc' }}>Welcome back, {localStorage.getItem('username')}</h2>
          <div style={{ color: '#ccc' }}>VNMS (Veziri Network Management System) is online and ready.</div>
        </div>
        <div style={{ fontSize: '3rem', color: '#007acc' }}>🌐</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', marginBottom: '30px' }}>
        <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333' }}>
          <div style={{ fontSize: '0.85rem', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '10px' }}>Managed Nodes</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: '#fff' }}>{totalDevices}</div>
        </div>
        <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #4caf50' }}>
          <div style={{ fontSize: '0.85rem', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '10px' }}>Nodes Online</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: '#4caf50' }}>{onlineCount}</div>
        </div>
        <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #f44336' }}>
          <div style={{ fontSize: '0.85rem', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '10px' }}>Nodes Offline</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: '#f44336' }}>{offlineCount}</div>
        </div>
      </div>

      {/* --- NEW: SCHEDULED JOBS METRICS --- */}
      <h3 style={{ borderBottom: '1px solid #333', paddingBottom: '10px', marginBottom: '20px' }}>Automation Engine</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', marginBottom: '40px' }}>
        <div style={{ backgroundColor: '#1e1e1e', padding: '20px', borderRadius: '8px', border: '1px solid #333' }}>
          <div style={{ fontSize: '0.85rem', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '10px' }}>Total Jobs</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: '#fff' }}>{isLoading ? '-' : totalJobs}</div>
        </div>
        <div style={{ backgroundColor: '#1e1e1e', padding: '20px', borderRadius: '8px', border: '1px solid #007acc' }}>
          <div style={{ fontSize: '0.85rem', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '10px' }}>Enabled</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: '#007acc' }}>{isLoading ? '-' : activeJobsCount}</div>
        </div>
        <div style={{ backgroundColor: '#1e1e1e', padding: '20px', borderRadius: '8px', border: '1px solid #e6a23c' }}>
          <div style={{ fontSize: '0.85rem', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '10px' }}>Disabled / Paused</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: '#e6a23c' }}>{isLoading ? '-' : disabledJobsCount}</div>
        </div>
      </div>

      <h3 style={{ borderBottom: '1px solid #333', paddingBottom: '10px', marginBottom: '20px' }}>System Modules</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px' }}>
        
        <div onClick={() => setActiveTab('Configuration')} style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', cursor: 'pointer', transition: 'transform 0.2s', ':hover': { transform: 'translateY(-5px)' } }}>
          <div style={{ fontSize: '2rem', marginBottom: '10px', color: '#e6a23c' }}>⚡</div>
          <h4 style={{ margin: '0 0 10px 0', color: '#fff' }}>AI Configuration</h4>
          <p style={{ fontSize: '0.9rem', color: '#aaa', margin: 0 }}>Generate and deploy network changes via AI-driven JSON models and Ansible.</p>
        </div>

        <div onClick={() => setActiveTab('Maintenance')} style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', cursor: 'pointer' }}>
          <div style={{ fontSize: '2rem', marginBottom: '10px', color: '#ccc' }}>💾</div>
          <h4 style={{ margin: '0 0 10px 0', color: '#fff' }}>Backup & Restore</h4>
          <p style={{ fontSize: '0.9rem', color: '#aaa', margin: 0 }}>Manage bulk configuration archives and emergency rollback procedures.</p>
        </div>

        <div onClick={() => setActiveTab('CLI')} style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', cursor: 'pointer' }}>
          <div style={{ fontSize: '2rem', marginBottom: '10px', color: '#007acc' }}>💻</div>
          <h4 style={{ margin: '0 0 10px 0', color: '#fff' }}>Secure Web CLI</h4>
          <p style={{ fontSize: '0.9rem', color: '#aaa', margin: 0 }}>Establish direct SSH interactive terminal sessions to inventory devices.</p>
        </div>

        <div onClick={() => setActiveTab('Event Logs')} style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', cursor: 'pointer' }}>
          <div style={{ fontSize: '2rem', marginBottom: '10px', color: '#e6a23c' }}>📋</div>
          <h4 style={{ margin: '0 0 10px 0', color: '#fff' }}>System Audit Logs</h4>
          <p style={{ fontSize: '0.9rem', color: '#aaa', margin: 0 }}>Review all platform events, playbook executions, and config diffs.</p>
        </div>

      </div>
    </div>
  );
}