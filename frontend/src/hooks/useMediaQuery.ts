import { useState, useEffect } from 'react';

/**
 * Client-side breakpoint match (default: &lt; 768px = narrow / phone layout).
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(query);
    const update = () => setMatches(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [query]);

  return matches;
}

export function useIsMobileLayout(): boolean {
  return useMediaQuery('(max-width: 767px)');
}
