import React, { useState } from 'react';
import SiteManager from './SiteManager'; 

// --- DYNAMIC API ROUTING ---
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const API_URL = `${API_BASE}/device/`;

export default function Inventory({ devices, fetchNetworkStatus, userRole, orgData, fetchOrgData }) {
  const [activeView, setActiveView] = useState('devices'); 
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingId, setEditingId] = useState(null);
  
  const [formData, setFormData] = useState({
    hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin', password: '', zone_id: '', is_legacy: false
  });

  const [viewFilter, setViewFilter] = useState('all');

  const handleSubmit = (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    const url = editingId ? `${API_URL}${editingId}` : API_URL;
    const method = editingId ? 'PUT' : 'POST';

    // Parse empty string to null for Unassigned
    const payload = { ...formData, zone_id: formData.zone_id ? parseInt(formData.zone_id) : null };

    // If we are editing and the password field is empty, remove it from the payload
    // so we don't overwrite the existing encrypted password in the database with a blank string.
    if (editingId && !payload.password) {
      delete payload.password;
    }

    fetch(url, {
      method: method, 
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }, 
      body: JSON.stringify(payload)
    }).then(async (res) => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin', password: '', zone_id: '', is_legacy: false });
      setEditingId(null);
      fetchNetworkStatus();
      setIsSubmitting(false);
    }).catch(err => { 
      console.error(err); 
      alert("Failed to save: Check console for duplicate IP or Hostname or permissions error."); 
      setIsSubmitting(false); 
    });
  };

  const handleDeleteDevice = (id) => {
    if(!window.confirm("Are you sure you want to delete this device?")) return;
    fetch(`${API_URL}${id}`, { 
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    }).then(() => fetchNetworkStatus());
  };

  const filteredDevices = devices.filter(d => {
    if (viewFilter === 'all') return true;
    return d.device_type === viewFilter;
  });

  const sortedDevices = [...filteredDevices].sort((a, b) => 
    a.device_type.localeCompare(b.device_type) || a.hostname.localeCompare(b.hostname)
  );

  const getZoneName = (zoneId) => {
    if (!zoneId) return "Unassigned";
    for (const bldg of orgData) {
      for (const floor of bldg.floors) {
        const found = floor.zones.find(z => z.id === zoneId);
        if (found) return `${floor.name} - ${found.name}`;
      }
    }
    return "Unknown Zone";
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ margin: 0 }}>Inventory Management</h2>
        <div style={{ display: 'flex', gap: '5px', backgroundColor: '#1e1e1e', padding: '4px', borderRadius: '6px', border: '1px solid #333' }}>
          <button onClick={() => setActiveView('devices')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: activeView === 'devices' ? '#007acc' : 'transparent', color: activeView === 'devices' ? 'white' : '#aaa' }}>💻 Device Manager</button>
          <button onClick={() => setActiveView('sites')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: activeView === 'sites' ? '#007acc' : 'transparent', color: activeView === 'sites' ? 'white' : '#aaa' }}>🏢 Site Manager</button>
        </div>
      </div>

      {activeView === 'sites' ? (
        <SiteManager orgData={orgData} fetchOrgData={fetchOrgData} />
      ) : (
        <>
          <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '30px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '15px', color: editingId ? '#e6a23c' : '#fff' }}>{editingId ? `Editing Device: ${formData.hostname}` : 'Add New Device'}</h3>
            <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              
              <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Hostname</label><input required type="text" value={formData.hostname} onChange={e => setFormData({...formData, hostname: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
              <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>IP Address</label><input required type="text" value={formData.ip_address} onChange={e => setFormData({...formData, ip_address: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
              <div style={{ flex: 1, minWidth: '120px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Device Type</label><select value={formData.device_type} onChange={e => setFormData({...formData, device_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="switch">Switch</option><option value="router">Router</option></select></div>
              <div style={{ flex: 1, minWidth: '120px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>OS Type</label><select value={formData.os_type} onChange={e => setFormData({...formData, os_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="cisco">Cisco</option><option value="hpe">HPE</option><option value="aruba">Aruba</option><option value="mikrotik">MikroTik</option><option>Alcatel</option></select></div>
              
              <div style={{ flex: 1, minWidth: '120px' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Username</label>
                <input required type="text" value={formData.username} onChange={e => setFormData({...formData, username: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
              </div>

              <div style={{ flex: 1, minWidth: '150px' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Password</label>
                <input 
                  type="password" 
                  value={formData.password} 
                  onChange={e => setFormData({...formData, password: e.target.value})} 
                  placeholder={editingId ? "(Leave blank to keep)" : "Enter password"} 
                  required={!editingId} 
                  style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} 
                />
              </div>

              <div style={{ flex: 1.5, minWidth: '180px' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Zone Assignment</label>
                <select value={formData.zone_id || ''} onChange={e => setFormData({...formData, zone_id: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                  <option value="">-- Unassigned --</option>
                  {orgData.map(bldg => (
                    <optgroup key={`b-${bldg.id}`} label={`🏢 ${bldg.name}`}>
                      {bldg.floors.map(floor => (
                        floor.zones.map(zone => (
                          <option key={`z-${zone.id}`} value={zone.id}>{floor.name} - {zone.name}</option>
                        ))
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              <div style={{ flex: 1, minWidth: '150px', display: 'flex', alignItems: 'center', paddingBottom: '10px' }}>
                <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', color: formData.is_legacy ? '#e6a23c' : '#aaa', fontSize: '0.85rem', fontWeight: 'bold' }} title="Enable deprecated OpenSSH algorithms for old hardware">
                  <input 
                    type="checkbox" 
                    checked={formData.is_legacy} 
                    onChange={e => setFormData({...formData, is_legacy: e.target.checked})} 
                    style={{ marginRight: '8px', cursor: 'pointer' }} 
                  />
                  ⚠️ Legacy Crypto
                </label>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                {editingId && <button type="button" onClick={() => { setEditingId(null); setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin', password: '', zone_id: '', is_legacy: false }) }} style={{ padding: '10px', backgroundColor: '#555', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', height: '39px' }}>Cancel</button>}
                <button type="submit" disabled={isSubmitting || userRole !== 'admin'} title={userRole !== 'admin' ? "Administrator access required" : ""} style={{ padding: '10px 20px', backgroundColor: (isSubmitting || userRole !== 'admin') ? '#555' : (editingId ? '#e6a23c' : '#007acc'), color: editingId && userRole === 'admin' ? 'black' : 'white', border: 'none', borderRadius: '4px', cursor: (isSubmitting || userRole !== 'admin') ? 'not-allowed' : 'pointer', fontWeight: 'bold', height: '39px' }}>
                  {isSubmitting ? 'Saving...' : (editingId ? 'Update' : '+ Add')}
                </button>
              </div>
            </form>
          </div>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '10px', borderBottom: '1px solid #444', paddingBottom: '10px' }}>
            <h3 style={{ margin: 0 }}>Device List</h3>
            <div style={{ display: 'flex', gap: '5px', backgroundColor: '#1e1e1e', padding: '4px', borderRadius: '6px', border: '1px solid #333' }}>
              <button onClick={() => setViewFilter('all')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: viewFilter === 'all' ? '#007acc' : 'transparent', color: viewFilter === 'all' ? 'white' : '#aaa' }}>All</button>
              <button onClick={() => setViewFilter('switch')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: viewFilter === 'switch' ? '#007acc' : 'transparent', color: viewFilter === 'switch' ? 'white' : '#aaa' }}>Switches</button>
              <button onClick={() => setViewFilter('router')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: viewFilter === 'router' ? '#007acc' : 'transparent', color: viewFilter === 'router' ? 'white' : '#aaa' }}>Routers</button>
            </div>
          </div>

          <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflow: 'hidden', marginBottom: '30px' }}>
            <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
              <thead style={{ backgroundColor: '#333' }}>
                <tr>
                  <th style={{ padding: '12px' }}>Hostname</th>
                  <th style={{ padding: '12px' }}>IP Address</th>
                  <th style={{ padding: '12px' }}>Type</th>
                  <th style={{ padding: '12px' }}>OS Type</th>
                  <th style={{ padding: '12px', textAlign: 'center' }}>Legacy</th>
                  <th style={{ padding: '12px' }}>Zone ID</th>
                  <th style={{ padding: '12px', textAlign: 'center' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedDevices.length === 0 ? <tr><td colSpan="7" style={{ padding: '20px', textAlign: 'center', color: '#666' }}>No devices found in this view.</td></tr> : sortedDevices.map((device) => (
                  <tr key={device.id} style={{ borderBottom: '1px solid #444' }}>
                    <td style={{ padding: '12px', fontWeight: 'bold' }}>{device.hostname}</td>
                    <td style={{ padding: '12px', fontFamily: 'monospace', color: '#aaa' }}>{device.ip_address}</td>
                    <td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.device_type}</td>
                    <td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.os_type || 'Unknown'}</td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      {device.is_legacy ? (
                        <span style={{ padding: '4px 8px', borderRadius: '4px', backgroundColor: '#e6a23c22', color: '#e6a23c', fontSize: '0.8rem', fontWeight: 'bold' }} title="Deprecated SSH algorithms enabled">Yes ⚠️</span>
                      ) : (
                        <span style={{ color: '#555', fontSize: '0.85rem' }}>No</span>
                      )}
                    </td>
                    <td style={{ padding: '12px', color: '#aaa' }}>{getZoneName(device.zone_id)}</td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <button onClick={() => { setEditingId(device.id); setFormData({ hostname: device.hostname, ip_address: device.ip_address, device_type: device.device_type, os_type: device.os_type || 'cisco', username: device.username || 'admin', password: '', zone_id: device.zone_id || '', is_legacy: device.is_legacy || false }); window.scrollTo({ top: 0, behavior: 'smooth' }) }} disabled={userRole !== 'admin'} style={{ padding: '4px 10px', backgroundColor: userRole === 'admin' ? 'transparent' : '#333', color: userRole === 'admin' ? '#e6a23c' : '#777', border: `1px solid ${userRole === 'admin' ? '#e6a23c' : '#555'}`, borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', marginRight: '5px' }}>Edit</button>
                      <button onClick={() => handleDeleteDevice(device.id)} disabled={userRole !== 'admin'} style={{ padding: '4px 10px', backgroundColor: userRole === 'admin' ? 'transparent' : '#333', color: userRole === 'admin' ? '#f44336' : '#777', border: `1px solid ${userRole === 'admin' ? '#f44336' : '#555'}`, borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed' }}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}