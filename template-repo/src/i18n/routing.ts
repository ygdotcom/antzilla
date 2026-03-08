import { defineRouting } from 'next-intl/routing';

export const routing = defineRouting({
  locales: ['fr', 'en'],
  defaultLocale: 'fr',
  localeDetection: true,
  localePrefix: 'as-needed',
});

export type Locale = (typeof routing.locales)[number];
