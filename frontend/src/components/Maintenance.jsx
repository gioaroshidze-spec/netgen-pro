import React, { useState } from 'react';
import ManualOperations from './ManualOperations';
import ScheduledJobs from './ScheduledJobs';

export default function Maintenance({ devices, archiveFiles, userRole }) {
  const [activeView, setActiveView] = useState('manual');

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', height: '100%' }}>
      
      {/* HEADER WITH TOGGLE */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ margin: 0 }}>Configuration Maintenance</h2>
        <div style={{ display: 'flex', gap: '5px', backgroundColor: '#1e1e1e', padding: '4px', borderRadius: '6px', border: '1px solid #333' }}>
          <button 
            onClick={() => setActiveView('manual')} 
            style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: activeView === 'manual' ? '#007acc' : 'transparent', color: activeView === 'manual' ? 'white' : '#aaa' }}
          >
            Manual Operations
          </button>
          <button 
            onClick={() => setActiveView('scheduled')} 
            style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: activeView === 'scheduled' ? '#007acc' : 'transparent', color: activeView === 'scheduled' ? 'white' : '#aaa' }}
          >
            Scheduled Jobs
          </button>
        </div>
      </div>

      {/* VIEW ROUTER */}
      {activeView === 'manual' && <ManualOperations devices={devices} archiveFiles={archiveFiles} userRole={userRole} />}
      {activeView === 'scheduled' && <ScheduledJobs devices={devices} userRole={userRole} />}

    </div>
  );
}