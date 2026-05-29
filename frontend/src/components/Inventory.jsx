import React, { useState } from 'react';
import SiteManager from './SiteManager';

const API_URL = 'http://127.0.0.1:8000/device/';

export default function Inventory({ devices, fetchNetworkStatus, userRole, orgData, setOrgData }) {
  const [activeView, setActiveView] = useState('devices'); // 'devices' or 'sites'
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingId, setEditingId] = useState(null);
  
  const [formData, setFormData] = useState({
    hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin', floor: 'zone-1'
  });

  const [viewFilter, setViewFilter] = useState('all');

  const handleSubmit = (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    const url = editingId ? `${API_URL}${editingId}` : API_URL;
    const method = editingId ? 'PUT' : 'POST';

    fetch(url, {
      method: method, 
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` }, 
      body: JSON.stringify(formData)
    }).then(async (res) => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin', floor: 'zone-1' });
      setEditingId(null);
      fetchNetworkStatus();
      setIsSubmitting(false);
    }).catch(err => { 
      console.error(err); 
      alert("Failed to save. Check console."); 
      setIsSubmitting(false); 
    });
  };

  const handleDeleteDevice = (id) => {
    if(!window.confirm("Delete this device?")) return;
    fetch(`${API_URL}${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
    .then(() => fetchNetworkStatus());
  };

  const filteredDevices = devices.filter(d => viewFilter === 'all' || d.device_type === viewFilter);
  const sortedDevices = [...filteredDevices].sort((a, b) => a.device_type.localeCompare(b.device_type) || a.hostname.localeCompare(b.hostname));

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
      
      {/* HEADER WITH TOGGLE */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ margin: 0 }}>Inventory Management</h2>
        <div style={{ display: 'flex', gap: '5px', backgroundColor: '#1e1e1e', padding: '4px', borderRadius: '6px', border: '1px solid #333' }}>
          <button onClick={() => setActiveView('devices')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: activeView === 'devices' ? '#007acc' : 'transparent', color: activeView === 'devices' ? 'white' : '#aaa' }}>🖥️ Device Manager</button>
          <button onClick={() => setActiveView('sites')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: activeView === 'sites' ? '#007acc' : 'transparent', color: activeView === 'sites' ? 'white' : '#aaa' }}>🏢 Site Manager</button>
        </div>
      </div>

      {activeView === 'sites' ? (
        <SiteManager orgData={orgData} setOrgData={setOrgData} />
      ) : (
        <>
          {/* DEVICE MANAGER FORM */}
          <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '30px' }}>
            <h3 style={{ marginTop: 0, marginBottom: '15px', color: editingId ? '#e6a23c' : '#fff' }}>{editingId ? `Editing Device: ${formData.hostname}` : 'Add New Device'}</h3>
            <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Hostname</label><input required type="text" value={formData.hostname} onChange={e => setFormData({...formData, hostname: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
              <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>IP Address</label><input required type="text" value={formData.ip_address} onChange={e => setFormData({...formData, ip_address: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
              <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Device Type</label><select value={formData.device_type} onChange={e => setFormData({...formData, device_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="switch">Switch</option><option value="router">Router</option></select></div>
              <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>OS Type</label><select value={formData.os_type} onChange={e => setFormData({...formData, os_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="cisco">Cisco</option><option value="hpe">HPE</option><option value="aruba">Aruba</option><option value="mikrotik">MikroTik</option></select></div>
              
              {/* DYNAMIC ORG DROPDOWN */}
              <div style={{ flex: 1, minWidth: '150px' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Zone Assignment</label>
                <select value={formData.floor} onChange={e => setFormData({...formData, floor: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                  {orgData.map(bldg => (
                    <optgroup key={bldg.id} label={bldg.name}>
                      {bldg.floors.flatMap(floor => floor.zones.map(zone => (
                        <option key={zone.id} value={zone.id}>{floor.name} - {zone.name}</option>
                      )))}
                    </optgroup>
                  ))}
                </select>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                {editingId && <button type="button" onClick={() => { setEditingId(null); setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin', floor: 'zone-1' }) }} style={{ padding: '10px', backgroundColor: '#555', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', height: '39px' }}>Cancel</button>}
                <button type="submit" disabled={isSubmitting || userRole !== 'admin'} style={{ padding: '10px 20px', backgroundColor: (isSubmitting || userRole !== 'admin') ? '#555' : (editingId ? '#e6a23c' : '#007acc'), color: editingId && userRole === 'admin' ? 'black' : 'white', border: 'none', borderRadius: '4px', cursor: (isSubmitting || userRole !== 'admin') ? 'not-allowed' : 'pointer', fontWeight: 'bold', height: '39px' }}>
                  {isSubmitting ? 'Saving...' : (editingId ? 'Update' : '+ Add')}
                </button>
              </div>
            </form>
          </div>
          
          {/* DEVICE TABLE */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '10px', borderBottom: '1px solid #444', paddingBottom: '10px' }}>
            <h3 style={{ margin: 0 }}>Device List</h3>
            <div style={{ display: 'flex', gap: '5px', backgroundColor: '#1e1e1e', padding: '4px', borderRadius: '6px', border: '1px solid #333' }}>
              <button onClick={() => setViewFilter('all')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: viewFilter === 'all' ? '#007acc' : 'transparent', color: viewFilter === 'all' ? 'white' : '#aaa' }}>All</button>
              <button onClick={() => setViewFilter('switch')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: viewFilter === 'switch' ? '#007acc' : 'transparent', color: viewFilter === 'switch' ? 'white' : '#aaa' }}>Switches</button>
              <button onClick={() => setViewFilter('router')} style={{ padding: '6px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: viewFilter === 'router' ? '#007acc' : 'transparent', color: viewFilter === 'router' ? 'white' : '#aaa' }}>Routers</button>
            </div>
          </div>

          <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflow: 'hidden' }}>
            <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
              <thead style={{ backgroundColor: '#333' }}><tr><th style={{ padding: '12px' }}>Hostname</th><th style={{ padding: '12px' }}>IP Address</th><th style={{ padding: '12px' }}>Type</th><th style={{ padding: '12px' }}>Zone ID</th><th style={{ padding: '12px', textAlign: 'center' }}>Actions</th></tr></thead>
              <tbody>
                {sortedDevices.map((device) => (
                  <tr key={device.id} style={{ borderBottom: '1px solid #444' }}>
                    <td style={{ padding: '12px', fontWeight: 'bold' }}>{device.hostname}</td>
                    <td style={{ padding: '12px', fontFamily: 'monospace', color: '#aaa' }}>{device.ip_address}</td>
                    <td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.device_type}</td>
                    <td style={{ padding: '12px', color: '#aaa' }}>{device.floor || 'Unassigned'}</td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <button onClick={() => { setEditingId(device.id); setFormData({ hostname: device.hostname, ip_address: device.ip_address, device_type: device.device_type, os_type: device.os_type || 'cisco', username: device.username || 'admin', floor: device.floor || 'zone-1' }); window.scrollTo({ top: 0, behavior: 'smooth' }) }} disabled={userRole !== 'admin'} style={{ padding: '4px 10px', backgroundColor: userRole === 'admin' ? '#e6a23c22' : '#333', color: userRole === 'admin' ? '#e6a23c' : '#777', border: `1px solid ${userRole === 'admin' ? '#e6a23c' : '#555'}`, borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', marginRight: '5px' }}>Edit</button>
                      <button onClick={() => handleDeleteDevice(device.id)} disabled={userRole !== 'admin'} style={{ padding: '4px 10px', backgroundColor: userRole === 'admin' ? '#f4433622' : '#333', color: userRole === 'admin' ? '#f44336' : '#777', border: `1px solid ${userRole === 'admin' ? '#f44336' : '#555'}`, borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed' }}>Delete</button>
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