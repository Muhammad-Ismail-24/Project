import React from 'react';

/**
 * FeatureErrorBoundary
 *
 * Isolates render crashes to a single feature area (AI Chat, Matchmaker,
 * Search Results, etc.) so the rest of the page stays alive. The fallback
 * UI follows the project's Neo-Brutalist design language — monospace type,
 * hard borders, uppercase tracking, and a "Try Again" reset button.
 *
 * Usage:
 *   <FeatureErrorBoundary featureName="AI Chat">
 *     <ChatPage />
 *   </FeatureErrorBoundary>
 */
class FeatureErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Log to console in development only
    if (import.meta.env.DEV) {
      console.error(
        `[FeatureErrorBoundary] ${this.props.featureName} crashed:`,
        error,
        info.componentStack
      );
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center p-8 text-center border-2 border-black dark:border-white bg-white dark:bg-zinc-900 my-4 shadow-[4px_4px_0px_#000000] dark:shadow-[4px_4px_0px_#ffffff]">
          <span className="font-mono text-[10px] sm:text-xs font-bold tracking-[0.1em] text-df-red mb-3 uppercase">
            [ RENDER_FAULT ]
          </span>
          <p className="font-mono text-sm font-bold text-df-black dark:text-zinc-100 mb-1 uppercase tracking-wide">
            {this.props.featureName || 'This feature'} ran into a problem.
          </p>
          <p className="font-body text-xs text-df-black/50 dark:text-white/50 mb-6">
            Your other data is safe. Only this section was affected.
          </p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="px-5 py-2.5 border-2 border-black dark:border-white bg-df-red text-white font-mono text-xs font-bold uppercase tracking-[0.06em] hover:-translate-y-0.5 hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] dark:hover:shadow-[3px_3px_0px_0px_rgba(255,255,255,1)] transition-all active:translate-x-[1px] active:translate-y-[1px]"
          >
            [ TRY AGAIN ]
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default FeatureErrorBoundary;
