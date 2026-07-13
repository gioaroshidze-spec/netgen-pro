import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export default function EventLogs() {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null);

  // --- FILTER & PAGINATION STATES ---
  const [filterType, setFilterType] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterDevice, setFilterDevice] = useState('');
  const [filterAuthor, setFilterAuthor] = useState('');
  const [filterStartDate, setFilterStartDate] = useState('');
  const [filterEndDate, setFilterEndDate] = useState('');
  const [filterLimit, setFilterLimit] = useState(50);
  const [currentPage, setCurrentPage] = useState(0);
  
  // --- DEEP SEARCH STATE ---
  const [deepSearch, setDeepSearch] = useState('');

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
    params.append('skip', currentPage * filterLimit);

    fetch(`${API_BASE}/logs/?${params.toString()}`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
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
        console.error("Audit log fetch error:", err);
        setIsLoading(false);
      });
  }, [filterType, filterSeverity, filterDevice, filterAuthor, filterStartDate, filterEndDate, filterLimit, currentPage]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // --- CLIENT-SIDE DEEP FUZZY SEARCH ---
  const filteredLogs = logs.filter(log => {
    if (!deepSearch) return true;
    const searchString = JSON.stringify(log).toLowerCase();
    return searchString.includes(deepSearch.toLowerCase());
  });

  // --- CSV EXPORT LOGIC ---
  const exportToCSV = () => {
    const headers = ["Timestamp", "Event Type", "Severity", "Author", "Target Devices", "Details"];
    
    const csvRows = filteredLogs.map(log => {
      let targets = "None";
      if (Array.isArray(log.target_devices)) {
        targets = log.target_devices.map(d => typeof d === 'object' ? d.hostname : d).join(" | ");
      } else if (typeof log.target_devices === 'string') {
        targets = log.target_devices;
      }
      
      const safeDetails = `"${JSON.stringify(log.details).replace(/"/g, '""')}"`;

      return [
        new Date(log.timestamp).toISOString(),
        log.event_type,
        log.severity,
        log.author,
        `"${targets}"`,
        safeDetails
      ].join(",");
    });

    const csvContent = [headers.join(","), ...csvRows].join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `VNMS_Audit_Logs_${new Date().getTime()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

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
        <div style={{ display: 'flex', gap: '10px' }}>
          <button onClick={exportToCSV} style={{ padding: '8px 15px', backgroundColor: '#e6a23c', color: 'black', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>
            📥 Export CSV
          </button>
          <button onClick={fetchLogs} style={{ padding: '8px 15px', backgroundColor: '#333', color: 'white', border: '1px solid #555', borderRadius: '4px', cursor: 'pointer' }}>
            {isLoading ? '↻ Loading...' : '↻ Refresh Data'}
          </button>
        </div>
      </div>

      <div style={{ backgroundColor: '#252526', padding: '15px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px', display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
        
        {/* --- DEEP SEARCH BAR --- */}
        <div style={{ width: '100%', marginBottom: '10px' }}>
          <input 
            type="text" 
            placeholder="🔍 Deep Search (Scan all prompts, JSON payloads, and Ansible output...)" 
            value={deepSearch} 
            onChange={e => setDeepSearch(e.target.value)} 
            style={{ width: '100%', padding: '12px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #007acc', borderRadius: '4px', fontSize: '1rem' }} 
          />
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Event Type</label>
          <select value={filterType} onChange={e => {setFilterType(e.target.value); setCurrentPage(0);}} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
            <option value="">All Types</option>
            <option value="Configuration">Configuration (AI/Ansible)</option>
            <option value="Maintenance">Maintenance (Backups/Restore)</option>
            <option value="Inventory">Inventory (CRUD)</option>
          </select>
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Severity</label>
          <select value={filterSeverity} onChange={e => {setFilterSeverity(e.target.value); setCurrentPage(0);}} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
            <option value="">All Severities</option>
            <option value="SUCCESS">Success</option>
            <option value="ERROR">Error</option>
            <option value="WARNING">Warning</option>
            <option value="INFO">Info</option>
          </select>
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Target Device</label>
          <input type="text" placeholder="e.g. cctv_sw1" value={filterDevice} onChange={e => {setFilterDevice(e.target.value); setCurrentPage(0);}} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
        </div>

        <div style={{ flex: 1, minWidth: '150px' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Author</label>
          <input type="text" placeholder="e.g. System" value={filterAuthor} onChange={e => {setFilterAuthor(e.target.value); setCurrentPage(0);}} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
        </div>

        {/* --- PAGINATION CONTROLS --- */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-end', marginLeft: 'auto' }}>
          <div style={{ width: '80px' }}>
            <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '5px' }}>Limit</label>
            <select value={filterLimit} onChange={e => {setFilterLimit(Number(e.target.value)); setCurrentPage(0);}} style={{ width: '100%', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
              <option value={10}>10</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
          <button 
            onClick={() => setCurrentPage(prev => Math.max(0, prev - 1))} 
            disabled={currentPage === 0 || isLoading}
            style={{ padding: '8px 15px', backgroundColor: currentPage === 0 ? '#333' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: currentPage === 0 ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}>
            &laquo; Prev
          </button>
          <div style={{ padding: '8px 10px', backgroundColor: '#1e1e1e', color: '#aaa', border: '1px solid #444', borderRadius: '4px' }}>
            Page {currentPage + 1}
          </div>
          <button 
            onClick={() => setCurrentPage(prev => prev + 1)} 
            disabled={logs.length < filterLimit || isLoading}
            style={{ padding: '8px 15px', backgroundColor: logs.length < filterLimit ? '#333' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: logs.length < filterLimit ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}>
            Next &raquo;
          </button>
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
            {filteredLogs.length === 0 ? (
              <tr><td colSpan="6" style={{ padding: '30px', textAlign: 'center', color: '#666' }}>No logs found matching these criteria.</td></tr>
            ) : filteredLogs.map((log) => {
              
              let safeDetails = {};
              if (typeof log.details === 'string') {
                try { safeDetails = JSON.parse(log.details); } catch(e) { safeDetails = { raw_string: log.details }; }
              } else if (typeof log.details === 'object' && log.details !== null) {
                safeDetails = log.details;
              }

              // Filter out the strictly tracked keys from the "Additional Metadata" raw JSON block
              const rawPayloadData = Object.fromEntries(
                Object.entries(safeDetails).filter(([k]) => ![
                  'ansible_logs', 'prompt', 'generated_commands', 'action', 'mode', 
                  'execution_status', 'source', 'filename', 'file', 'options', 
                  'saved_to_archive', 'failures', 'source_template', 'template_name', 
                  'category', 'ai_description'
                ].includes(k))
              );

              // Smart Target Parsing
              let safeTargets = "None / System";
              if (Array.isArray(log.target_devices) && log.target_devices.length > 0) {
                safeTargets = log.target_devices.map(d => typeof d === 'object' ? d.hostname : d).join(', ');
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
                      
                      {/* TOP ROW: Action, Mode, Source, Templates & Status Badges */}
                      <div style={{ display: 'flex', gap: '15px', marginBottom: '15px', alignItems: 'center', flexWrap: 'wrap' }}>
                        {safeDetails.action && (
                          <div style={{ fontSize: '1.1rem', fontWeight: 'bold', color: '#e6a23c' }}>
                            Action: {safeDetails.action}
                          </div>
                        )}
                        {safeDetails.mode && (
                          <span style={{ padding: '4px 10px', backgroundColor: '#333', color: '#ccc', borderRadius: '4px', fontSize: '0.85rem', border: '1px solid #555' }}>
                            Mode: {safeDetails.mode}
                          </span>
                        )}
                        {safeDetails.source && (
                          <span style={{ padding: '4px 10px', backgroundColor: '#9c27b022', color: '#9c27b0', borderRadius: '4px', fontSize: '0.85rem', border: '1px solid #9c27b0' }}>
                            Source: {safeDetails.source}
                          </span>
                        )}
                        {/* --- NEW: SOURCE TEMPLATE BADGE --- */}
                        {safeDetails.source_template && (
                          <span style={{ padding: '4px 10px', backgroundColor: '#007acc22', color: '#007acc', borderRadius: '4px', fontSize: '0.85rem', border: '1px solid #007acc' }}>
                            Template Used: {safeDetails.source_template}
                          </span>
                        )}
                        {safeDetails.execution_status && (
                          <span style={{ padding: '4px 10px', backgroundColor: safeDetails.execution_status === 'Success' ? '#4caf5022' : '#f4433622', color: safeDetails.execution_status === 'Success' ? '#4caf50' : '#f44336', borderRadius: '4px', fontSize: '0.85rem', fontWeight: 'bold', border: `1px solid ${safeDetails.execution_status === 'Success' ? '#4caf50' : '#f44336'}` }}>
                            Status: {safeDetails.execution_status}
                          </span>
                        )}
                      </div>

                      {/* TEMPLATE SAVED EVENT BLOCK */}
                      {safeDetails.action === 'Template Saved' && (
                        <div style={{ marginBottom: '20px', color: '#ccc', padding: '15px', backgroundColor: '#1e1e1e', borderRadius: '4px', borderLeft: '4px solid #4caf50' }}>
                          <div style={{ marginBottom: '8px' }}><strong style={{ color: '#aaa' }}>Template Name: </strong> <span style={{ color: '#fff' }}>{safeDetails.template_name}</span></div>
                          <div style={{ marginBottom: '8px' }}><strong style={{ color: '#aaa' }}>Category: </strong> <span style={{ color: '#fff' }}>{safeDetails.category}</span></div>
                          <div><strong style={{ color: '#aaa' }}>AI Description: </strong> <span style={{ color: '#fff', fontStyle: 'italic' }}>"{safeDetails.ai_description}"</span></div>
                        </div>
                      )}

                      {/* MAINTENANCE FILE / OPTIONS BLOCK */}
                      {(safeDetails.filename || safeDetails.file) && safeDetails.action !== 'Template Saved' && (
                        <div style={{ marginBottom: '15px', color: '#ccc', padding: '10px', backgroundColor: '#1e1e1e', borderRadius: '4px', borderLeft: '4px solid #007acc' }}>
                          <strong>Target File: </strong> {safeDetails.filename || safeDetails.file}
                        </div>
                      )}
                      
                      {safeDetails.options && (
                        <div style={{ marginBottom: '20px', display: 'flex', gap: '15px', color: '#aaa', fontSize: '0.9rem' }}>
                          <strong>Backup Options:</strong>
                          <span>NVRAM: {safeDetails.options.save_nvram ? "✅" : "❌"}</span>
                          <span>Flash: {safeDetails.options.save_flash ? "✅" : "❌"}</span>
                          <span>Archive: {safeDetails.options.save_archive ? "✅" : "❌"}</span>
                          <span>Local: {safeDetails.options.download_local ? "✅" : "❌"}</span>
                        </div>
                      )}

                      {/* USER PROMPT BLOCK */}
                      {safeDetails.prompt && (
                        <div style={{ marginBottom: '20px', backgroundColor: '#252526', padding: '15px', borderRadius: '4px', borderLeft: '4px solid #9c27b0' }}>
                          <strong style={{ color: '#aaa', display: 'block', marginBottom: '5px' }}>User Requirement Prompt:</strong>
                          <span style={{ color: '#fff', fontSize: '1rem', fontStyle: 'italic' }}>"{safeDetails.prompt}"</span>
                        </div>
                      )}

                      {/* DATA & LOGS GRID */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
                        
                        {safeDetails.generated_commands && (
                          <div>
                            <strong style={{ color: '#aaa', display: 'block', marginBottom: '5px' }}>AI Generated Configuration (JSON):</strong>
                            <pre style={{ backgroundColor: '#000', padding: '15px', borderRadius: '4px', border: '1px solid #333', color: '#569cd6', overflowX: 'auto', maxHeight: '400px', fontSize: '0.85rem', margin: 0 }}>
                              {safeDetails.generated_commands}
                            </pre>
                          </div>
                        )}

                        {safeDetails.ansible_logs && (
                          <div>
                            <strong style={{ color: '#aaa', display: 'block', marginBottom: '5px' }}>Execution Output Logs:</strong>
                            <pre style={{ backgroundColor: '#000', padding: '15px', borderRadius: '4px', border: '1px solid #333', color: safeDetails.execution_status === 'Failed' || safeDetails.execution_status === 'Partial Failure' ? '#f44336' : '#4caf50', overflowX: 'auto', maxHeight: '400px', fontSize: '0.85rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>
                              {safeDetails.ansible_logs}
                            </pre>
                          </div>
                        )}
                        
                        {/* FALLBACK RAW DATA BLOCK */}
                        {Object.keys(rawPayloadData).length > 0 && (
                          <div>
                            <strong style={{ color: '#aaa', display: 'block', marginBottom: '5px' }}>Additional Metadata:</strong>
                            <pre style={{ backgroundColor: '#000', padding: '15px', borderRadius: '4px', border: '1px solid #333', color: '#ccc', overflowX: 'auto', maxHeight: '400px', fontSize: '0.85rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>
                              {JSON.stringify(rawPayloadData, null, 2)}
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