import { LayoutDashboard, BarChart3, FileText, Settings, ChevronLeft } from 'lucide-react';

/* ── Navigation Items ─────────────────────────────────── */
const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, active: true },
  { id: 'analytics', label: 'Analytics', icon: BarChart3, active: false },
  { id: 'reports', label: 'Reports', icon: FileText, active: false },
  { id: 'settings', label: 'Settings', icon: Settings, active: false },
];

/* ── Sidebar Component ────────────────────────────────── */
interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      className="fixed left-0 top-0 z-40 flex h-screen flex-col border-r"
      style={{
        width: collapsed ? '68px' : '240px',
        transition: 'width 200ms ease',
        background: '#000000',
        borderColor: 'rgba(255, 255, 255, 0.06)',
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
      <nav className="flex-1 space-y-0.5 px-2 py-4">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`sidebar-item w-full ${item.active ? 'active' : ''}`}
            title={item.label}
            style={{
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? '10px' : undefined,
            }}
          >
            <item.icon
              size={18}
              strokeWidth={1.8}
              className={`sidebar-icon flex-shrink-0 ${item.active ? 'text-app-accent' : ''}`}
            />
            {!collapsed && <span>{item.label}</span>}
          </button>
        ))}
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
