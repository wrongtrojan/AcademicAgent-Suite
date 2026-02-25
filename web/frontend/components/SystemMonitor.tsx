"use client";
import { useState, useEffect } from 'react';

export default function SystemMonitor() {
  const [metrics, setMetrics] = useState({ cpu: 45, gpu: 32, mem: 68 });

  useEffect(() => {
    const timer = setInterval(() => {
      setMetrics({
        cpu: Math.floor(Math.random() * (85 - 40) + 40),
        gpu: Math.floor(Math.random() * (92 - 20) + 20),
        mem: Math.floor(Math.random() * (75 - 65) + 65), // 内存通常波动较小
      });
    }, 1500);
    return () => clearInterval(timer);
  }, []);

  const MetricBar = ({ label, value, colorClass }: { label: string, value: number, colorClass: string }) => (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-[8px] font-mono text-dracula-comment tracking-tighter">
        <span>{label}</span>
        <span className={colorClass}>{value}%</span>
      </div>
      <div className="w-16 h-1 bg-dracula-current rounded-full overflow-hidden border border-dracula-comment/20">
        <div 
          className={`h-full transition-all duration-1000 ease-out ${colorClass.replace('text-', 'bg-')}`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );

  return (
    <div className="flex items-center gap-4 px-4 py-1 border-l border-dracula-comment/30">
      <MetricBar label="CPU_LOAD" value={metrics.cpu} colorClass="text-dracula-cyan" />
      <MetricBar label="GPU_INF" value={metrics.gpu} colorClass="text-dracula-purple" />
      <MetricBar label="MEM_USED" value={metrics.mem} colorClass="text-dracula-pink" />
      
      <div className="hidden lg:flex flex-col ml-2">
        <span className="text-[8px] font-mono text-dracula-green animate-pulse">● ENGINE_STABLE</span>
        <span className="text-[8px] font-mono text-dracula-comment uppercase">v3.0.4-dist</span>
      </div>
    </div>
  );
}