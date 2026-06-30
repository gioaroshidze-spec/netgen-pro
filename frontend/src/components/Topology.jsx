import { useState, useEffect, useCallback, useMemo } from 'react';
import ReactFlow, { Background, Controls, MiniMap, applyNodeChanges, applyEdgeChanges, Handle, Position, getBezierPath, EdgeLabelRenderer, BaseEdge } from 'reactflow';
import PropTypes from 'prop-types'; 
import dagre from 'dagre'; 
import { NodeResizer } from '@reactflow/node-resizer';
import '@reactflow/node-resizer/dist/style.css';
import 'reactflow/dist/style.css';

const CustomDeviceNode = ({ data }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [imgError, setImgError] = useState(false); 
  const [telemetry, setTelemetry] = useState({ cpu: 'Fetching...', memory: 'Fetching...', uptime: 'Fetching...' });
  const [hasFetched, setHasFetched] = useState(false);
  
  const isGhost = data.status === 'unmanaged';
  const isOnline = data.status === 'online';
  const borderColor = isGhost ? '#555' : (isOnline ? '#4caf50' : '#f44336');
  const glow = isGhost ? 'none' : `0 0 15px ${isOnline ? 'rgba(76, 175, 80, 0.4)' : 'rgba(244, 67, 54, 0.6)'}`;
  let iconSrc = data.device_type === 'router' ? '/router-icon.png' : '/switch-icon.png';
  if (isGhost) iconSrc = ''; 

  const handleMouseEnter = () => {
    setIsHovered(true);
    if (!hasFetched && !isGhost && isOnline && data.full_device) {
      setHasFetched(true); 
      fetch(`http://127.0.0.1:8000/topology/telemetry/${data.full_device.id}`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
      .then(res => res.ok ? res.json() : null)
      .then(metrics => { if (metrics) setTelemetry(metrics); else setTelemetry({ cpu: 'Error', memory: 'Error', uptime: 'Error' }); })
      .catch(() => setTelemetry({ cpu: 'Timeout', memory: 'Timeout', uptime: 'Timeout' }));
    }
  };

  return (
    <div onMouseEnter={handleMouseEnter} onMouseLeave={() => setIsHovered(false)} style={{ padding: '15px', borderRadius: '8px', backgroundColor: '#252526', border: `2px solid ${borderColor}`, boxShadow: glow, color: '#fff', textAlign: 'center', minWidth: '130px', position: 'relative', opacity: isGhost ? 0.7 : 1 }}>
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      {!isGhost && isOnline && data.latency && (<div style={{ position: 'absolute', top: '-10px', right: '-10px', backgroundColor: '#1e1e1e', border: `1px solid ${borderColor}`, color: borderColor, padding: '2px 8px', borderRadius: '12px', fontSize: '0.65rem', fontWeight: 'bold', boxShadow: '0 2px 5px rgba(0,0,0,0.5)', zIndex: 5 }}>{data.latency}</div>)}
      {isHovered && !isGhost && (
        <div style={{ position: 'absolute', top: '-85px', left: '50%', transform: 'translateX(-50%)', backgroundColor: '#1a1a1a', padding: '12px', borderRadius: '6px', zIndex: 10, whiteSpace: 'nowrap', border: '1px solid #444', fontSize: '0.75rem', boxShadow: '0 4px 15px rgba(0,0,0,0.8)', textAlign: 'left' }}>
          <div style={{ color: '#007acc', fontWeight: 'bold', borderBottom: '1px solid #333', paddingBottom: '5px', marginBottom: '8px' }}>Live Telemetry</div>
          <div style={{ marginBottom: '3px' }}><span style={{ color: '#aaa' }}>CPU Load:</span> <span style={{ color: '#fff' }}>{telemetry.cpu}</span></div>
          <div style={{ marginBottom: '3px' }}><span style={{ color: '#aaa' }}>Memory:</span> <span style={{ color: '#fff' }}>{telemetry.memory}</span></div>
          <div><span style={{ color: '#aaa' }}>Uptime:</span> <span style={{ color: '#fff' }}>{telemetry.uptime}</span></div>
        </div>
      )}
      <div style={{ marginBottom: '10px', height: '40px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        {imgError || isGhost ? ( <div style={{ fontSize: '1.5rem', color: isGhost ? '#777' : '#fff' }}>🖧</div> ) : ( <img src={iconSrc} alt={data.device_type} style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }} onError={() => setImgError(true)} /> )}
      </div>
      <div style={{ fontWeight: 'bold', fontSize: '0.9rem', color: isGhost ? '#aaa' : '#fff' }}>{data.label}</div>
      {data.ip && <div style={{ fontSize: '0.75rem', color: '#aaa', marginTop: '4px', fontFamily: 'monospace' }}>{data.ip}</div>}
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
};
CustomDeviceNode.propTypes = { data: PropTypes.object.isRequired };

const CustomZoneNode = ({ data, selected }) => {
  return (
    <>
      <NodeResizer color="#007acc" isVisible={selected} minWidth={300} minHeight={300} />
      <div style={{ width: '100%', height: '100%', backgroundColor: 'rgba(255, 255, 255, 0.02)', border: selected ? '2px dashed #007acc' : '2px dashed #444', borderRadius: '12px' }}>
        <div style={{ padding: '15px', color: '#aaa', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '2px', fontSize: '1.2rem' }}>{data.label}</div>
      </div>
    </>
  );
};

const CustomEdge = ({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, data }) => {
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  let shouldFlip = (sourceX > targetX) || (sourceX === targetX && sourceY > targetY);
  const displayLabel = shouldFlip ? `${data.target_port} ⟷ ${data.source_port}` : `${data.source_port} ⟷ ${data.target_port}`;
  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      <EdgeLabelRenderer>
        <div style={{ position: 'absolute', transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`, background: '#1e1e1e', color: '#ccc', padding: '2px 6px', borderRadius: '4px', fontSize: '10px', fontWeight: 700, fontFamily: 'monospace', pointerEvents: 'all' }} className="nodrag nopan">{displayLabel}</div>
      </EdgeLabelRenderer>
    </>
  );
};
CustomEdge.propTypes = { id: PropTypes.string, sourceX: PropTypes.number, sourceY: PropTypes.number, targetX: PropTypes.number, targetY: PropTypes.number, sourcePosition: PropTypes.string, targetPosition: PropTypes.string, style: PropTypes.object, markerEnd: PropTypes.string, data: PropTypes.object };


export default function Topology({ devices, userRole, setActiveTab, fetchNetworkStatus, orgData }) {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [isRebooting, setIsRebooting] = useState(false);
  const [bouncingPort, setBouncingPort] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(false)

  const [showOrgSidebar, setShowOrgSidebar] = useState(true);
  
  const [savedViews, setSavedViews] = useState([]);
  const [activeView, setActiveView] = useState(null);
  const [newViewName, setNewViewName] = useState('');
  const [selectedZones, setSelectedZones] = useState([]); 

  const nodeTypes = useMemo(() => ({ customDevice: CustomDeviceNode, customZone: CustomZoneNode }), []);
  const edgeTypes = useMemo(() => ({ customEdge: CustomEdge }), []); 

  useEffect(() => {
    if (orgData.length > 0 && selectedZones.length === 0 && !activeView) {
      const allZones = orgData.flatMap(b => b.floors.flatMap(f => f.zones.map(z => z.id)));
      setSelectedZones([...allZones, -1]); 
    }
  }, [orgData, selectedZones.length, activeView]);

  useEffect(() => {
    fetch('http://127.0.0.1:8000/topology/views', { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
    .then(res => res.ok ? res.json() : [])
    .then(data => setSavedViews(data))
    .catch(err => console.error("Failed to load views:", err));
  }, []);

  const handleZoneToggle = (zoneId) => {
    setActiveView(null); 
    setSelectedZones(prev => prev.includes(zoneId) ? prev.filter(z => z !== zoneId) : [...prev, zoneId]);
  };

  const onConnect = useCallback((params) => {
    if (userRole !== 'admin') return alert("Only admins can map manual links.");
    
    const sourcePort = window.prompt(`Enter the outbound port for ${params.source} (e.g., Gig1/0/2):`);
    if (!sourcePort) return;
    const targetPort = window.prompt(`Enter the inbound port for ${params.target} (e.g., ether1):`);
    if (!targetPort) return;
    
    fetch('http://127.0.0.1:8000/topology/edges/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify({
        source_hostname: params.source,
        target_hostname: params.target,
        source_port: sourcePort,
        target_port: targetPort
      })
    })
    .then(async res => {
      if(!res.ok) throw new Error("Failed to add manual link");
      setRefreshTrigger(prev => !prev); 
    })
    .catch(err => alert(err.message));
  }, [userRole]);

  const handleDeleteManualEdge = (edgeId) => {
    if(!window.confirm("Delete this manual link?")) return;
    fetch(`http://127.0.0.1:8000/topology/edges/${edgeId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    .then(() => {
      setSelectedEdge(null);
      setRefreshTrigger(prev => !prev);
    });
  };

  const handleFloorToggle = (floor) => {
    setActiveView(null);
    const floorZoneIds = floor.zones.map(z => z.id);
    const allChecked = floorZoneIds.every(id => selectedZones.includes(id));
    if (allChecked) { setSelectedZones(prev => prev.filter(id => !floorZoneIds.includes(id))); } 
    else { setSelectedZones(prev => [...new Set([...prev, ...floorZoneIds])]); }
  };

  const handleBuildingToggle = (bldg) => {
    setActiveView(null);
    const bldgZoneIds = bldg.floors.flatMap(f => f.zones.map(z => z.id));
    const allChecked = bldgZoneIds.every(id => selectedZones.includes(id));
    if (allChecked) { setSelectedZones(prev => prev.filter(id => !bldgZoneIds.includes(id))); } 
    else { setSelectedZones(prev => [...new Set([...prev, ...bldgZoneIds])]); }
  };

  const handleSaveView = () => {
    if (!newViewName) return alert("Please enter a name for your view.");
    const currentCoords = {};
    nodes.forEach(n => {
      if (n.type === 'customDevice') currentCoords[n.id] = { x: n.position.x, y: n.position.y };
      else if (n.type === 'customZone') currentCoords[n.id] = { x: n.position.x, y: n.position.y, width: n.width || n.style?.width, height: n.height || n.style?.height };
    });

    fetch('http://127.0.0.1:8000/topology/views', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      body: JSON.stringify({ name: newViewName, zone_ids: selectedZones, coordinates: currentCoords })
    })
    .then(async res => { if (!res.ok) throw new Error(await res.text()); return res.json(); })
    .then(newView => { setSavedViews([...savedViews, newView]); setNewViewName(''); setActiveView(newView); })
    .catch(err => alert(`Failed to save view: ${err}`));
  };

  const handleUpdateActiveView = () => {
    if (!activeView) return;
    const currentCoords = {};
    nodes.forEach(n => {
      if (n.type === 'customDevice') currentCoords[n.id] = { x: n.position.x, y: n.position.y };
      else if (n.type === 'customZone') currentCoords[n.id] = { x: n.position.x, y: n.position.y, width: n.width || n.style?.width, height: n.height || n.style?.height };
    });

    const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` };
    
    fetch(`http://127.0.0.1:8000/topology/views/${activeView.id}`, { method: 'DELETE', headers })
    .then(() => fetch('http://127.0.0.1:8000/topology/views', { method: 'POST', headers, body: JSON.stringify({ name: activeView.name, zone_ids: selectedZones, coordinates: currentCoords }) }))
    .then(res => res.json())
    .then(newView => {
      setSavedViews(prev => [...prev.filter(v => v.id !== activeView.id), newView]);
      setActiveView(newView);
      alert(`✅ View "${activeView.name}" updated successfully!`);
    })
    .catch(err => alert(`Failed to update view: ${err}`));
  };

  const handleDeleteView = (viewId) => {
    if (!window.confirm("Delete this saved view?")) return;
    fetch(`http://127.0.0.1:8000/topology/views/${viewId}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
    .then(() => { setSavedViews(savedViews.filter(v => v.id !== viewId)); if (activeView?.id === viewId) setActiveView(null); });
  };

  const handleLoadView = (view) => {
    setActiveView(view);
    setSelectedZones(view.zone_ids);
  };

  useEffect(() => {
    fetch('http://127.0.0.1:8000/topology/edges', { headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } })
    .then(res => res.ok ? res.json() : [])
    .then(edgeData => {
      let savedGhostPositions = {};
      let savedZoneGeometries = {};
      try { savedGhostPositions = JSON.parse(localStorage.getItem('vnms_ghost_positions') || '{}'); } catch (e) {}
      try { savedZoneGeometries = JSON.parse(localStorage.getItem('vnms_zone_geometries') || '{}'); } catch (e) {} 

      const visibleZoneIds = [...new Set(devices.map(d => d.zone_id || -1))].filter(z => selectedZones.includes(z));
      let currentNodes = [];

      visibleZoneIds.forEach((zoneId, index) => {
        let zName = zoneId === -1 ? "Unassigned Devices" : "Unknown Zone";
        orgData.forEach(b => b.floors.forEach(f => f.zones.forEach(z => { if(z.id === zoneId) zName = z.name; })));

        const boxId = `box-${zoneId}`;
        const defX = savedZoneGeometries[boxId]?.x ?? 50 + (index * 450);
        const defY = savedZoneGeometries[boxId]?.y ?? 50;
        const defW = savedZoneGeometries[boxId]?.width ?? 400;
        const defH = savedZoneGeometries[boxId]?.height ?? 400;

        let spawnX = activeView?.coordinates?.[boxId]?.x ?? defX;
        let spawnY = activeView?.coordinates?.[boxId]?.y ?? defY;
        let zWidth = activeView?.coordinates?.[boxId]?.width ?? defW;
        let zHeight = activeView?.coordinates?.[boxId]?.height ?? defH;

        currentNodes.push({
          id: boxId, type: 'customZone',
          position: { x: spawnX, y: spawnY },
          data: { label: zName },
          style: { width: zWidth, height: zHeight, zIndex: -1 } 
        });
      });

      devices.forEach((dev, index) => {
        const devZone = dev.zone_id || -1;
        if (selectedZones.includes(devZone)) {
          let spawnX = activeView?.coordinates?.[dev.hostname]?.x ?? dev.pos_x ?? 50;
          let spawnY = activeView?.coordinates?.[dev.hostname]?.y ?? dev.pos_y ?? 80;

          currentNodes.push({
            id: dev.hostname, type: 'customDevice', parentNode: `box-${devZone}`, 
            position: { x: spawnX, y: spawnY },
            data: { label: dev.hostname, ip: dev.ip_address, status: dev.status, latency: dev.latency, device_type: dev.device_type, os: dev.os_type, full_device: dev },
          });
        }
      });

      const activeNodeIds = new Set(currentNodes.map(n => n.id));
      const formattedEdges = [];
      let rogueOffset = 0;

      edgeData.forEach(edge => {
        if (activeNodeIds.has(edge.source_hostname) && activeNodeIds.has(edge.target_hostname)) {
          const isBlocked = edge.link_type.includes('_blocked');
          const baseLinkType = edge.link_type.replace('_blocked', '');
          const isManual = edge.link_type === 'manual'; 
          formattedEdges.push({
            id: `e-${edge.id}`, source: edge.source_hostname, target: edge.target_hostname, type: 'customEdge', 
            data: { source_port: edge.source_port, target_port: edge.target_port, utilization: edge.current_utilization, original_stroke: baseLinkType === 'trunk' ? '#007acc' : '#777', link_type: edge.link_type },
            style: { 
              stroke: isBlocked ? '#555' : (baseLinkType === 'trunk' ? '#007acc' : '#777'), 
              strokeWidth: baseLinkType === 'trunk' ? 3 : 1.5, 
              strokeDasharray: isBlocked ? '5, 5' : (isManual ? '10, 5' : 'none'), 
              opacity: isBlocked ? 0.5 : 1 
            },
          });
        } else if (activeNodeIds.has(edge.source_hostname) && !devices.find(d => d.hostname === edge.target_hostname)) {
           if (!currentNodes.find(n => n.id === edge.target_hostname)) {
              
              // THE SURGICAL INCISION: Check activeView coordinates first, fallback to localStorage
              const viewPos = activeView?.coordinates?.[edge.target_hostname];
              const savedPos = viewPos || savedGhostPositions[edge.target_hostname];
              
              currentNodes.push({ 
                  id: edge.target_hostname, 
                  type: 'customDevice', 
                  position: { 
                      x: savedPos ? savedPos.x : 50 + (rogueOffset * 150), 
                      y: savedPos ? savedPos.y : 400 
                  }, 
                  data: { label: edge.target_hostname, status: 'unmanaged', os: 'Unmanaged / Rogue', full_device: null } 
              });
              rogueOffset++;
           }
           formattedEdges.push({ id: `e-${edge.id}`, source: edge.source_hostname, target: edge.target_hostname, type: 'customEdge', data: { source_port: edge.source_port, target_port: edge.target_port, utilization: 0, original_stroke: '#777' }, style: { stroke: '#777', strokeWidth: 1.5 } });
        }
      });

      setNodes(prev => { return currentNodes.map(cn => { const existing = prev.find(p => p.id === cn.id); if (existing && existing.type !== 'customZone' && !activeView) cn.position = existing.position; return cn; }); });
      setEdges(formattedEdges);
    })
    .catch(err => console.error("Failed to load edges:", err));
  }, [devices, selectedZones, orgData, activeView, refreshTrigger]);

  const onLayout = useCallback(() => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({ rankdir: 'TB', nodesep: 150, ranksep: 200 });

    const deviceNodes = nodes.filter(n => n.type === 'customDevice');
    deviceNodes.forEach((node) => { dagreGraph.setNode(node.id, { width: 160, height: 160 }); });
    edges.forEach((edge) => { dagreGraph.setEdge(edge.source, edge.target); });
    dagre.layout(dagreGraph);

    setNodes(nds => nds.map((node) => {
      if (node.type === 'customZone') return node;
      const nodeWithPosition = dagreGraph.node(node.id);
      return { ...node, position: { x: nodeWithPosition.x - 80, y: nodeWithPosition.y - 80 } };
    }));
  }, [nodes, edges]);

  const onNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), []);
  const onEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), []);
  const onNodeClick = (event, node) => { setSelectedEdge(null); if (node.data && node.data.status !== 'unmanaged' && node.type !== 'customZone') setSelectedDevice(node.data.full_device); };
  const onEdgeClick = (event, edge) => { setSelectedDevice(null); setSelectedEdge(edge); };
  const onPaneClick = () => { setSelectedDevice(null); setSelectedEdge(null); };

  const saveLayout = () => {
    setIsSaving(true);
    const coordinates = [];
    const ghostPositions = {};
    const zoneGeometries = {};

    nodes.forEach(n => {
      if (n.type === 'customZone') {
        zoneGeometries[n.id] = { x: n.position.x, y: n.position.y, width: n.width || n.style?.width || 400, height: n.height || n.style?.height || 400 };
        return;
      }
      if (n.data.status === 'unmanaged') ghostPositions[n.id] = { x: n.position.x, y: n.position.y };
      else {
        const targetDevice = devices.find(d => d.hostname === n.id);
        if (targetDevice) coordinates.push({ id: parseInt(targetDevice.id, 10), pos_x: parseFloat(n.position.x.toFixed(2)), pos_y: parseFloat(n.position.y.toFixed(2)) });
      }
    });

    localStorage.setItem('vnms_ghost_positions', JSON.stringify(ghostPositions));
    localStorage.setItem('vnms_zone_geometries', JSON.stringify(zoneGeometries)); 

    fetch('http://127.0.0.1:8000/topology/update-coordinates', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` }, body: JSON.stringify(coordinates) })
    .then(async res => { if (!res.ok) { const err = await res.json(); throw new Error(err.detail); } return res.json(); })
    .then(() => { setIsSaving(false); alert("✅ Global Map Layout and Zone Sizes saved successfully!"); if (fetchNetworkStatus) fetchNetworkStatus(); })
    .catch(err => { console.error(err); alert(`❌ Failed: ${err.message}`); setIsSaving(false); });
  };

  const handleDiscovery = () => { setIsDiscovering(true); fetch(`http://127.0.0.1:8000/topology/discover`, { method: 'POST', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } }).then(res => res.json()).then(() => { alert("Discovery Engine launched. Map will refresh shortly."); setIsDiscovering(false); }).catch(() => setIsDiscovering(false)); };
  const handleReboot = () => { if (!selectedDevice || !window.confirm(`⚠️ Reboot ${selectedDevice.hostname}?`)) return; setIsRebooting(true); fetch(`http://127.0.0.1:8000/device/${selectedDevice.id}/reboot`, { method: 'POST', headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } }).then(() => { alert("Reboot queued."); setIsRebooting(false); setSelectedDevice(null); }).catch(() => setIsRebooting(false)); };
  const handlePortAction = (hostname, port, action) => { if (!window.confirm(`⚠️ ${action.toUpperCase()} port ${port}?`)) return; setBouncingPort(`${hostname}-${port}`); fetch('http://127.0.0.1:8000/topology/port-action', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` }, body: JSON.stringify({ hostname, port, action }) }).then(res => res.json()).then(data => { alert(`✅ ${data.message}`); setBouncingPort(null); }).catch(err => { alert(`❌ Error: ${err.message}`); setBouncingPort(null); }); };
  const handlePcap = (targetDev, targetPort) => { if(!targetDev) return; const url = `http://127.0.0.1:8000/topology/pcap?device_id=${targetDev.id}&port=${encodeURIComponent(targetPort)}&token=${localStorage.getItem('token')}`; window.open(url, `pcap_${targetDev.id}`, `width=800,height=600`); };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 120px)', position: 'relative', border: '1px solid #333', borderRadius: '8px', overflow: 'hidden' }}>
      
      {showOrgSidebar && (
        <div style={{ width: '320px', backgroundColor: '#252526', borderRight: '1px solid #333', display: 'flex', flexDirection: 'column', zIndex: 5 }}>
          <div style={{ padding: '20px', flex: 1, overflowY: 'auto' }}>
            
            <h4 style={{ margin: '0 0 10px 0', color: '#fff', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Saved Views</h4>
            
            {activeView && (
              <button onClick={handleUpdateActiveView} style={{ width: '100%', padding: '10px', backgroundColor: '#007acc', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', marginBottom: '15px', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>
                💾 Update "{activeView.name}"
              </button>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '15px' }}>
              {savedViews.map(view => (
                <div key={view.id} style={{ display: 'flex', gap: '5px' }}>
                  <button onClick={() => handleLoadView(view)} style={{ flex: 1, padding: '10px', backgroundColor: activeView?.id === view.id ? '#007acc' : '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px', cursor: 'pointer', textAlign: 'left', fontWeight: 'bold' }}>📺 {view.name}</button>
                  <button onClick={() => handleDeleteView(view.id)} style={{ padding: '10px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer' }}>✖</button>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: '5px', marginBottom: '25px' }}>
              <input type="text" placeholder="Save as new view..." value={newViewName} onChange={(e) => setNewViewName(e.target.value)} style={{ flex: 1, padding: '8px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px' }} />
              <button onClick={handleSaveView} style={{ padding: '8px 12px', backgroundColor: '#4caf50', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>Save</button>
            </div>

            <h4 style={{ margin: '0 0 15px 0', color: '#fff', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Organization Tree</h4>
            {orgData.map(bldg => {
              const bldgZoneIds = bldg.floors.flatMap(f => f.zones.map(z => z.id));
              const isBldgChecked = bldgZoneIds.length > 0 && bldgZoneIds.every(id => selectedZones.includes(id));
              const isBldgIndeterminate = !isBldgChecked && bldgZoneIds.some(id => selectedZones.includes(id));

              return (
                <div key={bldg.id} style={{ marginBottom: '20px', padding: '10px', backgroundColor: '#1e1e1e', borderRadius: '6px', border: '1px solid #333' }}>
                  <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', color: '#007acc', fontWeight: 'bold', fontSize: '1.05rem', marginBottom: '10px' }}>
                    <input type="checkbox" checked={isBldgChecked} ref={input => { if (input) input.indeterminate = isBldgIndeterminate; }} onChange={() => handleBuildingToggle(bldg)} style={{ marginRight: '10px' }} /> 🏢 {bldg.name}
                  </label>
                  
                  {bldg.floors.map(floor => {
                    const floorZoneIds = floor.zones.map(z => z.id);
                    const isFloorChecked = floorZoneIds.length > 0 && floorZoneIds.every(id => selectedZones.includes(id));
                    const isFloorIndeterminate = !isFloorChecked && floorZoneIds.some(id => selectedZones.includes(id));

                    return (
                      <div key={floor.id} style={{ paddingLeft: '15px', borderLeft: '1px dashed #444', marginLeft: '10px', marginBottom: '10px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', color: '#e6a23c', fontWeight: 'bold', fontSize: '0.9rem', marginBottom: '5px' }}>
                          <input type="checkbox" checked={isFloorChecked} ref={input => { if (input) input.indeterminate = isFloorIndeterminate; }} onChange={() => handleFloorToggle(floor)} style={{ marginRight: '10px' }} /> 📂 {floor.name}
                        </label>
                        
                        <div style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                          {floor.zones.length === 0 && <span style={{ color: '#666', fontSize: '0.8rem', fontStyle: 'italic' }}>No zones assigned</span>}
                          {floor.zones.map(zone => (
                            <label key={zone.id} style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', color: selectedZones.includes(zone.id) ? '#fff' : '#888', fontSize: '0.85rem' }}>
                              <input type="checkbox" checked={selectedZones.includes(zone.id)} onChange={() => handleZoneToggle(zone.id)} style={{ marginRight: '8px' }} /> {zone.name}
                            </label>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )
            })}

            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', color: '#ccc', fontWeight: 'bold', marginTop: '20px' }}>
              <input type="checkbox" checked={selectedZones.includes(-1)} onChange={() => handleZoneToggle(-1)} style={{ marginRight: '10px' }} /> ❓ Unassigned Devices
            </label>

          </div>
        </div>
      )}

      <div style={{ flex: 1, backgroundColor: '#1e1e1e', position: 'relative' }}>
        <ReactFlow nodes={nodes} edges={edges} onConnect={onConnect} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodeClick={onNodeClick} onEdgeClick={onEdgeClick} onPaneClick={onPaneClick} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView attributionPosition="bottom-left">
          <Background color="#333" gap={20} />
          <Controls style={{ backgroundColor: '#252526', fill: '#fff' }} />
          <MiniMap nodeColor="#007acc" maskColor="rgba(0,0,0,0.5)" style={{ backgroundColor: '#252526' }} />
        </ReactFlow>

        <div style={{ position: 'absolute', top: '20px', left: '20px', zIndex: 10 }}>
          <button onClick={() => setShowOrgSidebar(!showOrgSidebar)} style={{ padding: '10px', backgroundColor: '#333', color: '#fff', border: '1px solid #555', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>{showOrgSidebar ? '◀ Hide Views' : '▶ Show Views'}</button>
        </div>
        <div style={{ position: 'absolute', top: '20px', right: (selectedDevice || selectedEdge) ? '340px' : '20px', transition: 'right 0.3s ease', zIndex: 10, display: 'flex', gap: '10px' }}>
          <button onClick={onLayout} style={{ padding: '10px 20px', backgroundColor: '#e6a23c', color: '#000', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>✨ Auto-Layout</button>
          <button onClick={handleDiscovery} disabled={isDiscovering || userRole !== 'admin'} style={{ padding: '10px 20px', backgroundColor: isDiscovering ? '#555' : '#4caf50', color: 'white', border: 'none', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>{isDiscovering ? 'Scanning...' : '🔍 Run Auto-Discovery'}</button>
          <button onClick={saveLayout} disabled={isSaving || userRole !== 'admin'} style={{ padding: '10px 20px', backgroundColor: isSaving ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>{isSaving ? 'Saving...' : '💾 Save Global Layout'}</button>
        </div>
      </div>

      <div style={{ width: '320px', backgroundColor: '#252526', borderLeft: '1px solid #333', padding: '20px', display: 'flex', flexDirection: 'column', position: 'absolute', right: (selectedDevice || selectedEdge) ? '0' : '-320px', top: 0, bottom: 0, transition: 'right 0.3s ease', boxShadow: '-5px 0 15px rgba(0,0,0,0.5)', overflowY: 'auto' }}>
        {selectedDevice && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #444', paddingBottom: '15px', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#fff' }}>{selectedDevice.hostname}</h3><button onClick={() => setSelectedDevice(null)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2rem' }}>✖</button>
            </div>
            <div style={{ marginBottom: '30px' }}>
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>IP Address</div><div style={{ color: '#fff', fontFamily: 'monospace', marginBottom: '15px' }}>{selectedDevice.ip_address}</div>
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>Status</div><div style={{ color: selectedDevice.status === 'online' ? '#4caf50' : '#f44336', fontWeight: 'bold', marginBottom: '15px', textTransform: 'uppercase' }}>{selectedDevice.status}</div>
              <div style={{ color: '#aaa', fontSize: '0.85rem', marginBottom: '5px' }}>OS Type</div><div style={{ color: '#fff', textTransform: 'capitalize' }}>{selectedDevice.os_type}</div>
            </div>
            <h4 style={{ color: '#888', borderBottom: '1px solid #444', paddingBottom: '5px', marginBottom: '15px' }}>Quick Actions</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <button onClick={() => setActiveTab('Configuration')} style={{ padding: '12px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px', cursor: 'pointer', textAlign: 'left', fontWeight: 'bold' }}>⚡ Push Template</button>
              <button onClick={() => window.open(`/?cli=${selectedDevice.id}`, `cli_${selectedDevice.id}`, `width=800,height=600,resizable=yes,scrollbars=yes`)} style={{ padding: '12px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', borderRadius: '4px', cursor: 'pointer', textAlign: 'left', fontWeight: 'bold' }}>💻 Open Secure CLI</button>
              <button onClick={handleReboot} disabled={isRebooting || userRole !== 'admin'} style={{ padding: '12px', backgroundColor: isRebooting ? '#555' : '#f4433622', color: isRebooting ? '#aaa' : '#f44336', border: `1px solid ${isRebooting ? '#555' : '#f44336'}`, borderRadius: '4px', cursor: (isRebooting || userRole !== 'admin') ? 'not-allowed' : 'pointer', textAlign: 'left', fontWeight: 'bold', marginTop: '20px' }}>{isRebooting ? 'Executing...' : '↻ Safe Reboot'}</button>
            </div>
          </>
        )}
        {selectedEdge && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #444', paddingBottom: '15px', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#fff' }}>Link Interconnect</h3><button onClick={() => setSelectedEdge(null)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2rem' }}>✖</button>
            </div>
            <div style={{ backgroundColor: '#1a1a1a', padding: '15px', borderRadius: '6px', marginBottom: '30px', border: '1px solid #333' }}>
              {selectedEdge.data?.link_type === 'manual' && (
              <button onClick={() => handleDeleteManualEdge(selectedEdge.id.replace('e-', ''))} style={{ width: '100%', padding: '10px', backgroundColor: 'transparent', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', marginBottom: '15px' }}>
                ✂️ Delete Manual Link
              </button>
            )}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ textAlign: 'left', maxWidth: '40%' }}><strong style={{ color: '#007acc', display: 'block', fontSize: '1.1rem', wordBreak: 'break-all' }}>{selectedEdge.source}</strong><span style={{ fontFamily: 'monospace', color: '#4caf50', fontSize: '0.85rem' }}>{selectedEdge.data?.source_port}</span></div>
                <div style={{ flex: 1, borderBottom: '2px dashed #555', margin: '0 10px', position: 'relative', top: '-5px' }}><span style={{ position: 'absolute', top: '-18px', left: '50%', transform: 'translateX(-50%)', fontSize: '0.75rem', color: '#aaa', whiteSpace: 'nowrap', backgroundColor: '#1a1a1a', padding: '0 5px' }}>{selectedEdge.data?.utilization}% Util</span></div>
                <div style={{ textAlign: 'right', maxWidth: '40%' }}><strong style={{ color: '#007acc', display: 'block', fontSize: '1.1rem', wordBreak: 'break-all' }}>{selectedEdge.target}</strong><span style={{ fontFamily: 'monospace', color: '#4caf50', fontSize: '0.85rem' }}>{selectedEdge.data?.target_port}</span></div>
              </div>
            </div>
            <h4 style={{ color: '#888', borderBottom: '1px solid #444', paddingBottom: '5px', marginBottom: '15px' }}>Port Ops: {selectedEdge.source}</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '25px' }}>
              <button onClick={() => handlePortAction(selectedEdge.source, selectedEdge.data.source_port, 'shutdown')} disabled={bouncingPort === `${selectedEdge.source}-${selectedEdge.data.source_port}` || userRole !== 'admin'} style={{ padding: '8px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold' }}>🔴 Shut</button>
              <button onClick={() => handlePortAction(selectedEdge.source, selectedEdge.data.source_port, 'no_shutdown')} disabled={bouncingPort === `${selectedEdge.source}-${selectedEdge.data.source_port}` || userRole !== 'admin'} style={{ padding: '8px', backgroundColor: '#4caf5022', color: '#4caf50', border: '1px solid #4caf50', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold' }}>🟢 No Shut</button>
              <button onClick={() => handlePortAction(selectedEdge.source, selectedEdge.data.source_port, 'bounce')} disabled={bouncingPort === `${selectedEdge.source}-${selectedEdge.data.source_port}` || userRole !== 'admin'} style={{ gridColumn: '1 / -1', padding: '8px', backgroundColor: '#1e1e1e', color: '#e6a23c', border: '1px solid #e6a23c', borderRadius: '4px', cursor: userRole === 'admin' ? 'pointer' : 'not-allowed', fontWeight: 'bold' }}>⚡ Bounce Port</button>
              <button onClick={() => handlePcap(devices.find(d => d.hostname === selectedEdge.source), selectedEdge.data.source_port)} disabled={!devices.find(d => d.hostname === selectedEdge.source) || devices.find(d => d.hostname === selectedEdge.source)?.os_type !== 'cisco'} style={{ gridColumn: '1 / -1', padding: '8px', backgroundColor: '#007acc', color: '#fff', border: 'none', borderRadius: '4px', cursor: devices.find(d => d.hostname === selectedEdge.source) && devices.find(d => d.hostname === selectedEdge.source)?.os_type === 'cisco' ? 'pointer' : 'not-allowed', fontWeight: 'bold', marginTop: '5px', opacity: devices.find(d => d.hostname === selectedEdge.source) && devices.find(d => d.hostname === selectedEdge.source)?.os_type === 'cisco' ? 1 : 0.5 }}>🕵️‍♂️ Packet Trace (Cisco Only)</button>
            </div>
            <h4 style={{ color: '#888', borderBottom: '1px solid #444', paddingBottom: '5px', marginBottom: '15px' }}>Port Ops: {selectedEdge.target}</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '20px' }}>
              <button onClick={() => handlePortAction(selectedEdge.target, selectedEdge.data.target_port, 'shutdown')} disabled={bouncingPort === `${selectedEdge.target}-${selectedEdge.data.target_port}` || userRole !== 'admin' || !devices.find(d => d.hostname === selectedEdge.target)} style={{ padding: '8px', backgroundColor: '#f4433622', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: (userRole === 'admin' && devices.find(d => d.hostname === selectedEdge.target)) ? 'pointer' : 'not-allowed', fontWeight: 'bold', opacity: !devices.find(d => d.hostname === selectedEdge.target) ? 0.5 : 1 }}>🔴 Shut</button>
              <button onClick={() => handlePortAction(selectedEdge.target, selectedEdge.data.target_port, 'no_shutdown')} disabled={bouncingPort === `${selectedEdge.target}-${selectedEdge.data.target_port}` || userRole !== 'admin' || !devices.find(d => d.hostname === selectedEdge.target)} style={{ padding: '8px', backgroundColor: '#4caf5022', color: '#4caf50', border: '1px solid #4caf50', borderRadius: '4px', cursor: (userRole === 'admin' && devices.find(d => d.hostname === selectedEdge.target)) ? 'pointer' : 'not-allowed', fontWeight: 'bold', opacity: !devices.find(d => d.hostname === selectedEdge.target) ? 0.5 : 1 }}>🟢 No Shut</button>
              <button onClick={() => handlePortAction(selectedEdge.target, selectedEdge.data.target_port, 'bounce')} disabled={bouncingPort === `${selectedEdge.target}-${selectedEdge.data.target_port}` || userRole !== 'admin' || !devices.find(d => d.hostname === selectedEdge.target)} style={{ gridColumn: '1 / -1', padding: '8px', backgroundColor: '#1e1e1e', color: '#e6a23c', border: '1px solid #e6a23c', borderRadius: '4px', cursor: (userRole === 'admin' && devices.find(d => d.hostname === selectedEdge.target)) ? 'pointer' : 'not-allowed', fontWeight: 'bold', opacity: !devices.find(d => d.hostname === selectedEdge.target) ? 0.5 : 1 }}>⚡ Bounce Port</button>
              <button onClick={() => handlePcap(devices.find(d => d.hostname === selectedEdge.target), selectedEdge.data.target_port)} disabled={!devices.find(d => d.hostname === selectedEdge.target) || devices.find(d => d.hostname === selectedEdge.target)?.os_type !== 'cisco'} style={{ gridColumn: '1 / -1', padding: '8px', backgroundColor: '#007acc', color: '#fff', border: 'none', borderRadius: '4px', cursor: devices.find(d => d.hostname === selectedEdge.target) && devices.find(d => d.hostname === selectedEdge.target)?.os_type === 'cisco' ? 'pointer' : 'not-allowed', fontWeight: 'bold', marginTop: '5px', opacity: !devices.find(d => d.hostname === selectedEdge.target) || devices.find(d => d.hostname === selectedEdge.target)?.os_type !== 'cisco' ? 0.5 : 1 }}>🕵️‍♂️ Packet Trace (Cisco Only)</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
Topology.propTypes = { devices: PropTypes.array.isRequired, userRole: PropTypes.string.isRequired, setActiveTab: PropTypes.func.isRequired, fetchNetworkStatus: PropTypes.func, orgData: PropTypes.array.isRequired };