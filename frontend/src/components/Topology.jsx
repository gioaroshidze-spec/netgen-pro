import { useState, useEffect, useCallback, useMemo } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  MiniMap, 
  applyNodeChanges, 
  applyEdgeChanges,
  Handle,
  Position
} from 'reactflow';
import PropTypes from 'prop-types'; 
import 'reactflow/dist/style.css';

// --- CUSTOM NODE: HEALTH HALOS, IMAGES & TOOLTIPS ---
const CustomDeviceNode = ({ data }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [imgError, setImgError] = useState(false); 
  
  const isOnline = data.status === 'online';
  const borderColor = isOnline ? '#4caf50' : '#f44336';
  const glow = `0 0 15px ${isOnline ? 'rgba(76, 175, 80, 0.4)' : 'rgba(244, 67, 54, 0.6)'}`;
  const iconSrc = data.device_type === 'router' ? '/router-icon.png' : '/switch-icon.png';

  return (
    <div 
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{ 
        padding: '15px', 
        borderRadius: '8px', 
        backgroundColor: '#252526', 
        border: `2px solid ${borderColor}`,
        boxShadow: glow,
        color: '#fff',
        textAlign: 'center',
        minWidth: '130px',
        position: 'relative'
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      
      {/* HOVER TOOLTIP */}
      {isHovered && (
        <div style={{ 
          position: 'absolute', 
          top: '-75px', 
          left: '50%', 
          transform: 'translateX(-50%)', 
          backgroundColor: '#1a1a1a', 
          padding: '10px', 
          borderRadius: '6px', 
          zIndex: 10, 
          whiteSpace: 'nowrap', 
          border: '1px solid #444', 
          fontSize: '0.75rem', 
          boxShadow: '0 4px 10px rgba(0,0,0,0.5)',
          textAlign: 'left'
        }}>
          <div style={{ color: '#007acc', fontWeight: 'bold', borderBottom: '1px solid #333', paddingBottom: '3px', marginBottom: '5px' }}>Device Telemetry</div>
          <div><span style={{ color: '#aaa' }}>CPU Load:</span> Nominal</div>
          <div><span style={{ color: '#aaa' }}>Memory:</span> 42% Used</div>
          <div><span style={{ color: '#aaa' }}>Uptime:</span> Active</div>
        </div>
      )}

      {/* DEVICE IMAGE */}
      <div style={{ marginBottom: '10px', height: '40px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        {imgError ? (
          <div style={{ fontSize: '1.5rem' }}>🖧</div>
        ) : (
          <img 
            src={iconSrc} 
            alt={data.device_type} 
            style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain', filter: 'drop-shadow(0px 2px 4px rgba(0,0,0,0.5))' }}
            onError={() => setImgError(true)}
          />
        )}
      </div>

      <div style={{ fontWeight: 'bold', fontSize: '0.9rem' }}>{data.label}</div>
      <div style={{ fontSize: '0.75rem', color: '#aaa', marginTop: '4px', fontFamily: 'monospace' }}>{data.ip}</div>
      <div style={{ fontSize: '0.65rem', color: '#888', marginTop: '4px', textTransform: 'uppercase', letterSpacing: '1px' }}>{data.os}</div>
      
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
};

CustomDeviceNode.propTypes = {
  data: PropTypes.shape({
    status: PropTypes.string,
    device_type: PropTypes.string,
    label: PropTypes.string,
    ip: PropTypes.string,
    os: PropTypes.string,
    full_device: PropTypes.object
  }).isRequired
};

// --- MAIN TOPOLOGY CANVAS ENGINE ---
export default function Topology({ devices, userRole, setActiveTab }) {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isRebooting, setIsRebooting] = useState(false);

  const nodeTypes = useMemo(() => ({ customDevice: CustomDeviceNode }), []);

  // --- SAFE LAYOUT SYNCHRONIZER ---
  useEffect(() => {
    setNodes((prevNodes) => {
      return devices.map((dev, index) => {
        const existingNode = prevNodes.find((n) => n.id === dev.id.toString());
        
        let currentX = existingNode ? existingNode.position.x : (dev.pos_x ?? 100);
        let currentY = existingNode ? existingNode.position.y : (dev.pos_y ?? 100);

        if (currentX === 100 && currentY === 100) {
          currentX = 100 + (index * 180);
        }

        return {
          id: dev.id.toString(),
          type: 'customDevice',
          position: { x: currentX, y: currentY },
          data: { 
            label: dev.hostname, 
            ip: dev.ip_address, 
            status: dev.status,
            device_type: dev.device_type,
            os: dev.os_type,
            full_device: dev 
          },
        };
      });
    });

    // Fetch Topology Interconnections
    fetch('http://127.0.0.1:8000/topology/edges', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    .then(res => res.ok ? res.json() : [])
    .then(data => {
      const formattedEdges = data.map(edge => ({
        id: `e-${edge.id}`,
        source: devices.find(d => d.hostname === edge.source_hostname)?.id.toString() || '',
        target: devices.find(d => d.hostname === edge.target_hostname)?.id.toString() || '',
        animated: edge.current_utilization > 50, 
        style: { stroke: edge.current_utilization > 80 ? '#f44336' : '#007acc', strokeWidth: 2 },
      })).filter(e => e.source && e.target); 
      setEdges(formattedEdges);
    })
    .catch(err => console.error("Failed to load edges:", err));

  }, [devices]);

  const onNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );

  const onEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  const onNodeClick = (event, node) => {
    setSelectedDevice(node.data.full_device);
  };

  const onPaneClick = () => {
    setSelectedDevice(null);
  };

  const saveLayout = () => {
    setIsSaving(true);
    const coordinates = nodes.map(n => ({
      id: parseInt(n.id),
      pos_x: n.position.x,
      pos_y: n.position.y
    }));

    fetch('http://127.0.0.1:8000/topology/update-coordinates', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}` 
      },
      body: JSON.stringify(coordinates)
    })
    .then(res => res.json())
    .then(() => {
      setIsSaving(false);
    })
    .catch(err => {
      console.error(err);
      alert("Failed to save layout.");
      setIsSaving(false);
    });
  };

  const handleReboot = () => {
    if (!selectedDevice) return;
    if (!window.confirm(`⚠️ DANGER: You are about to reboot ${selectedDevice.hostname}. This will cause a network interruption. Proceed?`)) return;

    setIsRebooting(true);
    fetch(`http://127.0.0.1:8000/device/${selectedDevice.id}/reboot`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      return res.json();
    })
    .then(data => {
      alert(data.message);
      setIsRebooting(false);
      setSelectedDevice(null);
    })
    .catch(err => {
      alert(`Reboot command failed: ${err.message}`);
      setIsRebooting(false);
    });
  };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 120px)', position: 'relative', border: '1px solid #333', borderRadius: '8px', overflow: 'hidden' }}>
      
      <div style={{ flex: 1, backgroundColor: '#1e1e1e' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          fitView
          attributionPosition="bottom-left"
        >
          <Background color="#333" gap={20} />
          <Controls style={{ backgroundColor: '#252526', fill: '#fff' }} />
          <MiniMap nodeColor="#007acc" maskColor="rgba(0,0,0,0.5)" style={{ backgroundColor: '#252526' }} />
        </ReactFlow>

        <button 
          onClick={saveLayout}
          disabled={isSaving || userRole !== 'admin'}
          style={{ position: 'absolute', top: '20px', right: selectedDevice ? '340px' : '20px', transition: 'right 0.3s ease', zIndex: 10, padding: '10px 20px', backgroundColor: isSaving ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}
          title={userRole !== 'admin' ? "Admins only" : ""}
        >
          {isSaving ? 'Saving...' : '💾 Save Map Layout'}
        </button>
      </div>

      <div style={{ 
        width: '320px', 
        backgroundColor: '#252526', 
        borderLeft: '1px solid #333',
        padding: '20px',
        display: 'flex', 
        flexDirection: 'column',
        position: 'absolute',
        right: selectedDevice ? '0' : '-320px',
        top: 0,
        bottom: 0,
        transition: 'right 0.3s ease',
        boxShadow: '-5px 0 15px rgba(0,0,0,0.5)'
      }}>
        {selectedDevice && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #444', paddingBottom: '15px', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#fff' }}>{selectedDevice.hostname}</h3>
              <button onClick={() => setSelectedDevice(null)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2rem' }}>✖</button>
            </div>

            <div style={{ marginBottom: '30px' }}>
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>IP Address</div>
              <div style={{ color: '#fff', fontFamily: 'monospace', marginBottom: '15px' }}>{selectedDevice.ip_address}</div>
              
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>Status</div>
              <div style={{ color: selectedDevice.status === 'online' ? '#4caf50' : '#f44336', fontWeight: 'bold', marginBottom: '15px', textTransform: 'uppercase' }}>{selectedDevice.status}</div>

              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>OS Type</div>
              <div style={{ color: '#fff', textTransform: 'capitalize' }}>{selectedDevice.os_type}</div>
            </div>

            <h4 style={{ color: '#888', borderBottom: '1px solid #444', paddingBottom: '5px', marginBottom: '15px' }}>Quick Actions</h4>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <button 
                onClick={() => setActiveTab('Configuration')}
                style={{ padding: '12px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px', cursor: 'pointer', textAlign: 'left', fontWeight: 'bold' }}
              >
                ⚡ Push Template
              </button>
              <button 
                onClick={() => setActiveTab('CLI')}
                style={{ padding: '12px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px', cursor: 'pointer', textAlign: 'left', fontWeight: 'bold' }}
              >
                💻 Open Secure CLI
              </button>
              <button 
                onClick={handleReboot}
                disabled={isRebooting || userRole !== 'admin'}
                title={userRole !== 'admin' ? 'Administrator required' : ''}
                style={{ padding: '12px', backgroundColor: isRebooting ? '#555' : '#f4433622', color: isRebooting ? '#aaa' : '#f44336', border: `1px solid ${isRebooting ? '#555' : '#f44336'}`, borderRadius: '4px', cursor: (isRebooting || userRole !== 'admin') ? 'not-allowed' : 'pointer', textAlign: 'left', fontWeight: 'bold', marginTop: '20px' }}
              >
                {isRebooting ? 'Executing...' : '↻ Safe Reboot'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

Topology.propTypes = {
  devices: PropTypes.array.isRequired,
  userRole: PropTypes.string.isRequired,
  setActiveTab: PropTypes.func.isRequired
};