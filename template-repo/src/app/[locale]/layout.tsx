import type { ReactNode } from 'react';
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages } from 'next-intl/server';
import { routing } from '@/i18n/routing';
import { GoogleAnalytics } from '@/components/google-analytics';
import { PlausibleAnalytics } from '@/components/plausible';
import { SchemaOrg } from '@/components/schema-org';
import '@/app/globals.css';
import '@/app/brand.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export const metadata: Metadata = {
  title: {
    template: `%s | ${process.env.NEXT_PUBLIC_APP_NAME || 'App'}`,
    default: process.env.NEXT_PUBLIC_APP_NAME || 'App',
  },
  description:
    process.env.NEXT_PUBLIC_APP_DESCRIPTION ||
    'A Canadian SaaS application.',
};

interface LocaleLayoutProps {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}

export default async function LocaleLayout({
  children,
  params,
}: LocaleLayoutProps) {
  const { locale } = await params;
  const messages = await getMessages();

  const appName = process.env.NEXT_PUBLIC_APP_NAME || 'App';
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://example.com';
  const appDescription =
    process.env.NEXT_PUBLIC_APP_DESCRIPTION ||
    'A Canadian SaaS application.';

  return (
    <html lang={locale} className={inter.variable}>
      <head>
        <SchemaOrg
          name={appName}
          description={appDescription}
          url={appUrl}
          price="0"
          currency="CAD"
        />
      </head>
      <body className="min-h-screen bg-white font-sans text-gray-900 antialiased">
        <NextIntlClientProvider messages={messages}>
          {children}
        </NextIntlClientProvider>
        <GoogleAnalytics />
        <PlausibleAnalytics />
      </body>
    </html>
  );
}
