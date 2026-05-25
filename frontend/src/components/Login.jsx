import React, { useState } from 'react';

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    // FastAPI's security dependency expects Form Data
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    fetch('http://127.0.0.1:8000/auth/token', {
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
        // Save the JWT token to local storage so it persists on refresh
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('username', username);
        localStorage.setItem('role', data.role);
        onLoginSuccess(); // Unlock the dashboard
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
          <h1 style={{ margin: '0 0 10px 0', color: '#007acc' }}></h1>
          <div style={{ color: '#aaa', fontSize: '0.9rem' }}>Enterprise Orchestration Engine</div>
        </div>

        {error && (
          <div style={{ backgroundColor: '#f4433622', color: '#f44336', padding: '10px', borderRadius: '4px', border: '1px solid #f44336', marginBottom: '20px', textAlign: 'center', fontSize: '0.9rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '8px' }}>Username</label>
            <input 
              type="text" 
              required
              value={username} 
              onChange={(e) => setUsername(e.target.value)} 
              style={{ width: '100%', padding: '12px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', boxSizing: 'border-box' }} 
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '8px' }}>Password</label>
            <input 
              type="password" 
              required
              value={password} 
              onChange={(e) => setPassword(e.target.value)} 
              style={{ width: '100%', padding: '12px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', boxSizing: 'border-box' }} 
            />
          </div>
          
          <button 
            type="submit" 
            disabled={isLoading}
            style={{ padding: '12px', backgroundColor: isLoading ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: isLoading ? 'wait' : 'pointer', fontWeight: 'bold', marginTop: '10px' }}
          >
            {isLoading ? 'Authenticating...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}