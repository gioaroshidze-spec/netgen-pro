import React, { useState, useEffect } from 'react';

export default function SiteManager({ orgData, fetchOrgData }) {
  const [selectedBldg, setSelectedBldg] = useState(null);
  const [selectedFloor, setSelectedFloor] = useState(null);

  const [newBldgName, setNewBldgName] = useState('');
  const [newFloorName, setNewFloorName] = useState('');
  const [newZoneName, setNewZoneName] = useState('');

  const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` };

  // --- THE FIX: AUTO-SYNC UI WHEN DATABASE CHANGES ---
  useEffect(() => {
    if (selectedBldg) {
      const updatedBldg = orgData.find(b => b.id === selectedBldg.id);
      setSelectedBldg(updatedBldg || null);
    }
    if (selectedFloor) {
      let foundFloor = null;
      orgData.forEach(b => {
        const f = b.floors.find(fl => fl.id === selectedFloor.id);
        if (f) foundFloor = f;
      });
      setSelectedFloor(foundFloor || null);
    }
  }, [orgData]);

  const addBuilding = () => {
    if (!newBldgName) return;
    fetch('http://127.0.0.1:8000/organization/building', { method: 'POST', headers, body: JSON.stringify({ name: newBldgName }) })
    .then(() => { setNewBldgName(''); fetchOrgData(); });
  };

  const addFloor = () => {
    if (!newFloorName || !selectedBldg) return;
    fetch('http://127.0.0.1:8000/organization/floor', { method: 'POST', headers, body: JSON.stringify({ name: newFloorName, building_id: selectedBldg.id }) })
    .then(() => { setNewFloorName(''); fetchOrgData(); });
  };

  const addZone = () => {
    if (!newZoneName || !selectedFloor) return;
    fetch('http://127.0.0.1:8000/organization/zone', { method: 'POST', headers, body: JSON.stringify({ name: newZoneName, floor_id: selectedFloor.id }) })
    .then(() => { setNewZoneName(''); fetchOrgData(); });
  };

  const deleteBuilding = (id) => {
    if(!window.confirm("Delete this building and all its contents?")) return;
    fetch(`http://127.0.0.1:8000/organization/building/${id}`, { method: 'DELETE', headers })
    .then(() => { if (selectedBldg?.id === id) { setSelectedBldg(null); setSelectedFloor(null); } fetchOrgData(); });
  };

  const deleteFloor = (id) => {
    fetch(`http://127.0.0.1:8000/organization/floor/${id}`, { method: 'DELETE', headers })
    .then(() => { if (selectedFloor?.id === id) setSelectedFloor(null); fetchOrgData(); });
  };

  const deleteZone = (id) => {
    fetch(`http://127.0.0.1:8000/organization/zone/${id}`, { method: 'DELETE', headers })
    .then(() => fetchOrgData());
  };

  return (
    <div style={{ display: 'flex', gap: '20px', height: '600px' }}>
      {/* BUILDINGS COLUMN */}
      <div style={{ flex: 1, backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
        <h3 style={{ margin: 0, padding: '15px', backgroundColor: '#1e1e1e', borderBottom: '1px solid #444', color: '#007acc' }}>🏢 Buildings</h3>
        <div style={{ padding: '15px', borderBottom: '1px solid #444', display: 'flex', gap: '5px' }}>
          <input type="text" placeholder="New Building..." value={newBldgName} onChange={e=>setNewBldgName(e.target.value)} style={{ flex: 1, padding: '8px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #555', borderRadius: '4px' }} />
          <button onClick={addBuilding} style={{ padding: '8px 15px', backgroundColor: '#007acc', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>+</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '10px' }}>
          {orgData.map(b => (
            <div key={b.id} onClick={() => { setSelectedBldg(b); setSelectedFloor(null); }} style={{ padding: '12px', backgroundColor: selectedBldg?.id === b.id ? '#007acc33' : '#1e1e1e', border: selectedBldg?.id === b.id ? '1px solid #007acc' : '1px solid #333', borderRadius: '4px', marginBottom: '8px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 'bold', color: selectedBldg?.id === b.id ? '#fff' : '#aaa' }}>{b.name}</span>
              <button onClick={(e) => { e.stopPropagation(); deleteBuilding(b.id); }} style={{ background: 'none', border: 'none', color: '#f44336', cursor: 'pointer' }}>✖</button>
            </div>
          ))}
        </div>
      </div>

      {/* FLOORS COLUMN */}
      <div style={{ flex: 1, backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', display: 'flex', flexDirection: 'column', opacity: selectedBldg ? 1 : 0.5, pointerEvents: selectedBldg ? 'auto' : 'none' }}>
        <h3 style={{ margin: 0, padding: '15px', backgroundColor: '#1e1e1e', borderBottom: '1px solid #444', color: '#e6a23c' }}>📂 Floors</h3>
        <div style={{ padding: '15px', borderBottom: '1px solid #444', display: 'flex', gap: '5px' }}>
          <input type="text" placeholder="New Floor..." value={newFloorName} onChange={e=>setNewFloorName(e.target.value)} style={{ flex: 1, padding: '8px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #555', borderRadius: '4px' }} />
          <button onClick={addFloor} style={{ padding: '8px 15px', backgroundColor: '#e6a23c', color: '#000', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>+</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '10px' }}>
          {selectedBldg && selectedBldg.floors.map(f => (
            <div key={f.id} onClick={() => setSelectedFloor(f)} style={{ padding: '12px', backgroundColor: selectedFloor?.id === f.id ? '#e6a23c33' : '#1e1e1e', border: selectedFloor?.id === f.id ? '1px solid #e6a23c' : '1px solid #333', borderRadius: '4px', marginBottom: '8px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 'bold', color: selectedFloor?.id === f.id ? '#fff' : '#aaa' }}>{f.name}</span>
              <button onClick={(e) => { e.stopPropagation(); deleteFloor(f.id); }} style={{ background: 'none', border: 'none', color: '#f44336', cursor: 'pointer' }}>✖</button>
            </div>
          ))}
        </div>
      </div>

      {/* ZONES COLUMN */}
      <div style={{ flex: 1, backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', display: 'flex', flexDirection: 'column', opacity: selectedFloor ? 1 : 0.5, pointerEvents: selectedFloor ? 'auto' : 'none' }}>
        <h3 style={{ margin: 0, padding: '15px', backgroundColor: '#1e1e1e', borderBottom: '1px solid #444', color: '#4caf50' }}>📍 Zones</h3>
        <div style={{ padding: '15px', borderBottom: '1px solid #444', display: 'flex', gap: '5px' }}>
          <input type="text" placeholder="New Zone..." value={newZoneName} onChange={e=>setNewZoneName(e.target.value)} style={{ flex: 1, padding: '8px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #555', borderRadius: '4px' }} />
          <button onClick={addZone} style={{ padding: '8px 15px', backgroundColor: '#4caf50', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>+</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '10px' }}>
          {selectedFloor && selectedFloor.zones.map(z => (
            <div key={z.id} style={{ padding: '12px', backgroundColor: '#1e1e1e', border: '1px solid #333', borderRadius: '4px', marginBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: '#ccc' }}>{z.name}</span>
              <button onClick={() => deleteZone(z.id)} style={{ background: 'none', border: 'none', color: '#f44336', cursor: 'pointer' }}>✖</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}