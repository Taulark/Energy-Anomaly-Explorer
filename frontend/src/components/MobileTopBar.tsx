import { Menu, Zap } from 'lucide-react';

interface MobileTopBarProps {
  onOpenMenu: () => void;
  onScrollTop: () => void;
}

export default function MobileTopBar({ onOpenMenu, onScrollTop }: MobileTopBarProps) {
  return (
    <header className="sticky top-0 z-30 flex md:hidden items-center gap-2 border-b border-[#2d2d44] bg-[#0f0f23]/95 backdrop-blur-md px-2 pr-[max(0.5rem,env(safe-area-inset-right))] pt-[max(0.375rem,env(safe-area-inset-top))] pb-2 pl-[max(0.5rem,env(safe-area-inset-left))]">
      <button
        type="button"
        aria-label="Open settings menu"
        onClick={onOpenMenu}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[#2d2d44] bg-[#1e1e2e] text-gray-200 active:bg-[#2a2a40]"
      >
        <Menu className="h-5 w-5" strokeWidth={2} />
      </button>
      <button
        type="button"
        onClick={onScrollTop}
        className="flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-lg px-2 active:bg-[#1e1e2e]/80"
      >
        <Zap className="h-5 w-5 shrink-0 text-cyan-400" fill="currentColor" />
        <span className="truncate text-center text-sm font-semibold text-white">
          Energy Anomaly Explorer
        </span>
      </button>
      <div className="w-11 shrink-0" aria-hidden />
    </header>
  );
}
