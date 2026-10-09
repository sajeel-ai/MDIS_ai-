import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const baseStyles =
    'group inline-flex items-center justify-center font-medium will-change-transform transition-[transform,box-shadow,background-color,border-color,color] duration-[240ms] ease-[cubic-bezier(0.22,1,0.36,1)] focus:outline-none focus:ring-0 focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-[#146EF5] active:translate-y-0 active:scale-[0.995] disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none disabled:hover:translate-y-0';

  const sizeStyles = {
    sm: 'h-8 px-3 text-xs rounded-sm',
    md: 'h-9 px-4 text-xs rounded-sm',
    lg: 'h-10 px-5 text-sm rounded-sm',
  };

  const variantStyles = {
    primary: 'bg-gradient-to-r from-[#0877F9] to-[#16C7E8] text-white hover:-translate-y-px hover:from-[#146EF5] hover:to-[#22D3EE] hover:shadow-[0_10px_24px_rgba(20,110,245,0.28)] border-0 shadow-[0_6px_16px_rgba(20,110,245,0.18)]',
    secondary: 'bg-[#F5FAFF] text-[#071A3D] hover:bg-[#DCE7F3] border border-transparent',
    outline: 'bg-white text-[#071A3D] border border-[#DCE7F3] hover:bg-[#EAF5FF]',
    ghost: 'bg-transparent text-[#52627A] hover:bg-[#F5FAFF] hover:text-[#071A3D]',
    danger: 'bg-[#dc2626] text-white hover:-translate-y-px hover:bg-[#b91c1c] hover:shadow-[0_8px_18px_rgba(220,38,38,0.22)] border-0 shadow-xs',
  };

  return (
    <button
      className={twMerge(clsx(baseStyles, sizeStyles[size], variantStyles[variant], className))}
      disabled={disabled}
      {...props}
    >
      {icon && <span className="mr-1.5 flex items-center justify-center">{icon}</span>}
      {children}
    </button>
  );
}
