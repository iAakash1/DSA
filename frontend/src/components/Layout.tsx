/** App shell: sidebar navigation, header, palette and global shortcuts. */

import { useCallback, useMemo, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  Award,
  BarChart3,
  BookOpen,
  Command,
  Flame,
  Layers,
  LayoutDashboard,
  ListChecks,
  Menu,
  Plus,
  RefreshCw,
  Repeat,
  Settings as SettingsIcon,
  Sparkles,
  Target,
  Flag,
  Trophy,
  X,
  Zap,
} from 'lucide-react';
import clsx from 'clsx';
import { api } from '../lib/api';
import { useApi, useHotkeys } from '../hooks/useApi';
import { AddProblemModal } from './AddProblemModal';
import { CommandPalette } from './CommandPalette';

const NAV = [
  {
    section: null,
    items: [{ to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true }],
  },
  {
    section: 'Problems',
    items: [
      { to: '/problems', label: 'All Problems', icon: Layers },
      { to: '/sheets/cp31', label: 'CP-31', icon: Target },
      { to: '/sheets/striver-a2z', label: 'Striver A2Z', icon: BookOpen },
    ],
  },
  {
    section: 'Practice',
    items: [
      { to: '/missions', label: "Today's Mission", icon: ListChecks },
      { to: '/reviews', label: 'Review Queue', icon: Repeat },
      { to: '/coach', label: 'AI Coach', icon: Sparkles },
    ],
  },
  {
    section: 'ICPC',
    items: [
      { to: '/icpc', label: 'ICPC Mode', icon: Flag },
    ],
  },
  {
    section: 'Analytics',
    items: [
      { to: '/analytics', label: 'Overview', icon: BarChart3 },
      { to: '/analytics/topics', label: 'Topics & Patterns', icon: Layers },
      { to: '/contests', label: 'Contests', icon: Trophy },
    ],
  },
  {
    section: null,
    items: [
      { to: '/achievements', label: 'Achievements', icon: Award },
      { to: '/settings', label: 'Settings', icon: SettingsIcon },
    ],
  },
] as const;

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      {NAV.map((group, index) => (
        <div key={index} className="mb-3">
          {group.section && <div className="label px-2 py-1.5">{group.section}</div>}
          {group.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={'end' in item ? item.end : false}
              onClick={onNavigate}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors',
                  isActive
                    ? 'bg-surface-3 font-medium text-ink'
                    : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                )
              }
            >
              <item.icon size={15} />
              {item.label}
            </NavLink>
          ))}
        </div>
      ))}
    </>
  );
}

export function Layout() {
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const { data: dashboard, reload } = useApi(() => api.dashboard(), []);

  const runSync = useCallback(async () => {
    setSyncing(true);
    try {
      await api.syncAll();
      reload();
    } finally {
      setSyncing(false);
    }
  }, [reload]);

  const hotkeys = useMemo(
    () => ({
      'mod+k': () => setPaletteOpen(true),
      s: () => setPaletteOpen(true),
      a: () => setAddOpen(true),
      d: () => navigate('/'),
      p: () => navigate('/problems'),
      r: () => navigate('/reviews'),
      c: () => navigate('/coach'),
    }),
    [navigate],
  );
  useHotkeys(hotkeys);

  const streak = dashboard?.streak;
  const level = dashboard?.level;
  const goal = dashboard?.daily_goal;

  return (
    <div className="flex min-h-screen bg-surface-0">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-surface-1 lg:flex">
        <div className="flex items-center gap-2 px-4 py-4">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-sm font-bold text-surface-0">
            ⚒
          </span>
          <span className="text-sm font-semibold tracking-wide">CP-FORGE</span>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          <NavLinks />
        </nav>

        <button
          onClick={() => setPaletteOpen(true)}
          className="mx-2 mb-3 flex items-center justify-between rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink-dim hover:text-ink"
        >
          <span className="flex items-center gap-1.5">
            <Command size={12} /> Command
          </span>
          <kbd className="font-mono">⌘K</kbd>
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex items-center justify-between gap-4 border-b border-line bg-surface-0/90 px-4 py-2.5 backdrop-blur lg:px-6">
          <div className="flex items-center gap-4 overflow-x-auto">
            <button
              onClick={() => setDrawerOpen(true)}
              className="shrink-0 rounded-lg p-1.5 text-ink-muted hover:bg-surface-2 hover:text-ink lg:hidden"
              aria-label="Open navigation"
            >
              <Menu size={18} />
            </button>

            {level && (
              <div className="flex items-center gap-2">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-surface-3 text-[11px] font-bold text-accent">
                  {level.level}
                </span>
                <div className="hidden sm:block">
                  <div className="text-[11px] font-medium text-ink">{level.rank}</div>
                  <div className="h-1 w-24 overflow-hidden rounded-full bg-surface-3">
                    <div
                      className="h-full rounded-full bg-accent transition-[width] duration-500"
                      style={{ width: `${Math.round(level.progress * 100)}%` }}
                    />
                  </div>
                </div>
              </div>
            )}

            {streak && (
              <span className="flex items-center gap-1.5 text-sm">
                <Flame size={14} className={streak.active_today ? 'text-accent' : 'text-ink-dim'} />
                <span className="tabular font-semibold">{streak.current}</span>
                <span className="hidden text-xs text-ink-dim sm:inline">day streak</span>
              </span>
            )}

            {level && (
              <span className="flex items-center gap-1.5 text-sm">
                <Zap size={14} className="text-accent" />
                <span className="tabular font-semibold">{level.total_xp.toLocaleString()}</span>
                <span className="hidden text-xs text-ink-dim sm:inline">XP</span>
              </span>
            )}

            {goal && (
              <span className="flex items-center gap-1.5 text-sm">
                <Target size={14} className={goal.completed ? 'text-success' : 'text-ink-dim'} />
                <span className="tabular font-semibold">
                  {goal.progress}/{goal.target}
                </span>
              </span>
            )}

            {streak && streak.freezes_available > 0 && (
              <span className="flex items-center gap-1 text-sm text-info" title="Streak freezes">
                ❄ <span className="tabular font-semibold">{streak.freezes_available}</span>
              </span>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={runSync}
              disabled={syncing}
              className="btn btn-ghost"
              title="Sync platform accounts"
            >
              <RefreshCw size={13} className={clsx(syncing && 'animate-spin')} />
              <span className="hidden sm:inline">Sync</span>
            </button>
            <button onClick={() => setAddOpen(true)} className="btn btn-primary">
              <Plus size={14} />
              <span className="hidden sm:inline">Add</span>
            </button>
          </div>
        </header>

        <main className="min-w-0 flex-1 px-4 py-5 lg:px-6">
          <Outlet />
        </main>
      </div>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
            aria-hidden
          />
          <div className="animate-in absolute left-0 top-0 flex h-full w-64 flex-col border-r border-line bg-surface-1">
            <div className="flex items-center justify-between px-4 py-4">
              <span className="flex items-center gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-sm font-bold text-surface-0">
                  ⚒
                </span>
                <span className="text-sm font-semibold tracking-wide">CP-FORGE</span>
              </span>
              <button
                onClick={() => setDrawerOpen(false)}
                className="text-ink-dim hover:text-ink"
                aria-label="Close navigation"
              >
                <X size={18} />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto px-2 pb-4">
              <NavLinks onNavigate={() => setDrawerOpen(false)} />
            </nav>
          </div>
        </div>
      )}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onAddProblem={() => setAddOpen(true)}
        onSync={runSync}
      />
      <AddProblemModal open={addOpen} onClose={() => setAddOpen(false)} onAdded={reload} />
    </div>
  );
}
