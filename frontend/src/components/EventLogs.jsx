import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export default function EventLogs() {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null);

  // --- FILTER STATES ---
  const [filterType, setFilterType] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterDevice, setFilterDevice] = useState('');
  const [filterAuthor, setFilterAuthor] = useState('');
  const [filterStartDate, setFilterStartDate] = useState('');
  const [filterEndDate, setFilterEndDate] = useState('');
  const [filterLimit, setFilterLimit] = useState(50);

  const fetchLogs = useCallback(() => {
    setIsLoading(true);
    
    const params = new URLSearchParams();
    if (filterType) params.append('event_type', filterType);
    if (filterSeverity) params.append('severity', filterSeverity);
    if (filterDevice) params.append('device', filterDevice);
    if (filterAuthor) params.append('author', filterAuthor);
    if (filterStartDate) params.append('start_date', new Date(filterStartDate).toISOString());
    if (filterEndDate) params.append('end_date', new Date(filterEndDate).toISOString());
    params.append('limit', filterLimit);

    fetch(`http://127.0.0.1:8000/logs/?${params.toString()}`, {
      headers: { 
        'Authorization': `Bearer ${localStorage.getItem('token')}` // <-- TOKEN INJECTED
      }
    })
      .then(async res => {
        if (!res.ok) throw new Error("Failed to fetch logs");
        return res.json();
      })
      .then(data => {
        setLogs(data);
        setIsLoading(false);
      })
      .catch(err => {
        console.error(err);
        setIsLoading(false);
      });
  }, [filterType, filterSeverity, filterDevice, filterAuthor, filterStartDate, filterEndDate, filterLimit]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const toggleRow = (id) => {
    setExpandedRow(prevRow => (prevRow === id ? null : id));
  };

  const getSeverityColor = (severity) => {
    switch(severity) {
      case 'SUCCESS': return '#4caf50';
      case 'ERROR': return '#f44336';  
      case 'WARNING': return '#ff9800'; 
      case 'INFO': return '#007acc';    
      default: return '#aaa';
    }
  };

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ margin: 0 }}>System Audit Logs</h2>
        <button onClick={fetchLogs} style={{ padding: '8px 15px', backgroundColor: '#333', color: 'white', border: '1px solid #555', borderRadius: '4px', cursor: 'pointer' }}>
          {isLoading ? '↻ Loading...' : '↻ Refresh Data'}
        </button>
      </div>

      <div style={{ backgroundColor: '#252526', padding: '15px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px', display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
        
        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Event Type</label>
          <select value={filterType} onChange={e => setFilterType(e.target.value)} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
            <option value="">All Types</option>
            <option value="Configuration">Configuration (AI/Ansible)</option>
            <option value="Maintenance">Maintenance (Backups/Restore)</option>
            <option value="Inventory">Inventory (CRUD)</option>
          </select>
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Severity</label>
          <select value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
            <option value="">All Severities</option>
            <option value="SUCCESS">Success</option>
            <option value="ERROR">Error</option>
            <option value="WARNING">Warning</option>
            <option value="INFO">Info</option>
          </select>
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Target Device</label>
          <input type="text" placeholder="e.g. cctv_sw1" value={filterDevice} onChange={e => setFilterDevice(e.target.value)} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Author</label>
          <input type="text" placeholder="e.g. System" value={filterAuthor} onChange={e => setFilterAuthor(e.target.value)} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Start Date</label>
          <input type="datetime-local" value={filterStartDate} onChange={e => setFilterStartDate(e.target.value)} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>End Date</label>
          <input type="datetime-local" value={filterEndDate} onChange={e => setFilterEndDate(e.target.value)} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
        </div>
        
        <div style={{ width: '80px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Limit</label>
          <select value={filterLimit} onChange={e => setFilterLimit(e.target.value)} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={500}>500</option>
          </select>
        </div>
      </div>

      <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflowX: 'auto' }}>
        <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse', minWidth: '900px' }}>
          <thead style={{ backgroundColor: '#333' }}>
            <tr>
              <th style={{ padding: '15px' }}>Timestamp</th>
              <th style={{ padding: '15px' }}>Type</th>
              <th style={{ padding: '15px' }}>Severity</th>
              <th style={{ padding: '15px' }}>Author</th>
              <th style={{ padding: '15px' }}>Target Devices</th>
              <th style={{ padding: '15px', textAlign: 'right' }}>Details</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr><td colSpan="6" style={{ padding: '30px', textAlign: 'center', color: '#666' }}>No logs found matching these criteria.</td></tr>
            ) : logs.map((log) => {
              
              let safeDetails = {};
              if (typeof log.details === 'string') {
                try { safeDetails = JSON.parse(log.details); } catch(e) { safeDetails = { raw_string: log.details }; }
              } else if (typeof log.details === 'object' && log.details !== null) {
                safeDetails = log.details;
              }

              const rawPayloadData = Object.fromEntries(
                Object.entries(safeDetails).filter(([k]) => k !== 'ansible_logs' && k !== 'prompt')
              );

              let safeTargets = "None / System";
              if (Array.isArray(log.target_devices) && log.target_devices.length > 0) {
                safeTargets = log.target_devices.join(', ');
              } else if (typeof log.target_devices === 'string' && log.target_devices.trim() !== '') {
                try {
                  const parsed = JSON.parse(log.target_devices);
                  safeTargets = Array.isArray(parsed) ? parsed.join(', ') : parsed;
                } catch(e) {
                  safeTargets = log.target_devices; 
                }
              }

              return (
              <React.Fragment key={log.id}>
                <tr style={{ borderBottom: '1px solid #444', backgroundColor: expandedRow === log.id ? '#2a2a2a' : 'transparent', transition: 'background-color 0.2s' }}>
                  <td style={{ padding: '15px', color: '#aaa', fontSize: '0.9rem' }}>{new Date(log.timestamp).toLocaleString()}</td>
                  <td style={{ padding: '15px', fontWeight: 'bold' }}>{log.event_type}</td>
                  <td style={{ padding: '15px' }}>
                    <span style={{ padding: '4px 8px', borderRadius: '4px', backgroundColor: `${getSeverityColor(log.severity)}22`, color: getSeverityColor(log.severity), fontWeight: 'bold', fontSize: '0.8rem' }}>
                      {log.severity}
                    </span>
                  </td>
                  <td style={{ padding: '15px', color: '#ccc' }}>{log.author}</td>
                  <td style={{ padding: '15px', color: '#ccc', fontSize: '0.9rem', wordBreak: 'break-word', maxWidth: '200px' }}>{safeTargets}</td>
                  <td style={{ padding: '15px', textAlign: 'right' }}>
                    <button onClick={() => toggleRow(log.id)} style={{ padding: '6px 12px', backgroundColor: '#1e1e1e', color: '#007acc', border: '1px solid #007acc', borderRadius: '4px', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                      {expandedRow === log.id ? 'Close' : 'Inspect Data'}
                    </button>
                  </td>
                </tr>

                {expandedRow === log.id && (
                  <tr style={{ backgroundColor: '#1a1a1a', borderBottom: '2px solid #007acc' }}>
                    <td colSpan="6" style={{ padding: '20px' }}>
                      
                      {safeDetails.action && (
                        <div style={{ marginBottom: '15px', fontSize: '1.1rem', fontWeight: 'bold', color: '#e6a23c' }}>
                          Action: {safeDetails.action}
                        </div>
                      )}

                      {safeDetails.prompt && (
                        <div style={{ marginBottom: '15px', backgroundColor: '#252526', padding: '15px', borderRadius: '4px', borderLeft: '4px solid #9c27b0' }}>
                          <strong style={{ color: '#aaa', display: 'block', marginBottom: '5px' }}>User Prompt:</strong>
                          <span style={{ color: '#fff', fontSize: '1.1rem' }}>"{safeDetails.prompt}"</span>
                        </div>
                      )}

                      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                        <div style={{ flex: 1, minWidth: '300px', maxWidth: '100%' }}>
                          <strong style={{ color: '#aaa', display: 'block', marginBottom: '5px' }}>Raw Payload Data:</strong>
                          <pre style={{ backgroundColor: '#000', padding: '15px', borderRadius: '4px', border: '1px solid #333', color: '#569cd6', overflowX: 'auto', maxHeight: '400px', fontSize: '0.85rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {JSON.stringify(rawPayloadData, null, 2)}
                          </pre>
                        </div>

                        {safeDetails.ansible_logs && (
                          <div style={{ flex: 1.5, minWidth: '300px', maxWidth: '100%' }}>
                            <strong style={{ color: '#aaa', display: 'block', marginBottom: '5px' }}>Execution Output (Ansible stdout):</strong>
                            <pre style={{ backgroundColor: '#000', padding: '15px', borderRadius: '4px', border: '1px solid #333', color: '#00ff00', overflowX: 'auto', maxHeight: '400px', fontSize: '0.85rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                              {safeDetails.ansible_logs}
                            </pre>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            )})}
          </tbody>
        </table>
      </div>
    </div>
  );
}