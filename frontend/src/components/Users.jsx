import React, { useState, useEffect } from 'react';

// --- DYNAMIC API ROUTING ---
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export default function Users() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('viewer');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [resetUserId, setResetUserId] = useState(null);
  const [newPassword, setNewPassword] = useState('');

  const currentUsername = localStorage.getItem('username');
  const token = localStorage.getItem('token');

  const fetchUsers = () => {
    setIsLoading(true);
    fetch(`${API_BASE}/auth/users`, { headers: { 'Authorization': `Bearer ${token}` } })
      .then(res => res.json())
      .then(data => { setUsers(data); setIsLoading(false); })
      .catch(err => { console.error(err); setIsLoading(false); });
  };

  useEffect(() => {
    if (currentUsername === 'admin') fetchUsers();
  }, [currentUsername]);

  if (currentUsername !== 'admin') {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#f44336' }}>
        <h2>Access Denied</h2><p>Only the default System Administrator can manage users.</p>
      </div>
    );
  }

  const handleCreateUser = (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    fetch(`${API_BASE}/auth/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ username, password, role })
    })
    .then(async res => { if (!res.ok) throw new Error((await res.json()).detail); return res.json(); })
    .then(data => { alert(data.message); setUsername(''); setPassword(''); setRole('viewer'); setIsSubmitting(false); fetchUsers(); })
    .catch(err => { alert(`Error: ${err.message}`); setIsSubmitting(false); });
  };

  const handleDeleteUser = (id) => {
    if (!window.confirm("Delete this user permanently?")) return;
    fetch(`${API_BASE}/auth/users/${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } })
      .then(() => fetchUsers())
      .catch(err => alert("Failed to delete user."));
  };

  const handleResetPassword = (e, id) => {
    e.preventDefault();
    fetch(`${API_BASE}/auth/users/${id}/password`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ new_password: newPassword })
    })
    .then(() => { alert("Password reset. User will be forced to change it on their next login."); setResetUserId(null); setNewPassword(''); fetchUsers(); })
    .catch(err => alert("Failed to reset password."));
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', display: 'flex', gap: '30px', alignItems: 'flex-start' }}>
      {/* Create User Panel */}
      <div style={{ flex: 1, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
        <h3 style={{ marginTop: 0, color: '#007acc', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Create New User</h3>
        <form onSubmit={handleCreateUser} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          <div><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Username</label><input required type="text" value={username} onChange={e => setUsername(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
          <div><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Temporary Password</label><input required type="password" value={password} onChange={e => setPassword(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} /></div>
          <div><label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Access Role</label><select value={role} onChange={e => setRole(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}><option value="viewer">Viewer (Read-Only / Templates)</option><option value="admin">Administrator (Full Access)</option></select></div>
          <button type="submit" disabled={isSubmitting} style={{ marginTop: '10px', padding: '12px', backgroundColor: isSubmitting ? '#555' : '#4caf50', color: 'white', border: 'none', borderRadius: '4px', cursor: isSubmitting ? 'wait' : 'pointer', fontWeight: 'bold' }}>{isSubmitting ? 'Creating...' : '+ Create Account'}</button>
        </form>
      </div>

      {/* Users List Panel */}
      <div style={{ flex: 1.5, backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
        <h3 style={{ marginTop: 0, color: '#e6a23c', borderBottom: '1px solid #444', paddingBottom: '10px' }}>System Accounts</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {isLoading ? <div style={{ color: '#888' }}>Loading users...</div> : users.map(u => (
            <div key={u.id} style={{ backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: '6px', padding: '15px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <strong style={{ fontSize: '1.1rem', color: '#fff' }}>{u.username}</strong>
                  <span style={{ marginLeft: '10px', padding: '2px 8px', borderRadius: '4px', backgroundColor: u.role === 'admin' ? '#4caf5022' : '#007acc22', color: u.role === 'admin' ? '#4caf50' : '#007acc', fontSize: '0.8rem', textTransform: 'uppercase' }}>{u.role}</span>
                  {u.requires_password_change && <span style={{ marginLeft: '10px', fontSize: '0.8rem', color: '#f44336' }}>⚠️ Pending Pwd Reset</span>}
                </div>
                {u.username !== 'admin' && (
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <button onClick={() => setResetUserId(resetUserId === u.id ? null : u.id)} style={{ padding: '6px 12px', backgroundColor: '#333', color: '#fff', border: '1px solid #555', borderRadius: '4px', cursor: 'pointer' }}>Reset Pwd</button>
                    <button onClick={() => handleDeleteUser(u.id)} style={{ padding: '6px 12px', backgroundColor: 'transparent', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer' }}>Delete</button>
                  </div>
                )}
              </div>
              
              {resetUserId === u.id && (
                <form onSubmit={(e) => handleResetPassword(e, u.id)} style={{ marginTop: '15px', paddingTop: '15px', borderTop: '1px dashed #444', display: 'flex', gap: '10px' }}>
                  <input required type="password" placeholder="New Password" value={newPassword} onChange={e => setNewPassword(e.target.value)} style={{ flex: 1, padding: '8px', backgroundColor: '#000', color: 'white', border: '1px solid #007acc', borderRadius: '4px' }} />
                  <button type="submit" style={{ padding: '8px 15px', backgroundColor: '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>Update</button>
                </form>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}