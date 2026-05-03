import { 
  SquaresFour as LayoutDashboard, 
  MagnifyingGlass as Search, 
  ClockCounterClockwise as History, 
  Handshake, 
  MapTrifold as Map, 
  Stack as Layers, 
  Shield, 
  CaretLeft as ChevronLeft 
} from '@phosphor-icons/react';

/* ── Navigation Items ─────────────────────────────────── */
const NAV_ITEMS = [
  { id: 'dashboard', label: 'Global Insight Dashboard', icon: LayoutDashboard, active: true },
  { id: 'search', label: 'Search & Configuration', icon: Search, active: false },
  { id: 'history', label: 'Historical Research Manager', icon: History, active: false },
  { id: 'collaboration', label: 'Brand-IP Collaboration', icon: Handshake, active: false },
  { id: 'geo', label: 'Geo-Based Comparison', icon: Map, active: false },
  { id: 'insights', label: 'Multi-Dimensional Insights', icon: Layers, active: false },
  { id: 'access', label: 'Access Management', icon: Shield, active: false },
];

/* ── Sidebar Component ────────────────────────────────── */
interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  activeId?: string;
  onNavigate?: (id: string) => void;
}

export default function Sidebar({ collapsed, onToggle, activeId, onNavigate }: SidebarProps) {
  return (
    <aside
      className="fixed left-0 top-0 z-40 flex h-screen flex-col border-r shadow-xl"
      style={{
        width: collapsed ? '68px' : '240px',
        transition: 'width 200ms ease',
        background: '#05070b',
        borderColor: 'rgba(148, 163, 184, 0.14)',
      }}
    >
      {/* Brand */}
      <div
        className="border-b px-4 py-5"
        style={{ borderColor: 'rgba(255, 255, 255, 0.06)' }}
      >
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-3'}`}>
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-slate-600/40 bg-slate-900/70 text-[11px] font-semibold text-slate-100">
            PP
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <p className="text-sm font-semibold text-white whitespace-nowrap">Project Pluto</p>
              <p className="text-[11px] text-slate-500 whitespace-nowrap">Luvcraft Explorer</p>
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 px-2.5 pb-4 pt-4">
        {!collapsed && (
          <div className="sidebar-nav-head">
            <p className="sidebar-nav-head-label">Navigation</p>
            <span className="sidebar-nav-head-count">{NAV_ITEMS.length}</span>
          </div>
        )}

        <nav className="space-y-2 pt-2">
          {NAV_ITEMS.map((item) => {
            const isActive = activeId ? activeId === item.id : item.active;
            return (
              <button
                key={item.id}
                onClick={() => onNavigate?.(item.id)}
                className={`sidebar-nav-item w-full ${isActive ? 'is-active' : ''} ${collapsed ? 'is-collapsed' : ''}`}
                title={item.label}
                aria-current={isActive ? 'page' : undefined}
                style={{
                  justifyContent: collapsed ? 'center' : 'flex-start',
                }}
              >
                <span className={`sidebar-nav-icon-wrap ${isActive ? 'is-active' : ''}`}>
                  <item.icon
                    size={16}
                    strokeWidth={2}
                    className="sidebar-icon flex-shrink-0"
                  />
                </span>

                {!collapsed && (
                  <span className="sidebar-nav-label truncate">{item.label}</span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer */}
      <div className="border-t px-2 py-3" style={{ borderColor: 'rgba(255, 255, 255, 0.06)' }}>
        <button
          onClick={onToggle}
          className="sidebar-item w-full"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          style={{
            justifyContent: collapsed ? 'center' : 'flex-start',
            padding: collapsed ? '10px' : undefined,
          }}
        >
          <ChevronLeft
            size={16}
            strokeWidth={2}
            className="flex-shrink-0 transition-transform duration-200"
            style={{ transform: collapsed ? 'rotate(180deg)' : 'rotate(0deg)' }}
          />
          {!collapsed && <span>Collapse</span>}
        </button>

        {!collapsed && (
          <div className="mt-2 flex items-center justify-center">
            <span
              className="rounded-md border border-slate-600/30 bg-slate-900/60 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400"
            >
              Internal Tool
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
