import { useState } from 'react';

const API_URL = 'http://127.0.0.1:8000/device/';

export default function Inventory({ devices, fetchNetworkStatus }) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState({
    hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin'
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    const url = editingId ? `${API_URL}${editingId}` : API_URL;
    const method = editingId ? 'PUT' : 'POST';

    fetch(url, {
      method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData)
    }).then(async (res) => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin' });
      setEditingId(null);
      fetchNetworkStatus();
      setIsSubmitting(false);
    }).catch(err => { 
      console.error(err); 
      alert("Failed to save: Check console for duplicate IP or Hostname."); 
      setIsSubmitting(false); 
    });
  };

  const handleDeleteDevice = (id) => {
    if(!window.confirm("Are you sure you want to delete this device?")) return;
    fetch(`${API_URL}${id}`, { method: 'DELETE' }).then(() => fetchNetworkStatus());
  };

  const allSwitches = devices.filter(d => d.device_type !== 'router');

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <h2>Device Inventory Management</h2>
      <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '30px' }}>
        <h3 style={{ marginTop: 0, marginBottom: '15px', color: editingId ? '#e6a23c' : '#fff' }}>{editingId ? `Editing Device: ${formData.hostname}` : 'Add New Device'}</h3>
        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Hostname</label><input required type="text" value={formData.hostname} onChange={e => setFormData({...formData, hostname: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
          <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>IP Address</label><input required type="text" value={formData.ip_address} onChange={e => setFormData({...formData, ip_address: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
          <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Device Type</label><select value={formData.device_type} onChange={e => setFormData({...formData, device_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="switch">Switch</option><option value="router">Router</option></select></div>
          <div style={{ flex: 1, minWidth: '150px' }}><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>OS Type</label><select value={formData.os_type} onChange={e => setFormData({...formData, os_type: e.target.value})} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="cisco">Cisco</option><option value="hpe">HPE</option><option value="aruba">Aruba</option><option value="mikrotik">MikroTik</option></select></div>
          <div style={{ display: 'flex', gap: '10px' }}>
            {editingId && <button type="button" onClick={() => { setEditingId(null); setFormData({ hostname: '', ip_address: '', device_type: 'switch', os_type: 'cisco', username: 'admin' }) }} style={{ padding: '10px', backgroundColor: '#555', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', height: '39px' }}>Cancel</button>}
            <button type="submit" disabled={isSubmitting} style={{ padding: '10px 20px', backgroundColor: editingId ? '#e6a23c' : '#007acc', color: editingId ? 'black' : 'white', border: 'none', borderRadius: '4px', cursor: isSubmitting ? 'wait' : 'pointer', fontWeight: 'bold', height: '39px' }}>{isSubmitting ? 'Saving...' : (editingId ? 'Update Device' : '+ Add Device')}</button>
          </div>
        </form>
      </div>
      
      <h3 style={{ marginBottom: '10px', borderBottom: '1px solid #444', paddingBottom: '5px' }}>Switch Inventory</h3>
      <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflow: 'hidden', marginBottom: '30px' }}>
        <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
          <thead style={{ backgroundColor: '#333' }}><tr><th style={{ padding: '12px' }}>Hostname</th><th style={{ padding: '12px' }}>IP Address</th><th style={{ padding: '12px' }}>Device Type</th><th style={{ padding: '12px' }}>OS Type</th><th style={{ padding: '12px', textAlign: 'center' }}>Actions</th></tr></thead>
          <tbody>
            {allSwitches.length === 0 ? <tr><td colSpan="5" style={{ padding: '20px', textAlign: 'center', color: '#666' }}>No switches found.</td></tr> : allSwitches.map((device) => (
              <tr key={device.id} style={{ borderBottom: '1px solid #444' }}><td style={{ padding: '12px', fontWeight: 'bold' }}>{device.hostname}</td><td style={{ padding: '12px', fontFamily: 'monospace', color: '#aaa' }}>{device.ip_address}</td><td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.device_type}</td><td style={{ padding: '12px', color: '#aaa', textTransform: 'capitalize' }}>{device.os_type || 'Unknown'}</td><td style={{ padding: '12px', textAlign: 'center' }}><button onClick={() => { setEditingId(device.id); setFormData({ hostname: device.hostname, ip_address: device.ip_address, device_type: device.device_type, os_type: device.os_type || 'cisco', username: device.username || 'admin' }); window.scrollTo({ top: 0, behavior: 'smooth' }) }} style={{ padding: '4px 10px', backgroundColor: '#e6a23c22', color: '#e6a23c', border: '1px solid #e6a23c', borderRadius: '4px', cursor: 'pointer', marginRight: '5px' }}>Edit</button><button onClick={() => handleDeleteDevice(device.id)} style={{ padding: '4px 10px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer' }}>Delete</button></td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}