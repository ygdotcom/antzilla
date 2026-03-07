import Stripe from 'stripe';

export type Plan = 'free' | 'pro' | 'business';

export const PLAN_FEATURES: Record<Plan, string[]> = {
  free: [
    'Basic features',
    'Limited projects',
    'Community support',
  ],
  pro: [
    'All Free features',
    'Unlimited projects',
    'Priority support',
    'Advanced analytics',
    'Export & integrations',
  ],
  business: [
    'All Pro features',
    'Team collaboration',
    'Custom branding',
    'API access',
    'Dedicated support',
  ],
};

export function isFeatureAvailable(plan: Plan, feature: string): boolean {
  const features = PLAN_FEATURES[plan];
  if (!features) return false;
  return features.some((f) => f.toLowerCase().includes(feature.toLowerCase()));
}

let stripeInstance: Stripe | null = null;

export function getStripeInstance(): Stripe {
  const secret = process.env.STRIPE_SECRET_KEY;
  if (!secret) {
    throw new Error('STRIPE_SECRET_KEY is not set');
  }
  if (!stripeInstance) {
    stripeInstance = new Stripe(secret);
  }
  return stripeInstance;
}

export async function createCheckoutSession(
  userId: string,
  priceId: string,
  options?: { successUrl?: string; cancelUrl?: string; trialDays?: number }
): Promise<Stripe.Checkout.Session> {
  const stripe = getStripeInstance();
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';

  const session = await stripe.checkout.sessions.create({
    mode: 'subscription',
    payment_method_types: ['card'],
    line_items: [
      {
        price: priceId,
        quantity: 1,
      },
    ],
    success_url: options?.successUrl ?? `${appUrl}/dashboard?success=true`,
    cancel_url: options?.cancelUrl ?? `${appUrl}/pricing`,
    subscription_data: {
      trial_period_days: options?.trialDays ?? 14,
      metadata: { userId },
    },
    metadata: { userId },
    allow_promotion_codes: true,
  });

  return session;
}

export async function createPortalSession(customerId: string): Promise<Stripe.BillingPortal.Session> {
  const stripe = getStripeInstance();
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';

  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: `${appUrl}/dashboard`,
  });

  return session;
}
