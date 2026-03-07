import { NextResponse } from 'next/server';

export async function GET() {
  const appName = process.env.NEXT_PUBLIC_APP_NAME || 'App';
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://example.com';
  const appDescription =
    process.env.NEXT_PUBLIC_APP_DESCRIPTION ||
    'A SaaS application built in Canada.';

  const body = `# ${appName}

> ${appDescription}

## Overview
${appName} is a Canadian SaaS application offering business tools with bilingual support (French and English). All pricing is in CAD with flat-rate plans.

## Key Pages
- Home: ${appUrl}
- Pricing: ${appUrl}/pricing
- Dashboard: ${appUrl}/dashboard (authenticated)
- Sign Up: ${appUrl}/auth/signup
- Log In: ${appUrl}/auth/login
- Blog: ${appUrl}/blog

## Languages
- French (default): ${appUrl}/fr
- English: ${appUrl}/en

## Plans
- Free: $0/mo — basic features
- Pro: $49/mo CAD — unlimited projects, priority support, analytics
- Business: $99/mo CAD — team collaboration, API access, dedicated support

## API
- Webhooks: ${appUrl}/api/webhooks/stripe

## LLM Resources
- Summary: ${appUrl}/llms.txt
- Full content: ${appUrl}/llms-full.txt
- Sitemap: ${appUrl}/sitemap.xml
`;

  return new NextResponse(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
