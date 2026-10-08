import React from 'react';
import { Card } from '../ui/Card';

export interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon?: React.ReactNode;
}

export function MetricCard({ title, value, subtitle, change, changeType = 'neutral', icon }: MetricCardProps) {
  const changeColors = {
    positive: 'text-[#15803d] bg-[#f0fdf4]',
    negative: 'text-[#b91c1c] bg-[#fef2f2]',
    neutral: 'text-[#52627A] bg-[#F5FAFF]',
  };

  return (
    <Card hoverable className="flex flex-col justify-between">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-[#52627A] font-sans">{title}</p>
          <h3 className="text-xl font-bold text-[#071A3D] font-sans mt-1 tracking-tight">{value}</h3>
        </div>
        {icon && <div className="p-2 bg-[#EAF5FF] text-[#146EF5] rounded-md">{icon}</div>}
      </div>
      {(subtitle || change) && (
        <div className="flex items-center gap-2 mt-3 pt-2 border-t border-[#DCE7F3]">
          {change && (
            <span className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded ${changeColors[changeType]}`}>
              {change}
            </span>
          )}
          {subtitle && <span className="text-xs text-[#52627A]">{subtitle}</span>}
        </div>
      )}
    </Card>
  );
}
