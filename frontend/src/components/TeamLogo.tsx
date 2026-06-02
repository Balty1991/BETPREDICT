import React, { useState } from 'react';
import { teamLogoUrl } from '@/utils/filters';

interface TeamLogoProps {
  id?: number | null;
  size?: number;
  className?: string;
}

export const TeamLogo: React.FC<TeamLogoProps> = ({ id, size = 34, className = '' }) => {
  const [failed, setFailed] = useState(false);
  const url = teamLogoUrl(id);

  if (!url || failed) {
    return (
      <div
        className={`rounded-full flex-shrink-0 ${className}`}
        style={{ width: size, height: size, background: '#1a2438' }}
      />
    );
  }

  return (
    <img
      src={url}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className={`rounded-full object-contain flex-shrink-0 p-0.5 ${className}`}
      style={{ width: size, height: size, background: '#131c2e' }}
    />
  );
};
