import React from 'react';
import { Eye } from 'lucide-react';

interface HeaderProps {
  mode: 'MANUAL' | 'AUTO';
  onModeChange: (mode: 'MANUAL' | 'AUTO') => void;
  apiConnected: boolean;
  activeVideoId?: string;
}

export const Header: React.FC<HeaderProps> = ({
  mode,
  onModeChange,
  apiConnected,
  activeVideoId = 'VID-000001',
}) => {
  return (
    <header className="app-header">
      <div className="app-container header-inner">
        {/* Left: Brand Identity */}
        <div className="brand-section">
          <div className="brand-logo">
            <Eye size={20} strokeWidth={2.5} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="brand-title">VisionInsight</span>
              <span className="brand-pill">Phase F-1</span>
            </div>
          </div>
        </div>

        {/* Center: Mode Switcher (MANUAL vs AUTO) */}
        <div className="header-center">
          <div className="mode-toggle-group" role="tablist" aria-label="검사 모드 선택">
            <button
              type="button"
              className={`mode-tab ${mode === 'MANUAL' ? 'active' : ''}`}
              onClick={() => onModeChange('MANUAL')}
            >
              <span>MANUAL (수동 Grab)</span>
            </button>
            <button
              type="button"
              className={`mode-tab ${mode === 'AUTO' ? 'active' : ''}`}
              onClick={() => onModeChange('AUTO')}
            >
              <span>AUTO (자동 검사)</span>
            </button>
          </div>
        </div>

        {/* Right: API Connectivity Status */}
        <div className="flex items-center gap-3">
          <div className="header-status-badge">
            <span
              className={`status-dot ${apiConnected ? 'connected' : 'disconnected'}`}
            />
            <span className="font-mono text-xs">
              {apiConnected ? 'FastAPI: CONNECTED' : 'FastAPI: OFFLINE'}
            </span>
          </div>

          <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900/60 border border-slate-700/60 text-xs text-slate-300 font-mono">
            <span className="text-slate-500">Source:</span>
            <span className="text-cyan">{activeVideoId}</span>
          </div>
        </div>
      </div>
    </header>
  );
};
