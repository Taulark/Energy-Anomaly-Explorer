import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  err: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { err: null };

  static getDerivedStateFromError(err: Error): State {
    return { err };
  }

  componentDidCatch(err: Error, info: ErrorInfo) {
    console.error('UI error boundary:', err, info.componentStack);
  }

  render() {
    if (this.state.err) {
      return (
        <div className="min-h-[100dvh] flex flex-col items-center justify-center gap-4 bg-[#0f0f23] px-6 text-center">
          <p className="text-sm font-medium text-amber-200">Something went wrong in this view.</p>
          <p className="max-w-md text-xs text-gray-500">
            Try refreshing the page. If it keeps happening, open another tab or switch chart tabs — the rest of the app may still work.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
