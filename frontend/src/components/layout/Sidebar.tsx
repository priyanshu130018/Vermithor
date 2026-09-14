import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, AlertCircle, Search, BookOpen, Activity } from 'lucide-react';
import { cn } from '../../lib/utils';

export const Sidebar: React.FC = () => {
  const navItems = [
    { label: 'Dashboard', path: '/', icon: LayoutDashboard },
    { label: 'Incidents', path: '/incidents', icon: AlertCircle },
    { label: 'Log Search', path: '/logs', icon: Search },
    { label: 'Runbooks', path: '/runbooks', icon: BookOpen },
  ];

  return (
    <aside className="w-64 bg-surface border-r border-border flex flex-col justify-between h-screen fixed top-0 left-0 z-20">
      <div>
        {/* Brand */}
        <div className="h-14 px-6 border-b border-border flex items-center gap-2.5">
          <div className="w-8 h-8 rounded bg-sky-500/20 border border-sky-500/40 flex items-center justify-center text-sky-400 font-bold">
            <Activity className="w-4 h-4 text-sky-400" />
          </div>
          <div>
            <h1 className="font-bold text-sm text-slate-100 tracking-wider font-mono">Vermithor</h1>
            <p className="text-[10px] text-slate-400 uppercase tracking-widest font-mono">Platform</p>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="p-4 space-y-1">
          <div className="px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-slate-500">
            Intelligence
          </div>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-colors',
                    isActive
                      ? 'bg-sky-500/10 text-sky-400 border border-sky-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-surface-elevated'
                  )
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Footer Info */}
      <div className="p-4 border-t border-border bg-surface-elevated/30">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-500">
          <span>Env: <span className="text-emerald-400">Production</span></span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            Live
          </span>
        </div>
      </div>
    </aside>
  );
};
