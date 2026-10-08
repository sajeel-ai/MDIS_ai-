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
    'inline-flex items-center justify-center font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50 disabled:pointer-events-cursor-not-allowed';

  const sizeStyles = {
    sm: 'h-8 px-3 text-xs rounded',
    md: 'h-9 px-4 text-xs rounded-md',
    lg: 'h-10 px-5 text-sm rounded-md',
  };

  const variantStyles = {
    primary: 'bg-[#146EF5] text-white hover:bg-[#0F5BD6] active:bg-[#0B4FC0] border border-transparent shadow-xs',
    secondary: 'bg-[#F5FAFF] text-[#071A3D] hover:bg-[#DCE7F3] border border-transparent',
    outline: 'bg-white text-[#071A3D] border border-[#DCE7F3] hover:bg-[#EAF5FF]',
    ghost: 'bg-transparent text-[#52627A] hover:bg-[#F5FAFF] hover:text-[#071A3D]',
    danger: 'bg-[#dc2626] text-white hover:bg-[#b91c1c] border border-transparent shadow-xs',
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
