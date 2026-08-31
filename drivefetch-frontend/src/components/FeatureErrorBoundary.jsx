import React from 'react';

class FeatureErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
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
      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center
                     p-8 text-center rounded-lg border
                     border-red-200 bg-red-50 my-4 mx-auto
                     max-w-lg"
        >
          <p className="text-red-700 font-semibold mb-1 text-lg">
            {this.props.featureName || 'This feature'} ran into
            a problem.
          </p>
          <p className="text-red-500 text-sm mb-4">
            The rest of the page is unaffected. You can try again
            or return to search.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => this.setState({ hasError: false })}
              className="px-4 py-2 text-sm bg-red-600 text-white
                         rounded-md hover:bg-red-700 transition"
            >
              Try Again
            </button>
            <a
              href="/"
              className="px-4 py-2 text-sm border border-red-300
                         text-red-600 rounded-md hover:bg-red-100
                         transition"
            >
              Back to Search
            </a>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default FeatureErrorBoundary;
