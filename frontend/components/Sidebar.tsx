import { 
  LayoutDashboard, 
  Search, 
  History, 
  Handshake, 
  Map, 
  Layers, 
  FileDown, 
  Shield, 
  Lock,
  ChevronLeft 
} from 'lucide-react';

/* ── Navigation Items ─────────────────────────────────── */
const NAV_ITEMS = [
  { id: 'dashboard', label: 'Global Insight Dashboard', icon: LayoutDashboard, active: true },
  { id: 'search', label: 'Search & Configuration', icon: Search, active: false },
  { id: 'history', label: 'Historical Research Manager', icon: History, active: false },
  { id: 'collaboration', label: 'Brand-IP Collaboration', icon: Handshake, active: false },
  { id: 'geo', label: 'Geo-Based Comparison', icon: Map, active: false },
  { id: 'insights', label: 'Multi-Dimensional Insights', icon: Layers, active: false },
  { id: 'export', label: 'Report Export Module', icon: FileDown, active: false },
  { id: 'access', label: 'Access Management', icon: Shield, active: false },
  { id: 'auth', label: 'Authentication & SSO', icon: Lock, active: false },
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
        background: '#050505',
        borderColor: '#1f1f22',
      }}
    >
      {/* Brand */}
      <div
        className="flex items-center gap-3 border-b px-4 py-5"
        style={{ borderColor: 'rgba(255, 255, 255, 0.06)' }}
      >
        <div
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-[11px] font-bold text-white"
          style={{ background: '#2573ff' }}
        >
          PP
        </div>
        {!collapsed && (
          <div className="overflow-hidden">
            <p className="text-sm font-semibold text-white whitespace-nowrap">Project Pluto</p>
            <p className="text-[11px] text-app-muted whitespace-nowrap">Luvcraft Explorer</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1.5 px-3 py-6">
        {NAV_ITEMS.map((item) => {
          const isActive = activeId ? activeId === item.id : item.active;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate?.(item.id)}
              className={`sidebar-item w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm font-medium ${
                isActive ? 'bg-[#141418] text-white border border-[#1f1f22]' : 'text-slate-400 hover:bg-[#141418] hover:text-white border border-transparent'
              }`}
              title={item.label}
              style={{
                justifyContent: collapsed ? 'center' : 'flex-start',
                padding: collapsed ? '10px' : undefined,
              }}
            >
              <item.icon
                size={18}
                strokeWidth={2}
                className={`sidebar-icon flex-shrink-0 ${isActive ? 'text-blue-400' : 'text-slate-500'}`}
              />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

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
              className="rounded-md px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em]"
              style={{ background: 'rgba(37, 115, 255, 0.1)', color: '#2573ff' }}
            >
              Internal Tool
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
