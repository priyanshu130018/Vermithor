import React from 'react';
import { Bell, ShieldCheck, Terminal } from 'lucide-react';

export const Topbar: React.FC = () => {
  return (
    <header className="h-14 bg-surface/80 backdrop-blur border-b border-border fixed top-0 right-0 left-64 z-10 px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-surface-elevated rounded border border-border text-xs font-mono text-slate-300">
          <Terminal className="w-3.5 h-3.5 text-sky-400" />
          <span>SRE Control Center</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/60 px-2.5 py-1 rounded">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>8 / 8 Services Online</span>
        </div>

        <button className="p-2 text-slate-400 hover:text-slate-200 hover:bg-surface-elevated rounded transition-colors relative">
          <Bell className="w-4 h-4" />
          <span className="w-2 h-2 rounded-full bg-red-500 absolute top-1.5 right-1.5" />
        </button>
      </div>
    </header>
  );
};
