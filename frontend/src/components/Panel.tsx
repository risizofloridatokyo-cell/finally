import type { HTMLAttributes, ReactNode } from 'react';

interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title: ReactNode;
  actions?: ReactNode;
  bodyClassName?: string;
}

/** Bordered terminal panel: a slim title bar over a body that fills the remaining height. */
export function Panel({ title, actions, bodyClassName = '', className = '', children, ...rest }: PanelProps) {
  return (
    <section className={`flex min-h-0 flex-col rounded-[3px] border border-line bg-panel ${className}`} {...rest}>
      <header className="flex h-8 shrink-0 items-center justify-between gap-2 border-b border-line px-3">
        <h2 className="truncate text-[12px] font-medium text-ink-2">{title}</h2>
        {actions}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
