import { useState, useEffect, useCallback, useMemo } from 'react';
import ReactFlow, { Background, Controls, MiniMap, applyNodeChanges, applyEdgeChanges, Handle, Position, getBezierPath, EdgeLabelRenderer, BaseEdge } from 'reactflow';
import PropTypes from 'prop-types'; 
import dagre from 'dagre'; 
import 'reactflow/dist/style.css';

// --- CUSTOM NODE: HEALTH HALOS, IMAGES & LIVE TELEMETRY ---
const CustomDeviceNode = ({ data }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [imgError, setImgError] = useState(false); 
  const [telemetry, setTelemetry] = useState({ cpu: 'Fetching...', memory: 'Fetching...', uptime: 'Fetching...' });
  const [hasFetched, setHasFetched] = useState(false);
  
  const isGhost = data.status === 'unmanaged';
  const isOnline = data.status === 'online';
  
  const borderColor = isGhost ? '#555' : (isOnline ? '#4caf50' : '#f44336');
  const glow = isGhost ? 'none' : `0 0 15px ${isOnline ? 'rgba(76, 175, 80, 0.4)' : 'rgba(244, 67, 54, 0.6)'}`;
  
  let iconSrc = '/switch-icon.png';
  if (data.device_type === 'router') iconSrc = '/router-icon.png';
  if (isGhost) iconSrc = ''; 

  const handleMouseEnter = () => {
    setIsHovered(true);
    if (!hasFetched && !isGhost && isOnline && data.full_device) {
      setHasFetched(true); 
      fetch(`http://127.0.0.1:8000/topology/telemetry/${data.full_device.id}`, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
      })
      .then(res => res.ok ? res.json() : null)
      .then(metrics => {
        if (metrics) setTelemetry(metrics);
        else setTelemetry({ cpu: 'Error', memory: 'Error', uptime: 'Error' });
      })
      .catch(() => setTelemetry({ cpu: 'Timeout', memory: 'Timeout', uptime: 'Timeout' }));
    }
  };

  return (
    <div 
      onMouseEnter={handleMouseEnter} 
      onMouseLeave={() => setIsHovered(false)}
      style={{ padding: '15px', borderRadius: '8px', backgroundColor: '#252526', border: `2px solid ${borderColor}`, boxShadow: glow, color: '#fff', textAlign: 'center', minWidth: '130px', position: 'relative', opacity: isGhost ? 0.7 : 1 }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      
      {isHovered && !isGhost && (
        <div style={{ position: 'absolute', top: '-85px', left: '50%', transform: 'translateX(-50%)', backgroundColor: '#1a1a1a', padding: '12px', borderRadius: '6px', zIndex: 10, whiteSpace: 'nowrap', border: '1px solid #444', fontSize: '0.75rem', boxShadow: '0 4px 15px rgba(0,0,0,0.8)', textAlign: 'left' }}>
          <div style={{ color: '#007acc', fontWeight: 'bold', borderBottom: '1px solid #333', paddingBottom: '5px', marginBottom: '8px' }}>Live Telemetry</div>
          <div style={{ marginBottom: '3px' }}><span style={{ color: '#aaa' }}>CPU Load:</span> <span style={{ color: '#fff' }}>{telemetry.cpu}</span></div>
          <div style={{ marginBottom: '3px' }}><span style={{ color: '#aaa' }}>Memory:</span> <span style={{ color: '#fff' }}>{telemetry.memory}</span></div>
          <div><span style={{ color: '#aaa' }}>Uptime:</span> <span style={{ color: '#fff' }}>{telemetry.uptime}</span></div>
        </div>
      )}

      <div style={{ marginBottom: '10px', height: '40px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        {imgError || isGhost ? ( <div style={{ fontSize: '1.5rem', color: isGhost ? '#777' : '#fff' }}>🖧</div> ) : ( <img src={iconSrc} alt={data.device_type} style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain', filter: 'drop-shadow(0px 2px 4px rgba(0,0,0,0.5))' }} onError={() => setImgError(true)} /> )}
      </div>

      <div style={{ fontWeight: 'bold', fontSize: '0.9rem', color: isGhost ? '#aaa' : '#fff' }}>{data.label}</div>
      {data.ip && <div style={{ fontSize: '0.75rem', color: '#aaa', marginTop: '4px', fontFamily: 'monospace' }}>{data.ip}</div>}
      <div style={{ fontSize: '0.65rem', color: isGhost ? '#f44336' : '#888', marginTop: '4px', textTransform: 'uppercase', letterSpacing: '1px' }}>{data.os}</div>
      
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
};
CustomDeviceNode.propTypes = { data: PropTypes.object.isRequired };

// --- DYNAMIC GEOMETRY-AWARE EDGE ---
const CustomEdge = ({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, data }) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
  });

  // Strict X-Axis Anchoring for Left-to-Right Port Labels
  let shouldFlip = false;
  if (sourceX > targetX) {
    shouldFlip = true;
  } else if (sourceX === targetX && sourceY > targetY) {
    shouldFlip = true;
  }

  const displayLabel = shouldFlip 
    ? `${data.target_port} ⟷ ${data.source_port}` 
    : `${data.source_port} ⟷ ${data.target_port}`;

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            background: '#1e1e1e',
            color: '#ccc',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '10px',
            fontWeight: 700,
            fontFamily: 'monospace',
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
        >
          {displayLabel}
        </div>
      </EdgeLabelRenderer>
    </>
  );
};
CustomEdge.propTypes = { id: PropTypes.string, sourceX: PropTypes.number, sourceY: PropTypes.number, targetX: PropTypes.number, targetY: PropTypes.number, sourcePosition: PropTypes.string, targetPosition: PropTypes.string, style: PropTypes.object, markerEnd: PropTypes.string, data: PropTypes.object };

// --- MAIN TOPOLOGY CANVAS ENGINE ---
export default function Topology({ devices, userRole, setActiveTab, fetchNetworkStatus }) {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [isRebooting, setIsRebooting] = useState(false);
  
  // Track which port action is executing
  const [bouncingPort, setBouncingPort] = useState(null);

  const nodeTypes = useMemo(() => ({ customDevice: CustomDeviceNode }), []);
  const edgeTypes = useMemo(() => ({ customEdge: CustomEdge }), []); 

  useEffect(() => {
    fetch('http://127.0.0.1:8000/topology/edges', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    .then(res => res.ok ? res.json() : [])
    .then(edgeData => {
      let savedGhostPositions = {};
      try { savedGhostPositions = JSON.parse(localStorage.getItem('vnms_ghost_positions') || '{}'); } catch (e) { console.error(e); }

      let currentNodes = devices.map((dev, index) => {
        let currentX = dev.pos_x ?? 100;
        let currentY = dev.pos_y ?? 100;
        if (currentX === 100 && currentY === 100) currentX = 100 + (index * 180);

        return {
          id: dev.hostname, 
          type: 'customDevice',
          position: { x: currentX, y: currentY },
          data: { label: dev.hostname, ip: dev.ip_address, status: dev.status, device_type: dev.device_type, os: dev.os_type, full_device: dev },
        };
      });

      const formattedEdges = [];
      let rogueOffset = 0;

      edgeData.forEach(edge => {
        if (!currentNodes.find(n => n.id === edge.target_hostname)) {
          const savedPos = savedGhostPositions[edge.target_hostname];
          let ghostX = savedPos ? savedPos.x : 50 + (rogueOffset * 150);
          let ghostY = savedPos ? savedPos.y : 400; 

          currentNodes.push({
            id: edge.target_hostname,
            type: 'customDevice',
            position: { x: ghostX, y: ghostY }, 
            data: { label: edge.target_hostname, status: 'unmanaged', os: 'Unmanaged / Rogue', full_device: null }
          });
          rogueOffset++;
        }

        formattedEdges.push({
          id: `e-${edge.id}`,
          source: edge.source_hostname,
          target: edge.target_hostname,
          type: 'customEdge', 
          data: {
            source_port: edge.source_port,
            target_port: edge.target_port,
            utilization: edge.current_utilization
          },
          animated: edge.current_utilization > 50,
          style: { 
            stroke: edge.link_type === 'trunk' ? '#007acc' : '#777',
            strokeWidth: edge.link_type === 'trunk' ? 3 : 1.5 
          },
        });
      });

      setNodes(prev => {
        return currentNodes.map(cn => {
          const existing = prev.find(p => p.id === cn.id);
          if (existing) cn.position = existing.position;
          return cn;
        });
      });
      setEdges(formattedEdges);
    })
    .catch(err => console.error("Failed to load edges:", err));
  }, [devices]);

  const onLayout = useCallback(() => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({ rankdir: 'TB', nodesep: 150, ranksep: 200 });

    nodes.forEach((node) => { dagreGraph.setNode(node.id, { width: 160, height: 160 }); });
    edges.forEach((edge) => { dagreGraph.setEdge(edge.source, edge.target); });

    dagre.layout(dagreGraph);

    const layoutedNodes = nodes.map((node) => {
      const nodeWithPosition = dagreGraph.node(node.id);
      return { ...node, position: { x: nodeWithPosition.x - 80, y: nodeWithPosition.y - 80 } };
    });

    setNodes(layoutedNodes);
  }, [nodes, edges]);

  const onNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), []);
  const onEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), []);
  
  const onNodeClick = (event, node) => {
    setSelectedEdge(null);
    if (node.data.status !== 'unmanaged') setSelectedDevice(node.data.full_device);
  };

  const onEdgeClick = (event, edge) => {
    setSelectedDevice(null);
    setSelectedEdge(edge);
  };

  const onPaneClick = () => {
    setSelectedDevice(null);
    setSelectedEdge(null);
  };

  const saveLayout = () => {
    setIsSaving(true);
    const coordinates = [];
    const ghostPositions = {};

    nodes.forEach(n => {
      if (n.data.status === 'unmanaged') {
        ghostPositions[n.id] = { x: n.position.x, y: n.position.y };
      } else {
        const targetDevice = devices.find(d => d.hostname === n.id);
        if (targetDevice) {
          coordinates.push({ id: parseInt(targetDevice.id, 10), pos_x: parseFloat(n.position.x.toFixed(2)), pos_y: parseFloat(n.position.y.toFixed(2)) });
        }
      }
    });

    localStorage.setItem('vnms_ghost_positions', JSON.stringify(ghostPositions));

    fetch('http://127.0.0.1:8000/topology/update-coordinates', {
      method: 'POST', 
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify(coordinates)
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Server rejected coordinate format."); }
      return res.json();
    })
    .then(() => {
      setIsSaving(false);
      alert("✅ Map layout saved successfully!");
      if (fetchNetworkStatus) fetchNetworkStatus();
    })
    .catch(err => { console.error(err); alert(`❌ Failed to save layout: ${err.message}`); setIsSaving(false); });
  };

  const handleDiscovery = () => {
    setIsDiscovering(true);
    fetch(`http://127.0.0.1:8000/topology/discover`, {
      method: 'POST', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    .then(res => res.json())
    .then(() => {
      alert("Discovery Engine launched in the background. Please wait 10-15 seconds and refresh the dashboard.");
      setIsDiscovering(false);
    })
    .catch(() => setIsDiscovering(false));
  };

  const handleReboot = () => {
    if (!selectedDevice || !window.confirm(`⚠️ DANGER: You are about to reboot ${selectedDevice.hostname}. Proceed?`)) return;
    setIsRebooting(true);
    fetch(`http://127.0.0.1:8000/device/${selectedDevice.id}/reboot`, {
      method: 'POST', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    .then(() => { alert("Reboot instruction queued."); setIsRebooting(false); setSelectedDevice(null); })
    .catch(() => setIsRebooting(false));
  };

  // --- PORT ACTIONS HANDLER ---
  const handlePortAction = (hostname, port, action) => {
    let warningMsg = `⚠️ DANGER: You are about to ${action.toUpperCase()} port ${port} on ${hostname}. Proceed?`;
    if (!window.confirm(warningMsg)) return;
    
    const actionKey = `${hostname}-${port}`;
    setBouncingPort(actionKey); 

    fetch('http://127.0.0.1:8000/topology/port-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify({ hostname, port, action })
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Failed to execute port action"); }
      return res.json();
    })
    .then(data => { alert(`✅ ${data.message}`); setBouncingPort(null); })
    .catch(err => { alert(`❌ Error: ${err.message}`); setBouncingPort(null); });
  };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 120px)', position: 'relative', border: '1px solid #333', borderRadius: '8px', overflow: 'hidden' }}>
      <div style={{ flex: 1, backgroundColor: '#1e1e1e' }}>
        <ReactFlow 
          nodes={nodes} edges={edges} 
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} 
          onNodeClick={onNodeClick} onEdgeClick={onEdgeClick} onPaneClick={onPaneClick} 
          nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView attributionPosition="bottom-left"
        >
          <Background color="#333" gap={20} />
          <Controls style={{ backgroundColor: '#252526', fill: '#fff' }} />
          <MiniMap nodeColor="#007acc" maskColor="rgba(0,0,0,0.5)" style={{ backgroundColor: '#252526' }} />
        </ReactFlow>

        <div style={{ position: 'absolute', top: '20px', right: (selectedDevice || selectedEdge) ? '340px' : '20px', transition: 'right 0.3s ease', zIndex: 10, display: 'flex', gap: '10px' }}>
          <button onClick={onLayout} style={{ padding: '10px 20px', backgroundColor: '#e6a23c', color: '#000', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>✨ Auto-Layout</button>
          <button onClick={handleDiscovery} disabled={isDiscovering || userRole !== 'admin'} style={{ padding: '10px 20px', backgroundColor: isDiscovering ? '#555' : '#4caf50', color: 'white', border: 'none', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>{isDiscovering ? 'Scanning...' : '🔍 Run Auto-Discovery'}</button>
          <button onClick={saveLayout} disabled={isSaving || userRole !== 'admin'} style={{ padding: '10px 20px', backgroundColor: isSaving ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>{isSaving ? 'Saving...' : '💾 Save Map Layout'}</button>
        </div>
      </div>

      <div style={{ width: '320px', backgroundColor: '#252526', borderLeft: '1px solid #333', padding: '20px', display: 'flex', flexDirection: 'column', position: 'absolute', right: (selectedDevice || selectedEdge) ? '0' : '-320px', top: 0, bottom: 0, transition: 'right 0.3s ease', boxShadow: '-5px 0 15px rgba(0,0,0,0.5)', overflowY: 'auto' }}>
        
        {/* --- NODE PANEL --- */}
        {selectedDevice && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #444', paddingBottom: '15px', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#fff' }}>{selectedDevice.hostname}</h3>
              <button onClick={() => setSelectedDevice(null)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2rem' }}>✖</button>
            </div>
            <div style={{ marginBottom: '30px' }}>
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>IP Address</div><div style={{ color: '#fff', fontFamily: 'monospace', marginBottom: '15px' }}>{selectedDevice.ip_address}</div>
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>Status</div><div style={{ color: selectedDevice.status === 'online' ? '#4caf50' : '#f44336', fontWeight: 'bold', marginBottom: '15px', textTransform: 'uppercase' }}>{selectedDevice.status}</div>
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>OS Type</div><div style={{ color: '#fff', textTransform: 'capitalize' }}>{selectedDevice.os_type}</div>
            </div>
            <h4 style={{ color: '#888', borderBottom: '1px solid #444', paddingBottom: '5px', marginBottom: '15px' }}>Quick Actions</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <button onClick={() => setActiveTab('Configuration')} style={{ padding: '12px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px', cursor: 'pointer', textAlign: 'left', fontWeight: 'bold' }}>⚡ Push Template</button>
              <button 
                onClick={() => {
                  const popWidth = window.screen.width * 0.5, popHeight = window.screen.height * 0.5;
                  const left = (window.screen.width - popWidth) / 2, top = (window.screen.height - popHeight) / 2;
                  window.open(`/?cli=${selectedDevice.id}`, `cli_${selectedDevice.id}`, `width=${popWidth},height=${popHeight},left=${left},top=${top},resizable=yes,scrollbars=yes`);
                }} 
                style={{ padding: '12px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px', cursor: 'pointer', textAlign: 'left', fontWeight: 'bold' }}
              >
                💻 Open Secure CLI
              </button>
              <button onClick={handleReboot} disabled={isRebooting || userRole !== 'admin'} style={{ padding: '12px', backgroundColor: isRebooting ? '#555' : '#f4433622', color: isRebooting ? '#aaa' : '#f44336', border: `1px solid ${isRebooting ? '#555' : '#f44336'}`, borderRadius: '4px', cursor: (isRebooting || userRole !== 'admin') ? 'not-allowed' : 'pointer', textAlign: 'left', fontWeight: 'bold', marginTop: '20px' }}>{isRebooting ? 'Executing...' : '↻ Safe Reboot'}</button>
            </div>
          </>
        )}

        {/* --- EDGE PANEL --- */}
        {selectedEdge && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #444', paddingBottom: '15px', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#fff' }}>Link Interconnect</h3>
              <button onClick={() => setSelectedEdge(null)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2rem' }}>✖</button>
            </div>

            <div style={{ backgroundColor: '#1a1a1a', padding: '15px', borderRadius: '6px', marginBottom: '30px', border: '1px solid #333' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ textAlign: 'left', maxWidth: '40%' }}>
                  <strong style={{ color: '#007acc', display: 'block', fontSize: '1.1rem', wordBreak: 'break-all' }}>{selectedEdge.source}</strong>
                  <span style={{ fontFamily: 'monospace', color: '#4caf50', fontSize: '0.85rem' }}>{selectedEdge.data?.source_port}</span>
                </div>
                
                <div style={{ flex: 1, borderBottom: '2px dashed #555', margin: '0 10px', position: 'relative', top: '-5px' }}>
                  <span style={{ position: 'absolute', top: '-18px', left: '50%', transform: 'translateX(-50%)', fontSize: '0.75rem', color: '#aaa', whiteSpace: 'nowrap', backgroundColor: '#1a1a1a', padding: '0 5px' }}>
                    {selectedEdge.data?.utilization}% Util
                  </span>
                </div>

                <div style={{ textAlign: 'right', maxWidth: '40%' }}>
                  <strong style={{ color: '#007acc', display: 'block', fontSize: '1.1rem', wordBreak: 'break-all' }}>{selectedEdge.target}</strong>
                  <span style={{ fontFamily: 'monospace', color: '#4caf50', fontSize: '0.85rem' }}>{selectedEdge.data?.target_port}</span>
                </div>
              </div>
            </div>

            {/* DEVICE A (SOURCE) OPERATIONS */}
            <h4 style={{ color: '#888', borderBottom: '1px solid #444', paddingBottom: '5px', marginBottom: '15px' }}>
              Port Ops: {selectedEdge.source}
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '25px' }}>
              <button onClick={() => handlePortAction(selectedEdge.source, selectedEdge.data.source_port, 'shutdown')} disabled={bouncingPort === `${selectedEdge.source}-${selectedEdge.data.source_port}` || userRole !== 'admin'} style={{ padding: '8px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold' }}>🔴 Shut</button>
              <button onClick={() => handlePortAction(selectedEdge.source, selectedEdge.data.source_port, 'no_shutdown')} disabled={bouncingPort === `${selectedEdge.source}-${selectedEdge.data.source_port}` || userRole !== 'admin'} style={{ padding: '8px', backgroundColor: '#4caf5022', color: '#4caf50', border: '1px solid #4caf50', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold' }}>🟢 No Shut</button>
              <button onClick={() => handlePortAction(selectedEdge.source, selectedEdge.data.source_port, 'bounce')} disabled={bouncingPort === `${selectedEdge.source}-${selectedEdge.data.source_port}` || userRole !== 'admin'} style={{ gridColumn: '1 / -1', padding: '8px', backgroundColor: '#1e1e1e', color: '#e6a23c', border: '1px solid #e6a23c', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold' }}>⚡ Bounce Port</button>
              <button 
                onClick={() => {
                  const targetDev = devices.find(d => d.hostname === selectedEdge.source);
                  if(!targetDev) return;
                  const popWidth = window.screen.width * 0.4, popHeight = window.screen.height * 0.6;
                  const left = (window.screen.width - popWidth) / 2, top = (window.screen.height - popHeight) / 2;
                  window.open(`/?pcap=${targetDev.id}&port=${encodeURIComponent(selectedEdge.data.source_port)}`, `pcap_${targetDev.id}`, `width=${popWidth},height=${popHeight},left=${left},top=${top},resizable=yes,scrollbars=yes`);
                }}
                disabled={!devices.find(d => d.hostname === selectedEdge.source)}
                style={{ gridColumn: '1 / -1', padding: '8px', backgroundColor: '#007acc', color: '#fff', border: 'none', borderRadius: '4px', cursor: devices.find(d => d.hostname === selectedEdge.source) ? 'pointer' : 'not-allowed', fontWeight: 'bold', marginTop: '5px' }}
              >🕵️‍♂️ Launch Packet Trace</button>
            </div>

            {/* DEVICE B (TARGET) OPERATIONS */}
            <h4 style={{ color: '#888', borderBottom: '1px solid #444', paddingBottom: '5px', marginBottom: '15px' }}>
              Port Ops: {selectedEdge.target}
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '20px' }}>
              <button onClick={() => handlePortAction(selectedEdge.target, selectedEdge.data.target_port, 'shutdown')} disabled={bouncingPort === `${selectedEdge.target}-${selectedEdge.data.target_port}` || userRole !== 'admin' || !devices.find(d => d.hostname === selectedEdge.target)} style={{ padding: '8px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: (userRole === 'admin' && devices.find(d => d.hostname === selectedEdge.target)) ? 'pointer' : 'not-allowed', fontWeight: 'bold', opacity: !devices.find(d => d.hostname === selectedEdge.target) ? 0.5 : 1 }}>🔴 Shut</button>
              <button onClick={() => handlePortAction(selectedEdge.target, selectedEdge.data.target_port, 'no_shutdown')} disabled={bouncingPort === `${selectedEdge.target}-${selectedEdge.data.target_port}` || userRole !== 'admin' || !devices.find(d => d.hostname === selectedEdge.target)} style={{ padding: '8px', backgroundColor: '#4caf5022', color: '#4caf50', border: '1px solid #4caf50', borderRadius: '4px', cursor: (userRole === 'admin' && devices.find(d => d.hostname === selectedEdge.target)) ? 'pointer' : 'not-allowed', fontWeight: 'bold', opacity: !devices.find(d => d.hostname === selectedEdge.target) ? 0.5 : 1 }}>🟢 No Shut</button>
              <button onClick={() => handlePortAction(selectedEdge.target, selectedEdge.data.target_port, 'bounce')} disabled={bouncingPort === `${selectedEdge.target}-${selectedEdge.data.target_port}` || userRole !== 'admin' || !devices.find(d => d.hostname === selectedEdge.target)} style={{ gridColumn: '1 / -1', padding: '8px', backgroundColor: '#1e1e1e', color: '#e6a23c', border: '1px solid #e6a23c', borderRadius: '4px', cursor: (userRole === 'admin' && devices.find(d => d.hostname === selectedEdge.target)) ? 'pointer' : 'not-allowed', fontWeight: 'bold', opacity: !devices.find(d => d.hostname === selectedEdge.target) ? 0.5 : 1 }}>⚡ Bounce Port</button>
              <button 
                onClick={() => {
                  const targetDev = devices.find(d => d.hostname === selectedEdge.target);
                  if(!targetDev) return;
                  const popWidth = window.screen.width * 0.4, popHeight = window.screen.height * 0.6;
                  const left = (window.screen.width - popWidth) / 2, top = (window.screen.height - popHeight) / 2;
                  window.open(`/?pcap=${targetDev.id}&port=${encodeURIComponent(selectedEdge.data.target_port)}`, `pcap_${targetDev.id}`, `width=${popWidth},height=${popHeight},left=${left},top=${top},resizable=yes,scrollbars=yes`);
                }}
                disabled={!devices.find(d => d.hostname === selectedEdge.target)}
                style={{ gridColumn: '1 / -1', padding: '8px', backgroundColor: '#007acc', color: '#fff', border: 'none', borderRadius: '4px', cursor: devices.find(d => d.hostname === selectedEdge.target) ? 'pointer' : 'not-allowed', fontWeight: 'bold', marginTop: '5px', opacity: !devices.find(d => d.hostname === selectedEdge.target) ? 0.5 : 1 }}
              >🕵️‍♂️ Launch Packet Trace</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
Topology.propTypes = { devices: PropTypes.array.isRequired, userRole: PropTypes.string.isRequired, setActiveTab: PropTypes.func.isRequired, fetchNetworkStatus: PropTypes.func };