export const routing = {
  locales: ['fr', 'en'] as const,
  defaultLocale: 'fr' as const,
};

export type Locale = (typeof routing.locales)[number];
