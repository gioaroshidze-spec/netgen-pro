import React, { useState, useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit'; // Brings in the dynamic resizing engine!
import '@xterm/xterm/css/xterm.css';
import { CanvasAddon } from '@xterm/addon-canvas';

// --- INDIVIDUAL TERMINAL COMPONENT ---
export function TerminalWindow({ device, isActive }) {
  const terminalRef = useRef(null);
  const termInstance = useRef(null);
  const fitAddonInstance = useRef(null);
  const ws = useRef(null);

  useEffect(() => {
    let isMounted = true;

    // Wait for all browser fonts to load BEFORE xterm measures character width
    document.fonts.ready.then(() => {
      if (!isMounted || !terminalRef.current) return;

      // 1. Initialize the terminal
      const term = new Terminal({
        cursorBlink: true,
        theme: { background: '#000000', foreground: '#00ff00' },
        fontFamily: "'Courier New', Courier, monospace",
        fontSize: 14,
      });

      // 2. Load the Fit Addon so it stretches to the container
      const fitAddon = new FitAddon();
      term.loadAddon(fitAddon);

      // FORCE CANVAS RENDERING TO FIX TEXT OVERLAP
      const canvasAddon = new CanvasAddon();
      term.loadAddon(canvasAddon);

      termInstance.current = term;
      fitAddonInstance.current = fitAddon;

      term.open(terminalRef.current);

      // Wait a tiny fraction of a second for the DOM to settle, then fit it!
      setTimeout(() => {
        if (!isMounted) return;
        
        fitAddon.fit();
        term.writeln(`\x1b[36m--- Establishing Secure Connection to ${device.hostname} ---\x1b[0m`);

        // 3. Open the WebSocket to our FastAPI Backend
        const token = localStorage.getItem('token');
        
        // --- DYNAMIC WEBSOCKET ROUTING ---
        const defaultWsBase = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
        const WS_BASE = import.meta.env.VITE_WS_URL || defaultWsBase;
        const socket = new WebSocket(`${WS_BASE}/ws/cli/${device.id}?token=${token}`);
        
        ws.current = socket;

        // 4. Bridge Data
        term.onData((data) => {
          if (socket.readyState === WebSocket.OPEN) socket.send(data);
        });

        socket.onmessage = (event) => term.write(event.data);
        socket.onclose = () => term.writeln('\r\n\x1b[31m--- CONNECTION CLOSED ---\x1b[0m');
        
      }, 50);
    });

    return () => {
          isMounted = false;
          try {
            if (ws.current) {
              ws.current.onmessage = null; // Stop listening to incoming messages
              ws.current.onclose = null;   // Prevent triggering state updates
              if (ws.current.readyState === WebSocket.OPEN) {
                ws.current.close();
              }
            }
            if (termInstance.current) {
              termInstance.current.dispose();
            }
          } catch (err) {
            console.warn("Terminal cleanup sequence aborted:", err);
          }
        };
      }, [device.id, device.hostname]);

  // React to Window Resizing and Tab Switching
  useEffect(() => {
    // When the user switches to this tab, or resizes the browser window, recalculate the terminal size
    const handleResize = () => {
      if (isActive && fitAddonInstance.current) {
        fitAddonInstance.current.fit();
      }
    };

    if (isActive) {
      // Delay slightly to ensure React applied 'display: block' before measuring
      setTimeout(handleResize, 50); 
    }

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [isActive]);

  return (
    <div style={{ display: isActive ? 'block' : 'none', height: '100%', width: '100%', backgroundColor: '#000', padding: '10px', borderRadius: '4px', border: '1px solid #333' }}>
      {/* overflow: hidden ensures the xterm scrollbar doesn't conflict with our container */}
      <div ref={terminalRef} style={{ height: '100%', width: '100%', overflow: 'hidden' }} />
    </div>
  );
}

// --- MAIN CLI DASHBOARD COMPONENT ---
export default function CLI({ devices }) {
  const [search, setSearch] = useState('');
  const [openSessions, setOpenSessions] = useState([]); 
  const [activeTabId, setActiveTabId] = useState(null); 

  const filteredDevices = devices
    .filter(d => d.hostname.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => a.hostname.localeCompare(b.hostname));

  const openTerminal = (device) => {
    if (!openSessions.find(s => s.id === device.id)) {
      setOpenSessions([...openSessions, device]);
    }
    setActiveTabId(device.id);
  };

  const closeTerminal = (e, deviceId) => {
    if (e && e.stopPropagation) e.stopPropagation(); 
    const newSessions = openSessions.filter(s => s.id !== deviceId);
    setOpenSessions(newSessions);
    if (activeTabId === deviceId) {
      setActiveTabId(newSessions.length > 0 ? newSessions[newSessions.length - 1].id : null);
    }
  };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 120px)', gap: '20px', maxWidth: '1600px', margin: '0 auto' }}>
      
      {/* LEFT SIDEBAR */}
      <div style={{ width: '300px', backgroundColor: '#252526', padding: '15px', borderRadius: '8px', border: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
        <h3 style={{ marginTop: 0, borderBottom: '1px solid #444', paddingBottom: '10px' }}>CLI Launcher</h3>
        <input 
          type="text" 
          placeholder="Search devices..." 
          value={search} 
          onChange={(e) => setSearch(e.target.value)} 
          style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px', marginBottom: '15px' }} 
        />
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {filteredDevices.map(device => (
            <div key={device.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e1e1e', padding: '10px', marginBottom: '8px', borderRadius: '4px', border: '1px solid #333' }}>
              <div>
                <div style={{ fontWeight: 'bold', fontSize: '0.9rem' }}>{device.hostname}</div>
                <div style={{ fontSize: '0.8rem', color: '#888' }}>{device.ip_address}</div>
              </div>
              <button 
                onClick={() => openTerminal(device)} 
                style={{ padding: '6px 12px', backgroundColor: openSessions.find(s => s.id === device.id) ? '#333' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
              >
                {openSessions.find(s => s.id === device.id) ? 'Open' : 'Connect'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT SIDE */}
      <div style={{ flex: 1, backgroundColor: '#1e1e1e', borderRadius: '8px', border: '1px solid #333', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        
        {/* TABS BAR */}
        <div style={{ display: 'flex', backgroundColor: '#252526', borderBottom: '1px solid #444', overflowX: 'auto' }}>
          {openSessions.length === 0 && <div style={{ padding: '12px 20px', color: '#888', fontStyle: 'italic' }}>No active CLI sessions.</div>}
          
          {openSessions.map(session => (
            <div 
              key={session.id} 
              onClick={() => setActiveTabId(session.id)}
              style={{ padding: '12px 20px', display: 'flex', alignItems: 'center', gap: '15px', backgroundColor: activeTabId === session.id ? '#1e1e1e' : 'transparent', borderTop: activeTabId === session.id ? '2px solid #007acc' : '2px solid transparent', cursor: 'pointer', borderRight: '1px solid #444' }}
            >
              <span style={{ fontWeight: 'bold', color: activeTabId === session.id ? '#fff' : '#aaa' }}>{session.hostname}</span>
              <button onClick={(e) => closeTerminal(e, session.id)} style={{ background: 'none', border: 'none', color: '#f44336', cursor: 'pointer', fontWeight: 'bold', padding: 0 }}>X</button>
            </div>
          ))}
        </div>

        {/* TERMINAL VIEWPORT */}
        <div style={{ flex: 1, padding: '10px', backgroundColor: '#1e1e1e' }}>
          {openSessions.length === 0 ? (
            <div style={{ height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#555', flexDirection: 'column' }}>
              <div style={{ fontSize: '3rem', marginBottom: '10px' }}>💻</div>
              <h3>Select a device to establish an SSH session</h3>
            </div>
          ) : (
            openSessions.map(session => (
              <TerminalWindow 
                key={session.id} 
                device={session} 
                isActive={activeTabId === session.id} 
              />
            ))
          )}
        </div>

      </div>
    </div>
  );
}