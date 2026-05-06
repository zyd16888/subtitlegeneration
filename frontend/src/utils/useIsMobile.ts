import { useEffect, useState } from 'react';

const MOBILE_BREAKPOINT = 768;
const TABLET_BREAKPOINT = 1024;

const matchQuery = (query: string) => {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia(query).matches;
};

export const useMediaQuery = (query: string) => {
  const [matched, setMatched] = useState(() => matchQuery(query));

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatched(e.matches);
    setMatched(mql.matches);
    if (mql.addEventListener) {
      mql.addEventListener('change', handler);
      return () => mql.removeEventListener('change', handler);
    }
    mql.addListener(handler);
    return () => mql.removeListener(handler);
  }, [query]);

  return matched;
};

export const useIsMobile = () => useMediaQuery(`(max-width: ${MOBILE_BREAKPOINT}px)`);

export const useIsTablet = () =>
  useMediaQuery(`(max-width: ${TABLET_BREAKPOINT}px)`);
