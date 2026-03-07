'use client';

import Script from 'next/script';

export function PlausibleAnalytics() {
  const domain = process.env.NEXT_PUBLIC_PLAUSIBLE_DOMAIN;

  if (!domain) return null;

  const plausibleHost =
    process.env.NEXT_PUBLIC_PLAUSIBLE_HOST || 'https://plausible.io';

  return (
    <Script
      defer
      data-domain={domain}
      src={`${plausibleHost}/js/script.js`}
      strategy="afterInteractive"
    />
  );
}
