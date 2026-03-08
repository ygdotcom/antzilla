import { useTranslations } from 'next-intl';
import { LanguageToggle } from '@/components/language-toggle';
import { Receipt, Zap, Shield, ArrowRight, Check } from 'lucide-react';

export default function LandingPage() {
  const t = useTranslations();

  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-gray-100/80 bg-white/80 backdrop-blur-lg">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-white text-sm font-bold">
              {t('common.appName').charAt(0)}
            </div>
            <span className="text-lg font-semibold tracking-tight text-gray-900">
              {t('common.appName')}
            </span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#features" className="hidden text-sm text-gray-500 transition hover:text-gray-900 sm:block">
              {t('nav.features') || 'Features'}
            </a>
            <a href="/pricing" className="hidden text-sm text-gray-500 transition hover:text-gray-900 sm:block">
              {t('nav.pricing')}
            </a>
            <a href="/auth/login" className="text-sm text-gray-500 transition hover:text-gray-900">
              {t('nav.login')}
            </a>
            <a
              href="/auth/signup"
              className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:opacity-90"
            >
              {t('nav.signup')}
            </a>
            <LanguageToggle />
          </div>
        </nav>
      </header>

      <main className="flex flex-1 flex-col">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div className="absolute inset-0 -z-10 bg-[radial-gradient(45%_40%_at_50%_60%,var(--color-primary-50,#eff6ff)_0%,transparent_100%)]" />
          <div className="mx-auto max-w-4xl px-6 pb-24 pt-20 text-center sm:pt-28">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-4 py-1.5 text-sm font-medium text-primary">
              <Zap className="h-3.5 w-3.5" />
              {t('hero.badge') || t('common.tagline')}
            </div>
            <h1 className="mx-auto max-w-3xl text-4xl font-bold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl lg:text-6xl">
              {t('hero.title') || t('common.appName')}
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-gray-500">
              {t('hero.subtitle') || t('common.tagline')}
            </p>
            <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
              <a
                href="/auth/signup"
                className="group inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition hover:shadow-xl hover:shadow-primary/30"
              >
                {t('auth.signupCta')}
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </a>
              <a
                href="#demo"
                className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-6 py-3 text-sm font-medium text-gray-700 transition hover:border-gray-300 hover:bg-gray-50"
              >
                {t('hero.demo') || 'See how it works'}
              </a>
            </div>
            <p className="mt-4 text-xs text-gray-400">
              {t('hero.noCard') || 'No credit card required · 14-day free trial'}
            </p>
          </div>
        </section>

        {/* Social Proof */}
        <section className="border-y border-gray-100 bg-gray-50/50 py-10">
          <div className="mx-auto max-w-4xl px-6 text-center">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-400">
              {t('social.trusted') || 'Trusted by Canadian businesses'}
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-12 gap-y-4 opacity-40">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-6 w-20 rounded bg-gray-300" />
              ))}
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="py-24">
          <div className="mx-auto max-w-6xl px-6">
            <div className="text-center">
              <p className="text-sm font-semibold uppercase tracking-wider text-primary">
                {t('features.label') || 'Features'}
              </p>
              <h2 className="mt-3 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
                {t('features.title') || 'Everything you need'}
              </h2>
              <p className="mx-auto mt-4 max-w-xl text-gray-500">
                {t('features.subtitle') || 'Built for Canadian businesses, designed with care.'}
              </p>
            </div>
            <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              {[
                { icon: Receipt, title: t('features.f1_title') || 'Feature 1', desc: t('features.f1_desc') || 'Description placeholder' },
                { icon: Shield, title: t('features.f2_title') || 'Feature 2', desc: t('features.f2_desc') || 'Description placeholder' },
                { icon: Zap, title: t('features.f3_title') || 'Feature 3', desc: t('features.f3_desc') || 'Description placeholder' },
              ].map((f, i) => (
                <div key={i} className="group relative rounded-2xl border border-gray-100 bg-white p-8 transition hover:border-primary/20 hover:shadow-lg hover:shadow-primary/5">
                  <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary transition group-hover:bg-primary group-hover:text-white">
                    <f.icon className="h-6 w-6" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-gray-500">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How It Works */}
        <section id="demo" className="border-t border-gray-100 bg-gray-50/50 py-24">
          <div className="mx-auto max-w-4xl px-6">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight text-gray-900">
                {t('howItWorks.title') || 'How it works'}
              </h2>
              <p className="mt-4 text-gray-500">
                {t('howItWorks.subtitle') || 'Get started in under 2 minutes'}
              </p>
            </div>
            <div className="mt-16 grid gap-12 md:grid-cols-3">
              {[1, 2, 3].map((step) => (
                <div key={step} className="text-center">
                  <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
                    {step}
                  </div>
                  <h3 className="font-semibold text-gray-900">
                    {t(`howItWorks.step${step}_title`) || `Step ${step}`}
                  </h3>
                  <p className="mt-2 text-sm text-gray-500">
                    {t(`howItWorks.step${step}_desc`) || 'Step description placeholder'}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="py-24">
          <div className="mx-auto max-w-3xl px-6 text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              {t('cta.title') || t('pricing.title')}
            </h2>
            <p className="mt-4 text-lg text-gray-500">
              {t('cta.subtitle') || t('pricing.subtitle')}
            </p>
            <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
              <a
                href="/auth/signup"
                className="group inline-flex items-center gap-2 rounded-full bg-primary px-8 py-3.5 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition hover:shadow-xl"
              >
                {t('auth.signupCta')}
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </a>
            </div>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-gray-400">
              <span className="flex items-center gap-1.5"><Check className="h-4 w-4 text-green-500" /> {t('cta.check1') || '14-day free trial'}</span>
              <span className="flex items-center gap-1.5"><Check className="h-4 w-4 text-green-500" /> {t('cta.check2') || 'No credit card'}</span>
              <span className="flex items-center gap-1.5"><Check className="h-4 w-4 text-green-500" /> {t('cta.check3') || 'Cancel anytime'}</span>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-100 bg-gray-50/30 py-12">
        <div className="mx-auto max-w-6xl px-6">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded bg-primary text-xs font-bold text-white">
                {t('common.appName').charAt(0)}
              </div>
              <span className="text-sm font-medium text-gray-900">{t('common.appName')}</span>
            </div>
            <div className="flex gap-6 text-sm text-gray-400">
              <a href="/privacy" className="transition hover:text-gray-600">{t('legal.privacy')}</a>
              <a href="/terms" className="transition hover:text-gray-600">{t('legal.terms')}</a>
            </div>
          </div>
          <p className="mt-8 text-center text-xs text-gray-400">
            © {new Date().getFullYear()} {t('common.appName')}. {t('common.tagline')}
          </p>
        </div>
      </footer>
    </div>
  );
}
