import React, { useState } from 'react';

// --- DYNAMIC API ROUTING ---
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const [requiresPasswordChange, setRequiresPasswordChange] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const handleLogin = (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    fetch(`${API_BASE}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData.toString()
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Login failed');
        }
        return res.json();
      })
      .then((data) => {
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('username', username);
        localStorage.setItem('role', data.role);
        
        // --- SECURED: INTERCEPT THE FLAG ---
        if (data.requires_password_change) {
          setRequiresPasswordChange(true);
          setIsLoading(false);
        } else {
          onLoginSuccess(); // Only unlock dashboard if secure
        }
      })
      .catch((err) => {
        setError(err.message);
        setIsLoading(false);
      });
  };

  const handleChangePassword = (e) => {
    e.preventDefault();
    if (newPassword.length < 8) return setError('Password must be at least 8 characters long.');
    if (newPassword !== confirmPassword) return setError('Passwords do not match.');

    setIsLoading(true);
    setError('');

    fetch(`${API_BASE}/auth/change-password`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}` 
      },
      body: JSON.stringify({ old_password: password, new_password: newPassword })
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Password update failed');
        }
        return res.json();
      })
      .then(() => {
        onLoginSuccess();
      })
      .catch((err) => {
        setError(err.message);
        setIsLoading(false);
      });
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', backgroundColor: '#1e1e1e' }}>
      <div style={{ backgroundColor: '#252526', padding: '40px', borderRadius: '8px', border: '1px solid #333', width: '100%', maxWidth: '400px', boxShadow: '0 4px 15px rgba(0,0,0,0.5)' }}>
        
        <div style={{ textAlign: 'center', marginBottom: '30px' }}>
          <h1 style={{ margin: '0 0 10px 0', color: requiresPasswordChange ? '#e6a23c' : '#007acc' }}>VNMS</h1>
          <div style={{ color: '#aaa', fontSize: '0.9rem' }}>
            {requiresPasswordChange ? 'Security Update Required' : 'Enterprise Orchestration Engine'}
          </div>
        </div>

        {error && (
          <div style={{ backgroundColor: '#f4433622', color: '#f44336', padding: '10px', borderRadius: '4px', border: '1px solid #f44336', marginBottom: '20px', textAlign: 'center', fontSize: '0.9rem' }}>
            {error}
          </div>
        )}

        {/* --- DYNAMIC RENDER: LOGIN VS PASSWORD CHANGE --- */}
        {!requiresPasswordChange ? (
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '8px' }}>Username</label>
              <input type="text" required value={username} onChange={(e) => setUsername(e.target.value)} style={{ width: '100%', padding: '12px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', boxSizing: 'border-box' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '8px' }}>Password</label>
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} style={{ width: '100%', padding: '12px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', boxSizing: 'border-box' }} />
            </div>
            <button type="submit" disabled={isLoading} style={{ padding: '12px', backgroundColor: isLoading ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: isLoading ? 'wait' : 'pointer', fontWeight: 'bold', marginTop: '10px' }}>
              {isLoading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleChangePassword} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ color: '#ccc', fontSize: '0.9rem', marginBottom: '10px', textAlign: 'center' }}>
              You are logging in with default credentials. You must set a new secure password before accessing the system.
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '8px' }}>New Password</label>
              <input type="password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} style={{ width: '100%', padding: '12px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #e6a23c', borderRadius: '4px', boxSizing: 'border-box' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '8px' }}>Confirm New Password</label>
              <input type="password" required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} style={{ width: '100%', padding: '12px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #e6a23c', borderRadius: '4px', boxSizing: 'border-box' }} />
            </div>
            <button type="submit" disabled={isLoading} style={{ padding: '12px', backgroundColor: isLoading ? '#555' : '#e6a23c', color: 'black', border: 'none', borderRadius: '4px', cursor: isLoading ? 'wait' : 'pointer', fontWeight: 'bold', marginTop: '10px' }}>
              {isLoading ? 'Updating...' : 'Secure Account'}
            </button>
          </form>
        )}

      </div>
    </div>
  );
}