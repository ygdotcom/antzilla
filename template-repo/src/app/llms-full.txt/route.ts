import { NextResponse } from 'next/server';

export async function GET() {
  const appName = process.env.NEXT_PUBLIC_APP_NAME || 'App';
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://example.com';
  const appDescription =
    process.env.NEXT_PUBLIC_APP_DESCRIPTION ||
    'A SaaS application built in Canada.';

  const body = `# ${appName} — Full Documentation

> ${appDescription}

---

## About

${appName} is a Canadian SaaS platform designed for small and medium businesses. It provides tools to streamline business operations with a focus on the Canadian market.

- Built and hosted in Canada
- Fully bilingual: French (Québec) and English
- All pricing in CAD — no currency surprises
- PIPEDA-compliant data handling

---

## Pages

### Home (/)
The landing page introduces ${appName} with a hero section, feature highlights, and a call-to-action leading to the pricing page or sign-up. Available in French and English.

### Pricing (/pricing)
Three flat-rate tiers with no per-seat fees:

| Plan     | Monthly | Annual (save 17%) |
|----------|---------|-------------------|
| Free     | $0      | $0                |
| Pro      | $49/mo  | $41/mo            |
| Business | $99/mo  | $82/mo            |

All paid plans include a 14-day reverse trial: users get full premium access for 14 days, then downgrade to Free unless they subscribe. This is designed around loss aversion — users experience what they'd lose.

Pro features: Unlimited projects, priority support, advanced analytics, export & integrations.
Business features: All Pro features plus team collaboration, custom branding, API access, dedicated support.

### Dashboard (/dashboard)
Authenticated users see their project dashboard. On first login, a pre-populated sample project is shown (never an empty state). An onboarding checklist with a progress bar guides new users through setup.

### Sign Up (/auth/signup)
Maximum 3 fields: name, email, phone. Accepts optional referral code via query parameter. Language auto-detected from phone area code (514/438 → French, otherwise English). CTA: "Start your 14-day free trial."

### Log In (/auth/login)
Email/password authentication with Google OAuth option.

### Blog (/blog)
MDX-powered blog with bilingual content for SEO and thought leadership.

---

## Technical Details

- Framework: Next.js 15 (App Router)
- Auth: Supabase Auth
- Payments: Stripe (subscriptions, reverse trial, dunning)
- i18n: next-intl (FR default, EN)
- Analytics: Plausible (self-hosted, no cookie consent needed)
- Styling: Tailwind CSS
- Hosting: Vercel

---

## API Endpoints

### POST /api/webhooks/stripe
Handles Stripe webhook events:
- checkout.session.completed — new subscription created
- customer.subscription.updated — plan changes, trial end
- customer.subscription.deleted — cancellation

---

## Sitemap Structure

- / (home)
- /pricing
- /dashboard (auth required)
- /auth/signup
- /auth/login
- /blog
- /blog/[slug]
- /llms.txt
- /llms-full.txt

Each page is available under /fr and /en prefixes.

---

## Contact

Visit ${appUrl} for more information.
`;

  return new NextResponse(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
