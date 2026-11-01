import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Button } from '../components/ui/Button';
import {
  sendBroadcast,
  getDiscoveredDevices,
  getSavedNodes,
  listenToEngineEvent,
  type DiscoveredPeer,
} from '../services/tauriBridge';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

interface NodeAckState {
  alias: string;
  slot_index: number;
  status: 'pending' | 'ack_received' | 'timeout';
  x: number;
  y: number;
}

export function Broadcast() {
  const [broadcasting, setBroadcasting] = useState(false);
  const [broadcastMessage, setBroadcastMessage] = useState('OPERATION NIGHTFALL — ALL UNITS ENGAGE ACOUSTIC AIR GAP RELAY.');
  const [availableNodes, setAvailableNodes] = useState<DiscoveredPeer[]>([]);
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [nodeStates, setNodeStates] = useState<Record<string, NodeAckState>>({});
  const [statusText, setStatusText] = useState('STANDBY — SELECT TARGETS');

  useEffect(() => {
    // Load discovered and saved nodes
    Promise.all([getDiscoveredDevices(), getSavedNodes()]).then(([d, s]) => {
      const all: DiscoveredPeer[] = [];
      const seen = new Set<string>();

      [...(d?.devices || []), ...(s?.nodes || [])].forEach((n) => {
        if (!seen.has(n.alias)) {
          seen.add(n.alias);
          all.push(n);
        }
      });

      if (all.length === 0) {
        // Fallback default nodes for offline demonstration if no nodes discovered yet
        all.push(
          { alias: 'UNIT_01_COMMAND', session_id: 1, last_seen: Date.now(), age_seconds: 5, rssi_db: 22, profile: 'ultrasonic' },
          { alias: 'UNIT_02_ALPHA', session_id: 2, last_seen: Date.now(), age_seconds: 15, rssi_db: 19, profile: 'ultrasonic' },
          { alias: 'UNIT_03_BRAVO', session_id: 3, last_seen: Date.now(), age_seconds: 25, rssi_db: 26, profile: 'audible' },
          { alias: 'UNIT_04_DELTA', session_id: 4, last_seen: Date.now(), age_seconds: 35, rssi_db: 18, profile: 'ultrasonic' },
        );
      }

      setAvailableNodes(all);
      setSelectedNodes(all.map((n) => n.alias));
    }).catch((e) => console.debug('Failed to load broadcast nodes:', e));

    let unsubAck: (() => void) | undefined;
    listenToEngineEvent<{ session_id: number; node: string; slot_index: number; completed: boolean }>(
      'broadcast_node_ack',
      (data) => {
        setNodeStates((prev) => {
          const current = prev[data.node];
          if (!current) return prev;
          return {
            ...prev,
            [data.node]: { ...current, status: 'ack_received' },
          };
        });

        if (data.completed) {
          setStatusText('ALL RECIPIENTS VERIFIED (FULL DELIVERY MATRIX CONFIRMED)');
        }
      }
    ).then((unsub) => {
      unsubAck = unsub;
    });

    return () => {
      unsubAck?.();
    };
  }, []);

  const handleToggleNode = (alias: string) => {
    setSelectedNodes((prev) =>
      prev.includes(alias) ? prev.filter((a) => a !== alias) : [...prev, alias]
    );
  };

  const handleBroadcast = async () => {
    if (selectedNodes.length === 0 || !broadcastMessage.trim()) return;

    setBroadcasting(true);
    setStatusText('TRANSMITTING GROUP-ENCRYPTED ACOUSTIC PAYLOAD...');

    // Layout nodes geometrically around center
    const initialStates: Record<string, NodeAckState> = {};
    const coords = [
      { x: 18, y: 22 },
      { x: 82, y: 18 },
      { x: 22, y: 80 },
      { x: 78, y: 82 },
      { x: 50, y: 15 },
      { x: 50, y: 85 },
    ];

    selectedNodes.forEach((alias, idx) => {
      const pos = coords[idx % coords.length];
      initialStates[alias] = {
        alias,
        slot_index: idx,
        status: 'pending',
        x: pos.x,
        y: pos.y,
      };
    });
    setNodeStates(initialStates);

    try {
      await sendBroadcast({
        fileName: 'broadcast.bin',
        payloadText: broadcastMessage,
        targets: selectedNodes,
        profile: 'ultrasonic',
        ecc: 8,
      });

      setStatusText('BROADCAST TRANSMITTED — AWAITING NON-COLLIDING TIME-SLOTTED ACKS');

      // Auto-reset broadcasting flag after ACK window
      setTimeout(() => {
        setBroadcasting(false);
      }, (selectedNodes.length * 1.5 + 2) * 1000);
    } catch (e) {
      console.error('Broadcast failed:', e);
      setStatusText('BROADCAST ERROR');
      setBroadcasting(false);
    }
  };

  const confirmedCount = Object.values(nodeStates).filter((n) => n.status === 'ack_received').length;

  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col items-center">
      <div className="absolute top-12 left-12">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">04 / BROADCAST</span>
      </div>

      <div className="text-center mb-10">
        <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-4">
          ONE SIGNAL.
        </h1>
        <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tighter leading-none text-[#888A8F]">
          MULTIPLE RECEIVERS.
        </h1>
        <p className="text-xs font-mono text-[#888A8F] tracking-widest mt-4 uppercase">
          {statusText} {broadcasting && `(${confirmedCount}/${selectedNodes.length} ACKS VERIFIED)`}
        </p>
      </div>

      {/* Acoustic Network Radar Layout */}
      <div className="relative w-full max-w-4xl h-[45vh] border border-[#E8E8E3]/10 bg-[#101114] mb-8 flex items-center justify-center overflow-hidden">
        {/* Central Transmitter */}
        <div className="absolute z-20 flex flex-col items-center">
          <div className="w-3.5 h-3.5 bg-[#E8E8E3] mb-2" />
          <span className="text-[10px] font-mono tracking-widest text-[#E8E8E3] uppercase">TRANSMITTER</span>
        </div>

        {/* Dynamic Nodes & Rays */}
        {Object.values(nodeStates).map((node) => {
          const isAcked = node.status === 'ack_received';
          return (
            <div key={node.alias} className="absolute inset-0 pointer-events-none">
              <div 
                className="absolute flex flex-col items-center z-10"
                style={{ left: `${node.x}%`, top: `${node.y}%`, transform: 'translate(-50%, -50%)' }}
              >
                <div className={`w-2.5 h-2.5 mb-1 transition-all ${isAcked ? 'bg-[#4ADE80]' : 'bg-[#888A8F]'}`} />
                <span className={`text-[9px] font-mono tracking-widest uppercase ${isAcked ? 'text-[#4ADE80]' : 'text-[#888A8F]'}`}>
                  {node.alias} [{isAcked ? 'ACK OK' : `SLOT ${node.slot_index}`}]
                </span>
              </div>

              {/* Ray to node */}
              <svg className="absolute inset-0 w-full h-full">
                <line 
                  x1="50%" y1="50%" 
                  x2={`${node.x}%`} y2={`${node.y}%`} 
                  stroke={isAcked ? 'rgba(74, 222, 128, 0.4)' : 'rgba(232, 232, 227, 0.08)'} 
                  strokeWidth="1" 
                />
                {broadcasting && !isAcked && (
                  <motion.line 
                    x1="50%" y1="50%" 
                    x2={`${node.x}%`} y2={`${node.y}%`} 
                    stroke="rgba(232, 232, 227, 0.6)" 
                    strokeWidth="1.5"
                    strokeDasharray="4 8"
                    initial={{ strokeDashoffset: 100 }}
                    animate={{ strokeDashoffset: 0 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  />
                )}
              </svg>
            </div>
          );
        })}
        
        {broadcasting && (
          <motion.div 
            initial={{ scale: 0, opacity: 0.6 }}
            animate={{ scale: 3.5, opacity: 0 }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            className="absolute rounded-full border border-[#E8E8E3]/30 w-32 h-32"
          />
        )}
      </div>

      {/* Target Node Checkboxes & Message Input */}
      <div className="w-full max-w-4xl bg-[#101114] border border-[#E8E8E3]/10 p-6 flex flex-col gap-6 mb-8">
        <div>
          <div className="flex justify-between items-center mb-3">
            <span className="text-[10px] font-mono tracking-widest text-[#888A8F] uppercase">SELECT RECIPIENT NODES ({selectedNodes.length} SELECTED)</span>
            <button
              onClick={() => setSelectedNodes(selectedNodes.length === availableNodes.length ? [] : availableNodes.map((n) => n.alias))}
              className="text-[9px] font-mono text-[#E8E8E3] underline uppercase"
            >
              {selectedNodes.length === availableNodes.length ? 'DESELECT ALL' : 'SELECT ALL'}
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {availableNodes.map((node) => {
              const checked = selectedNodes.includes(node.alias);
              return (
                <button
                  key={node.alias}
                  type="button"
                  onClick={() => handleToggleNode(node.alias)}
                  className={`p-2.5 text-left font-mono text-[10px] border transition-all ${
                    checked ? 'border-[#E8E8E3] bg-[#E8E8E3]/10 text-[#E8E8E3]' : 'border-[#E8E8E3]/15 text-[#888A8F]'
                  }`}
                >
                  <span className="block font-bold truncate">{node.alias}</span>
                  <span className="block text-[8px] text-[#888A8F]">{node.profile}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <span className="text-[10px] font-mono tracking-widest text-[#888A8F] block mb-2 uppercase">BROADCAST MESSAGE</span>
          <input
            type="text"
            value={broadcastMessage}
            onChange={(e) => setBroadcastMessage(e.target.value)}
            placeholder="ENTER PAYLOAD TO BROADCAST OVER AIR..."
            className="w-full bg-[#16181D] border border-[#E8E8E3]/20 text-[#E8E8E3] font-mono text-xs p-3 outline-none"
          />
        </div>
      </div>

      <Button onClick={handleBroadcast} disabled={broadcasting || selectedNodes.length === 0}>
        {broadcasting ? 'ACOUSTIC BROADCAST IN PROGRESS...' : `BROADCAST TO ${selectedNodes.length} NODES`}
      </Button>
    </motion.div>
  );
}
