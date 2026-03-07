import type { SoftwareApplication, WithContext } from 'schema-dts';

interface SchemaOrgProps {
  name: string;
  description: string;
  url: string;
  price: string;
  currency?: string;
}

export function SchemaOrg({
  name,
  description,
  url,
  price,
  currency = 'CAD',
}: SchemaOrgProps) {
  const schema: WithContext<SoftwareApplication> = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name,
    description,
    url,
    applicationCategory: 'BusinessApplication',
    operatingSystem: 'Web',
    offers: {
      '@type': 'Offer',
      price,
      priceCurrency: currency,
      url,
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
