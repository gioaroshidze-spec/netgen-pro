import React, { useState } from 'react';

export default function Users() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('viewer');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Security Check: Only the default Super Admin can manage users
  const currentUsername = localStorage.getItem('username');
  if (currentUsername !== 'admin') {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#f44336' }}>
        <h2>Access Denied</h2>
        <p>Only the default System Administrator can create new users.</p>
      </div>
    );
  }

  const handleCreateUser = (e) => {
    e.preventDefault();
    setIsSubmitting(true);

    fetch('http://127.0.0.1:8000/auth/users', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}` // <-- THE FIX: Injecting the JWT Token!
      },
      body: JSON.stringify({ username, password, role })
    })
    .then(async res => {
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail);
      }
      return res.json();
    })
    .then(data => {
      alert(data.message);
      setUsername('');
      setPassword('');
      setRole('viewer');
      setIsSubmitting(false);
    })
    .catch(err => {
      alert(`Error: ${err.message}`);
      setIsSubmitting(false);
    });
  };

  return (
    <div style={{ maxWidth: '600px', margin: '0 auto' }}>
      <h2 style={{ marginBottom: '20px' }}>User Access Management</h2>
      
      <div style={{ backgroundColor: '#252526', padding: '25px', borderRadius: '8px', border: '1px solid #333' }}>
        <h3 style={{ marginTop: 0, color: '#007acc', borderBottom: '1px solid #444', paddingBottom: '10px' }}>Create New User</h3>
        
        <form onSubmit={handleCreateUser} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Username</label>
            <input required type="text" value={username} onChange={e => setUsername(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
          </div>
          
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Password</label>
            <input required type="password" value={password} onChange={e => setPassword(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Access Role</label>
            <select value={role} onChange={e => setRole(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
              <option value="viewer">Viewer (Read-Only / Templates / CLI)</option>
              <option value="admin">Administrator (Full Access)</option>
            </select>
          </div>

          <button type="submit" disabled={isSubmitting} style={{ marginTop: '10px', padding: '12px', backgroundColor: isSubmitting ? '#555' : '#4caf50', color: 'white', border: 'none', borderRadius: '4px', cursor: isSubmitting ? 'wait' : 'pointer', fontWeight: 'bold' }}>
            {isSubmitting ? 'Creating...' : '+ Create Account'}
          </button>
        </form>
      </div>
    </div>
  );
}