import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'ai';
  size?: 'sm' | 'md';
}

export function Badge({
  children,
  variant = 'neutral',
  size = 'md',
  className,
  ...props
}: BadgeProps) {
  const baseStyles = 'inline-flex items-center font-mono font-medium rounded border';

  const sizeStyles = {
    sm: 'px-1.5 py-0.5 text-[10px]',
    md: 'px-2 py-0.5 text-[11px]',
  };

  const variantStyles = {
    success: 'bg-[#f0fdf4] text-[#15803d] border-[#bbf7d0]',
    warning: 'bg-[#fffbeb] text-[#b45309] border-[#fef3c7]',
    error: 'bg-[#fef2f2] text-[#b91c1c] border-[#fecaca]',
    info: 'bg-[#EAF5FF] text-[#146EF5] border-[#DCE7F3]',
    neutral: 'bg-[#EAF5FF] text-[#52627A] border-[#DCE7F3]',
    ai: 'bg-[#EAF5FF] text-[#146EF5] border-[#DCE7F3]',
  };

  return (
    <span
      className={twMerge(clsx(baseStyles, sizeStyles[size], variantStyles[variant], className))}
      {...props}
    >
      {children}
    </span>
  );
}
