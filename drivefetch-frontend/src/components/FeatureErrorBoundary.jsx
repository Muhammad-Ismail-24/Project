import React from 'react';

/**
 * FeatureErrorBoundary — contains a crash inside one feature (Chat,
 * Matchmaker, search results) so the rest of the app keeps working.
 */
class FeatureErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error instanceof Error ? error.message : '' };
  }

  componentDidCatch(error, info) {
    if (import.meta.env.DEV) {
      console.error(
        `[FeatureErrorBoundary] ${this.props.featureName} crashed:`,
        error instanceof Error ? error.message : 'Unknown error',
        info.componentStack
      );
    }
  }

  render() {
    if (this.state.hasError) {
      const name = this.props.featureName || 'This feature';
      return (
        <div role="alert" className="w-full max-w-3xl mx-auto my-10 px-5 sm:px-10">
          <div className="bg-df-grey dark:bg-black border-l-[14px] border-df-red p-6 sm:p-8 flex flex-col gap-4">
            <span className="self-start px-3 py-1.5 border-2 border-black dark:border-zinc-50 text-xs font-extrabold tracking-[0.08em] uppercase">{name}</span>
            <h2 className="df-display text-5xl sm:text-6xl">{name} hit a pothole.</h2>
            <p className="df-muted text-base leading-relaxed">
              The rest of DriveFetch still works. Try again, or use another tool while this is looked into.
            </p>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => this.setState({ hasError: false, message: '' })} className="df-btn-red h-12 px-5">
                Try again
              </button>
              <a href="/" className="df-btn-outline h-12 px-5">Back to Discover</a>
            </div>
            {this.state.message ? (
              <details className="text-sm df-muted">
                <summary className="min-h-[32px] flex items-center">Technical details</summary>
                <code className="block mt-2 px-3 py-2 bg-white dark:bg-zinc-950 font-mono text-xs text-black dark:text-zinc-50 break-words">{this.state.message}</code>
              </details>
            ) : null}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default FeatureErrorBoundary;
