import { createContext, useContext } from 'react';

/**
 * UIContext — app-wide UI actions and auth state that deeply nested
 * components (save buttons, cards) need without prop drilling.
 */
const UIContext = createContext({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  openSignIn: () => {},
  openAccount: () => {},
});

export function useUI() {
  return useContext(UIContext);
}

export default UIContext;
