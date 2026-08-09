import type { Metadata } from 'next';

import AuthBadge from '@/components/auth/AuthBadge';

import './globals.css';

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
      <body>
        <AuthBadge />
        {children}
      </body>
    </html>
  );
}
