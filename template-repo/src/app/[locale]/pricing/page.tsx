import { getTranslations } from 'next-intl/server';
import { PricingTable } from '@/components/pricing-table';

export default async function PricingPage() {
  const t = await getTranslations('pricing');

  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="mb-12 text-center">
          <h1 className="text-4xl font-bold text-gray-900">{t('title')}</h1>
          <p className="mt-4 text-lg text-gray-600">{t('subtitle')}</p>
        </div>
        <PricingTable />
      </div>
    </div>
  );
}
