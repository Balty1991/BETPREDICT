import React from 'react';
import { Shield } from 'lucide-react';

export const PremiumPage: React.FC = () => (
  <div className="flex flex-col items-center justify-center py-20 gap-4">
    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#ffb830] to-[#ff6b35] flex items-center justify-center">
      <Shield className="w-8 h-8 text-white" />
    </div>
    <p className="text-[#e8eeff] font-bold text-lg">Premium</p>
    <p className="text-[#6b7a9e] text-sm text-center max-w-[240px]">
      Funcționalitate în curs de dezvoltare.
    </p>
  </div>
);
