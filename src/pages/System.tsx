import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Button } from '../components/ui/Button';
import { runDiagnostics, getDeviceInfo } from '../services/diagnosticsService';
import type { DeviceInfo } from '../types';

const PAGE_TRANSITION = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
};

export function System() {
  const [testing, setTesting] = useState(false);
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
  const [results, setResults] = useState<Record<string, { status: string; value?: string; message?: string }>>({});

  useEffect(() => {
    let mounted = true;
    getDeviceInfo()
      .then((info) => {
        if (mounted) setDeviceInfo(info);
      })
      .catch((err) => console.error('Failed to load device info:', err));

    return () => {
      mounted = false;
    };
  }, []);

  const handleTest = async () => {
    setTesting(true);
    setResults({});

    try {
      await runDiagnostics((result) => {
        setResults((prev) => ({
          ...prev,
          [result.component]: {
            status: result.status.toUpperCase(),
            value: result.value,
            message: result.message,
          },
        }));
      });
    } catch (err) {
      console.error('Diagnostic error:', err);
    } finally {
      setTesting(false);
    }
  };

  const DIAGNOSTIC_ROWS = [
    {
      label: 'AUDIO INPUT',
      defaultVal: deviceInfo?.audioInput ? `${deviceInfo.audioInput.slice(0, 28)}` : 'PROBING...',
      key: 'MICROPHONE',
    },
    {
      label: 'AUDIO OUTPUT',
      defaultVal: deviceInfo?.audioOutput ? `${deviceInfo.audioOutput.slice(0, 28)}` : 'PROBING...',
      key: 'SPEAKER',
    },
    {
      label: 'SAMPLE RATE',
      defaultVal: deviceInfo ? `${deviceInfo.sampleRate / 1000} KHZ` : '48.0 KHZ',
      key: 'CHANNEL',
    },
    {
      label: 'CHANNEL BAND',
      defaultVal: deviceInfo ? deviceInfo.channelBand : '18.0–19.0 KHZ',
      key: 'FREQUENCY',
    },
    {
      label: 'SIGNAL NOISE FLOOR',
      defaultVal: results['SIGNAL']?.value || 'STANDBY',
      key: 'SIGNAL',
    },
    {
      label: 'MODULATION',
      defaultVal: '2-FSK (50 BAUD)',
      key: 'MODULATION',
    },
    {
      label: 'SECURITY PROFILE',
      defaultVal: 'X25519 / AES-256-GCM',
      key: 'SECURITY',
    },
    {
      label: 'NETWORK ISOLATION',
      defaultVal: 'AIR-GAPPED (OFFLINE)',
      key: 'NETWORK',
    },
  ];

  return (
    <motion.div {...PAGE_TRANSITION} className="w-full min-h-screen pt-32 pb-12 px-6 md:px-12 lg:px-24 flex flex-col items-center justify-center">
      <div className="absolute top-12 left-12">
        <span className="text-[10px] font-mono tracking-widest uppercase text-[#888A8F]">06 / SYSTEM</span>
      </div>

      <div className="w-full max-w-3xl flex flex-col items-center">
        <h1 className="text-6xl md:text-8xl font-bold tracking-tighter leading-none text-[#E8E8E3] mb-12">
          THE CHANNEL.
        </h1>

        <div className="w-full bg-[#101114] border border-[#E8E8E3]/10 p-8 md:p-12 mb-12">
          <div className="flex flex-col gap-4">
            {DIAGNOSTIC_ROWS.map((item) => {
              const res = results[item.key];
              const displayVal = res ? `${res.status} — ${res.value || res.message || ''}` : item.defaultVal;

              return (
                <div key={item.label} className="flex justify-between items-center border-b border-[#E8E8E3]/5 pb-4">
                  <span className="text-xs md:text-sm font-mono tracking-widest text-[#888A8F]">{item.label}</span>
                  <span
                    className={`text-xs md:text-sm font-mono tracking-widest ${
                      res?.status === 'PASS'
                        ? 'text-emerald-400'
                        : res?.status === 'FAIL'
                        ? 'text-red-400'
                        : res?.status === 'RUNNING'
                        ? 'text-amber-400 animate-pulse'
                        : 'text-[#E8E8E3]'
                    }`}
                  >
                    {displayVal}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <Button onClick={handleTest} disabled={testing}>
          {testing ? 'RUNNING REAL CALIBRATION...' : 'RUN CHANNEL TEST'}
        </Button>
      </div>
    </motion.div>
  );
}
