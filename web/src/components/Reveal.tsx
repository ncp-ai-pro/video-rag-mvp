import type { ReactNode } from "react";

import { useInView } from "@/hooks/use-in-view";
import { cn } from "@/lib/utils";

interface Props {
  children: ReactNode;
  className?: string;
  /** 같은 그리드 안 카드들을 순서대로 살짝 늦게 나타나게 할 때 쓴다(ms). */
  delay?: number;
}

/** 스크롤해서 뷰포트에 들어오면 아래에서 위로 살짝 올라오며 나타난다. 랜딩 페이지 전용. */
export function Reveal({ children, className, delay = 0 }: Props) {
  const { ref, inView } = useInView<HTMLDivElement>();

  return (
    <div
      ref={ref}
      style={{ transitionDelay: inView ? `${delay}ms` : "0ms" }}
      className={cn(
        "transition-all duration-700 ease-out",
        inView ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0",
        className,
      )}
    >
      {children}
    </div>
  );
}
