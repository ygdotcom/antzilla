import { useTranslations } from 'next-intl';
import { LanguageToggle } from '@/components/language-toggle';

export default function LandingPage() {
  const t = useTranslations();

  return (
    <div className="flex min-h-screen flex-col">
      {/* Nav */}
      <header className="border-b border-gray-100">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <span className="text-xl font-bold">{t('common.appName')}</span>
          <div className="flex items-center gap-4">
            <a
              href="/pricing"
              className="text-sm text-gray-600 hover:text-gray-900"
            >
              {t('nav.pricing')}
            </a>
            <a
              href="/auth/login"
              className="text-sm text-gray-600 hover:text-gray-900"
            >
              {t('nav.login')}
            </a>
            <a
              href="/auth/signup"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              {t('nav.signup')}
            </a>
            <LanguageToggle />
          </div>
        </nav>
      </header>

      {/* Hero */}
      <main className="flex flex-1 flex-col">
        <section className="mx-auto flex max-w-4xl flex-col items-center px-6 pb-20 pt-24 text-center">
          <h1 className="text-5xl font-bold leading-tight tracking-tight text-gray-900 sm:text-6xl">
            {t('common.appName')}
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-gray-600">
            {t('common.tagline')}
          </p>
          <div className="mt-10 flex gap-4">
            <a
              href="/auth/signup"
              className="rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white shadow-sm hover:bg-blue-700"
            >
              {t('auth.signupCta')}
            </a>
            <a
              href="/pricing"
              className="rounded-lg border border-gray-300 px-6 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              {t('nav.pricing')}
            </a>
          </div>
        </section>

        {/* Features */}
        <section className="border-t border-gray-100 bg-gray-50 py-20">
          <div className="mx-auto max-w-6xl px-6">
            <h2 className="text-center text-3xl font-bold text-gray-900">
              {t('common.tagline')}
            </h2>
            <div className="mt-12 grid gap-8 md:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="rounded-xl border border-gray-200 bg-white p-6"
                >
                  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100 text-blue-600">
                    ★
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900">
                    Feature {i}
                  </h3>
                  <p className="mt-2 text-sm text-gray-600">
                    Feature description placeholder — the Builder agent will
                    populate this with real copy from the Scout Report.
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Pricing CTA */}
        <section className="py-20">
          <div className="mx-auto max-w-3xl px-6 text-center">
            <h2 className="text-3xl font-bold text-gray-900">
              {t('pricing.title')}
            </h2>
            <p className="mt-4 text-gray-600">{t('pricing.subtitle')}</p>
            <a
              href="/pricing"
              className="mt-8 inline-block rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white hover:bg-blue-700"
            >
              {t('nav.pricing')}
            </a>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-100 py-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 text-sm text-gray-500">
          <span>
            © {new Date().getFullYear()} {t('common.appName')}
          </span>
          <div className="flex gap-4">
            <a href="/privacy" className="hover:text-gray-700">
              {t('legal.privacy')}
            </a>
            <a href="/terms" className="hover:text-gray-700">
              {t('legal.terms')}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
