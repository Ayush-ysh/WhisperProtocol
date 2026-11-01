import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  variant?: 'default' | 'outline';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ children, className = '', variant = 'default', ...props }, ref) => {
    const variantClass =
      variant === 'outline'
        ? 'border border-[#E8E8E3]/30 px-6 py-4 font-mono text-xs uppercase tracking-widest text-[#888A8F] hover:text-[#E8E8E3] hover:border-[#E8E8E3] transition-all duration-200'
        : 'brutalist-button';

    return (
      <button
        ref={ref}
        className={[variantClass, className].join(' ')}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
