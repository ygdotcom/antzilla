import { NextResponse } from 'next/server';

export async function GET() {
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://example.com';

  const body = `# Robots.txt — AI-friendly
# We welcome all crawlers, including AI agents.

User-agent: *
Allow: /

# AI crawlers explicitly allowed
User-agent: GPTBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: Amazonbot
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Bytespider
Allow: /

# LLM-optimized resources
# ${appUrl}/llms.txt — short summary for LLMs
# ${appUrl}/llms-full.txt — comprehensive documentation for LLMs

Sitemap: ${appUrl}/sitemap.xml
`;

  return new NextResponse(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
