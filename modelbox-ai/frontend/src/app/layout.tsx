import type { Metadata } from 'next';

import AuthBadge from '@/components/auth/AuthBadge';
import { cssVariableBlock } from '@/styles/cssVars';

import './globals.css';
import '@/styles/ui.css';

export const metadata: Metadata = {
  title: 'ModelBox AI',
  description: 'LLM-agnostic enterprise data modeling workspace.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        {/*
          The token values, emitted as CSS custom properties for `ui.css` to
          read. Rendered from `tokens.ts` rather than checked in as a stylesheet
          so there is no copy to drift: a token edit reaches the stylesheet on
          the next render, and `ui.css.test.ts` fails if the stylesheet names a
          variable this block does not emit.
        */}
        <style dangerouslySetInnerHTML={{ __html: cssVariableBlock() }} />
      </head>
      <body>
        <AuthBadge />
        {children}
      </body>
    </html>
  );
}
