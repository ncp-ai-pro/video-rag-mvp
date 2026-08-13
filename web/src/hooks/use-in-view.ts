import { useEffect, useRef, useState } from "react";

/** 요소가 뷰포트에 처음 들어오는 순간을 감지한다. 한 번 보이면 계속 보인 것으로 유지한다
 * (스크롤을 위아래로 왔다 갔다 해도 다시 사라지며 깜빡이지 않도록). */
export function useInView<T extends HTMLElement>(options?: IntersectionObserverInit) {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setInView(true);
        observer.disconnect();
      }
    }, { threshold: 0.15, ...options });
    observer.observe(el);
    return () => observer.disconnect();
  }, [options]);

  return { ref, inView };
}
