import React, { useState, useEffect } from 'react';

// --- DYNAMIC API ROUTING ---
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const JOBS_URL = `${API_BASE}/jobs/`;
const TEMPLATES_URL = `${API_BASE}/templates/`;

export default function ScheduledJobs({ devices, userRole }) {
  const [jobs, setJobs] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [isJobsLoading, setIsJobsLoading] = useState(false);
  const [isCreatingJob, setIsCreatingJob] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null); 

  // New Job Form State
  const [schedName, setSchedName] = useState('');
  const [schedType, setSchedType] = useState('backup');
  
  // TIMING STATE
  const [schedTiming, setSchedTiming] = useState('cron'); 
  const [schedInterval, setSchedInterval] = useState(24);
  const [schedCronDays, setSchedCronDays] = useState(['mon', 'tue', 'wed', 'thu', 'fri']); 
  const [schedCronTime, setSchedCronTime] = useState('02:00'); 
  const [schedRunOnceDate, setSchedRunOnceDate] = useState(''); 

  const [schedSwitches, setSchedSwitches] = useState([]);
  const [schedRouters, setSchedRouters] = useState([]);
  const [isSchedSwitchesOpen, setIsSchedSwitchesOpen] = useState(false);
  const [isSchedRoutersOpen, setIsSchedRoutersOpen] = useState(false);
  const [schedSelectedTemplate, setSchedSelectedTemplate] = useState('');

  const fetchJobsAndTemplates = () => {
    setIsJobsLoading(true);
    const headers = { 'Authorization': `Bearer ${localStorage.getItem('token')}` };
    
    Promise.all([
      fetch(JOBS_URL, { headers }).then(res => res.json()),
      fetch(TEMPLATES_URL, { headers }).then(res => res.json())
    ]).then(([jobsData, templatesData]) => {
      setJobs(jobsData);
      setTemplates(templatesData);
      setIsJobsLoading(false);
    }).catch(err => {
      console.error(err);
      setIsJobsLoading(false);
    });
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchJobsAndTemplates();
  }, []);

  const sortTargets = (a, b) => a.hostname.localeCompare(b.hostname, undefined, { numeric: true });
  const allSwitches = devices.filter(d => d.device_type !== 'router');
  const allRouters = devices.filter(d => d.device_type === 'router');
  
  const toggleSelection = (hostname, list, setList) => {
    setList(prev => prev.includes(hostname) ? prev.filter(h => h !== hostname) : [...prev, hostname]);
  };

  const toggleDay = (day) => {
    setSchedCronDays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day]);
  };

  const toggleRow = (id) => {
    setExpandedRow(prev => prev === id ? null : id);
  };

  const handleCreateScheduledJob = (e) => {
    e.preventDefault();
    const targets = [...schedSwitches, ...schedRouters];
    if (targets.length === 0) return alert("Please select target devices.");
    if (schedType === 'template_push' && !schedSelectedTemplate) return alert("Please select a template to push.");
    if (schedTiming === 'cron' && schedCronDays.length === 0) return alert("Please select at least one day of the week.");
    if (schedTiming === 'once' && !schedRunOnceDate) return alert("Please select a date and time.");

    let payload = {};
    if (schedType === 'backup') {
      payload = { save_nvram: false, save_flash: false, save_archive: true };
    } else {
      const template = templates.find(t => t.id.toString() === schedSelectedTemplate);
      payload = { template_id: template.id, template_config: template.payload };
    }

    const [hour, minute] = schedCronTime.split(':');

    const jobData = {
      name: schedName,
      job_type: schedType,
      target_devices: targets,
      job_payload: payload,
      interval_hours: schedTiming === 'interval' ? parseInt(schedInterval) : null,
      cron_day_of_week: schedTiming === 'cron' ? schedCronDays.join(',') : null,
      cron_hour: schedTiming === 'cron' ? hour : null,
      cron_minute: schedTiming === 'cron' ? minute : null,
      run_once_time: schedTiming === 'once' ? new Date(schedRunOnceDate).toISOString() : null
    };

    setIsCreatingJob(true);
    fetch(JOBS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify(jobData)
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      fetchJobsAndTemplates();
      setSchedName(''); setSchedSwitches([]); setSchedRouters([]); setIsCreatingJob(false);
      alert("Job scheduled successfully!");
    })
    .catch(err => { alert(`Failed to schedule: ${err.message}`); setIsCreatingJob(false); });
  };

  const handleToggleJob = (id) => {
    fetch(`${JOBS_URL}${id}/toggle`, { method: 'PUT', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
      .then(() => fetchJobsAndTemplates())
      .catch(() => alert("Failed to toggle job. Ensure you have permissions."));
  };

  const handleDeleteJob = (id) => {
    if (!window.confirm("Are you sure you want to delete this scheduled job?")) return;
    fetch(`${JOBS_URL}${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
      .then(() => fetchJobsAndTemplates())
      .catch(() => alert("Failed to delete job. Ensure you have permissions."));
  };

  const handleRunNow = (id) => {
    if (!window.confirm("Are you sure you want to run this job immediately?")) return;
    fetch(`${JOBS_URL}${id}/run`, { method: 'POST', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
      .then(async res => {
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
        alert("Job launched in the background! Check the Event Logs tab for the results.");
        fetchJobsAndTemplates();
      })
      .catch(err => alert(`Failed to run: ${err.message}`));
  };

  const daysOfWeek = [
    { label: 'Mon', val: 'mon' }, { label: 'Tue', val: 'tue' }, { label: 'Wed', val: 'wed' }, 
    { label: 'Thu', val: 'thu' }, { label: 'Fri', val: 'fri' }, { label: 'Sat', val: 'sat' }, { label: 'Sun', val: 'sun' }
  ];

  return (
    <div>
      {/* Create Job Form */}
      <div style={{ backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333', marginBottom: '30px' }}>
        <h3 style={{ marginTop: 0, color: '#007acc', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Schedule New Task</h3>
        <form onSubmit={handleCreateScheduledJob}>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '20px' }}>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Job Name</label>
              <input required type="text" value={schedName} onChange={e => setSchedName(e.target.value)} placeholder="e.g. Weekly Core Backup" style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
            </div>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Job Type</label>
              <select value={schedType} onChange={e => setSchedType(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="backup">Automated Backup</option>
                {userRole === 'admin' && <option value="template_push">Template Push (Ansible)</option>}
              </select>
            </div>
          </div>

          <div style={{ backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', border: '1px solid #444', marginBottom: '20px' }}>
            <h4 style={{ color: '#fff', margin: '0 0 10px 0', fontSize: '0.9rem' }}>{schedType === 'backup' ? 'Backup Options' : 'Template Selection'}</h4>
            {schedType === 'backup' ? (
              <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
                <label style={{ display: 'flex', alignItems: 'center', cursor: 'not-allowed', fontSize: '0.85rem', color: '#555' }} title="Background jobs cannot download to browser">
                  <input type="checkbox" disabled checked={true} style={{ marginRight: '8px' }} /> Save to Server Archive
                </label>
              </div>
            ) : (
              <select required value={schedSelectedTemplate} onChange={e => setSchedSelectedTemplate(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#252526', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="" disabled>-- Select a Template --</option>
                {templates.map(t => <option key={t.id} value={t.id}>{t.name} ({t.category})</option>)}
              </select>
            )}
          </div>

          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ color: '#fff', marginBottom: '10px', fontSize: '0.9rem' }}>Target Devices</h4>
            <div style={{ display: 'flex', gap: '10px' }}>
              <div style={{ flex: 1, backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: '4px', overflow: 'hidden' }}>
                <div onClick={() => setIsSchedSwitchesOpen(!isSchedSwitchesOpen)} style={{ padding: '10px', backgroundColor: '#2a2a2a', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 'bold' }}>Switches ({schedSwitches.length})</span><span>{isSchedSwitchesOpen ? '▼' : '▶'}</span>
                </div>
                {isSchedSwitchesOpen && (
                  <div style={{ maxHeight: '120px', overflowY: 'auto', padding: '5px' }}>
                    {allSwitches.sort(sortTargets).map(s => (
                      <label key={s.id} style={{ display: 'flex', alignItems: 'center', padding: '4px', cursor: 'pointer' }}><input type="checkbox" checked={schedSwitches.includes(s.hostname)} onChange={() => toggleSelection(s.hostname, schedSwitches, setSchedSwitches)} style={{ marginRight: '8px' }} /><span style={{ fontSize: '0.85rem' }}>{s.hostname}</span></label>
                    ))}
                  </div>
                )}
              </div>
              <div style={{ flex: 1, backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: '4px', overflow: 'hidden' }}>
                <div onClick={() => setIsSchedRoutersOpen(!isSchedRoutersOpen)} style={{ padding: '10px', backgroundColor: '#2a2a2a', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 'bold' }}>Routers ({schedRouters.length})</span><span>{isSchedRoutersOpen ? '▼' : '▶'}</span>
                </div>
                {isSchedRoutersOpen && (
                  <div style={{ maxHeight: '120px', overflowY: 'auto', padding: '5px' }}>
                    {allRouters.sort(sortTargets).map(r => (
                      <label key={r.id} style={{ display: 'flex', alignItems: 'center', padding: '4px', cursor: 'pointer' }}><input type="checkbox" checked={schedRouters.includes(r.hostname)} onChange={() => toggleSelection(r.hostname, schedRouters, setSchedRouters)} style={{ marginRight: '8px' }} /><span style={{ fontSize: '0.85rem' }}>{r.hostname}</span></label>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div style={{ backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', border: '1px solid #444', marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                <h4 style={{ color: '#fff', margin: 0, fontSize: '0.9rem' }}>Schedule Timing</h4>
                <select value={schedTiming} onChange={e => setSchedTiming(e.target.value)} style={{ padding: '8px', backgroundColor: '#252526', color: 'white', border: '1px solid #007acc', borderRadius: '4px', fontWeight: 'bold' }}>
                    <option value="cron">Recurring: Specific Days</option>
                    <option value="interval">Recurring: Every X Hours</option>
                    <option value="once">One-Time: Exact Date</option>
                </select>
            </div>

            <div style={{ padding: '15px', backgroundColor: '#252526', borderRadius: '4px', border: '1px solid #333' }}>
                {schedTiming === 'cron' && (
                    <div style={{ display: 'flex', gap: '20px', alignItems: 'center', flexWrap: 'wrap' }}>
                        <div>
                            <span style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '8px' }}>Select Days</span>
                            <div style={{ display: 'flex', gap: '5px' }}>
                                {daysOfWeek.map(day => (
                                    <button 
                                        key={day.val} 
                                        type="button"
                                        onClick={() => toggleDay(day.val)}
                                        style={{ padding: '8px 12px', borderRadius: '4px', border: '1px solid #555', cursor: 'pointer', fontWeight: 'bold', backgroundColor: schedCronDays.includes(day.val) ? '#007acc' : '#1e1e1e', color: schedCronDays.includes(day.val) ? 'white' : '#aaa' }}
                                    >
                                        {day.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div>
                            <span style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '8px' }}>Select Time</span>
                            <input type="time" value={schedCronTime} onChange={e => setSchedCronTime(e.target.value)} style={{ padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #555', borderRadius: '4px' }} />
                        </div>
                    </div>
                )}

                {schedTiming === 'interval' && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{ color: '#ccc' }}>Repeat execution every</span>
                        <input type="number" min="1" max="720" value={schedInterval} onChange={e => setSchedInterval(e.target.value)} style={{ width: '80px', padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #555', borderRadius: '4px' }} />
                        <span style={{ color: '#ccc' }}>hours</span>
                    </div>
                )}

                {schedTiming === 'once' && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{ color: '#ccc' }}>Execute exactly on:</span>
                        <input type="datetime-local" value={schedRunOnceDate} onChange={e => setSchedRunOnceDate(e.target.value)} style={{ padding: '8px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #555', borderRadius: '4px' }} />
                    </div>
                )}
            </div>
          </div>

          <button type="submit" disabled={isCreatingJob} style={{ padding: '12px 25px', backgroundColor: isCreatingJob ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: isCreatingJob ? 'wait' : 'pointer', fontWeight: 'bold' }}>
            {isCreatingJob ? 'Scheduling...' : 'Launch Scheduled Job'}
          </button>
        </form>
      </div>

      {/* Active Jobs Table */}
      <h3 style={{ color: '#fff', marginBottom: '15px' }}>Active System Tasks</h3>
      <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflow: 'hidden' }}>
        <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
          <thead style={{ backgroundColor: '#333' }}>
            <tr>
              <th style={{ padding: '15px' }}>Job Name</th>
              <th style={{ padding: '15px' }}>Type</th>
              <th style={{ padding: '15px' }}>Schedule</th>
              <th style={{ padding: '15px' }}>Status</th>
              <th style={{ padding: '15px' }}>Author</th>
              <th style={{ padding: '15px', textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isJobsLoading ? <tr><td colSpan="6" style={{ padding: '20px', textAlign: 'center' }}>Loading jobs...</td></tr> : 
             jobs.length === 0 ? <tr><td colSpan="6" style={{ padding: '20px', textAlign: 'center', color: '#888' }}>No scheduled jobs found.</td></tr> : 
             jobs.map(job => {
              const canEdit = userRole === 'admin' || job.created_by === localStorage.getItem('username');
              
              let scheduleText = '';
              if (job.run_once_time) scheduleText = `Once: ${new Date(job.run_once_time).toLocaleString()}`;
              else if (job.interval_hours) scheduleText = `Every ${job.interval_hours} hrs`;
              else scheduleText = `Days: ${job.cron_day_of_week.substring(0, 15)}${job.cron_day_of_week.length > 15 ? '...' : ''} at ${String(job.cron_hour).padStart(2, '0')}:${String(job.cron_minute).padStart(2, '0')}`;

              return (
              <React.Fragment key={job.id}>
                <tr style={{ borderBottom: '1px solid #444', backgroundColor: job.is_active ? 'transparent' : '#2a2a2a' }}>
                  <td style={{ padding: '15px', fontWeight: 'bold', color: job.is_active ? '#fff' : '#666' }}>{job.name}</td>
                  <td style={{ padding: '15px' }}><span style={{ padding: '4px 8px', borderRadius: '4px', backgroundColor: job.job_type === 'backup' ? '#007acc22' : '#9c27b022', color: job.job_type === 'backup' ? '#007acc' : '#007acc', fontSize: '0.8rem', textTransform: 'uppercase' }}>{job.job_type.replace('_', ' ')}</span></td>
                  <td style={{ padding: '15px', color: '#ccc', fontSize: '0.85rem' }}>{scheduleText}</td>
                  <td style={{ padding: '15px', fontSize: '0.85rem', color: job.last_run_status.includes('Success') ? '#4caf50' : job.last_run_status === 'Pending' ? '#aaa' : '#f44336' }}>
                    {job.last_run_status} {job.last_run_time && `(${new Date(job.last_run_time).toLocaleTimeString()})`}
                  </td>
                  <td style={{ padding: '15px', color: '#888' }}>{job.created_by}</td>
                  <td style={{ padding: '15px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    <button onClick={() => toggleRow(job.id)} style={{ padding: '6px 12px', marginRight: '5px', backgroundColor: '#1e1e1e', color: '#007acc', border: '1px solid #007acc', borderRadius: '4px', cursor: 'pointer' }}>
                      {expandedRow === job.id ? 'Close' : 'Details'}
                    </button>
                    <button onClick={() => handleRunNow(job.id)} disabled={!canEdit} style={{ padding: '6px 12px', marginRight: '5px', backgroundColor: canEdit ? '#007acc' : '#333', color: canEdit ? 'white' : '#555', border: 'none', borderRadius: '4px', cursor: canEdit ? 'pointer' : 'not-allowed', fontWeight: 'bold' }}>
                      ▶ Run Now
                    </button>
                    <button onClick={() => handleToggleJob(job.id)} disabled={!canEdit} style={{ padding: '6px 12px', marginRight: '5px', backgroundColor: job.is_active ? '#333' : '#4caf50', color: job.is_active ? '#aaa' : '#fff', border: 'none', borderRadius: '4px', cursor: canEdit ? 'pointer' : 'not-allowed' }}>
                      {job.is_active ? 'Pause' : 'Resume'}
                    </button>
                    <button onClick={() => handleDeleteJob(job.id)} disabled={!canEdit} style={{ padding: '6px 12px', backgroundColor: 'transparent', color: canEdit ? '#f44336' : '#555', border: `1px solid ${canEdit ? '#f44336' : '#555'}`, borderRadius: '4px', cursor: canEdit ? 'pointer' : 'not-allowed' }}>Delete</button>
                  </td>
                </tr>

                {expandedRow === job.id && (
                  <tr style={{ backgroundColor: '#1a1a1a', borderBottom: '2px solid #007acc' }}>
                    <td colSpan="6" style={{ padding: '20px' }}>
                      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                        <div style={{ flex: 1, minWidth: '300px' }}>
                          <strong style={{ color: '#aaa', display: 'block', marginBottom: '8px' }}>Target Devices:</strong>
                          <div style={{ color: '#00ff00', fontFamily: 'monospace', backgroundColor: '#000', padding: '10px', borderRadius: '4px', border: '1px solid #333' }}>
                            {job.target_devices.join(', ')}
                          </div>
                        </div>
                        <div style={{ flex: 2, minWidth: '300px' }}>
                          <strong style={{ color: '#aaa', display: 'block', marginBottom: '8px' }}>Job Execution Payload:</strong>
                          <pre style={{ backgroundColor: '#000', padding: '15px', borderRadius: '4px', border: '1px solid #333', color: '#569cd6', overflowX: 'auto', maxHeight: '200px', fontSize: '0.85rem', margin: 0 }}>
                            {JSON.stringify(job.job_payload, null, 2)}
                          </pre>
                        </div>
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