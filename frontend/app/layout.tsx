import type { Metadata, Viewport } from 'next'
import './globals.css'
import { AuthProvider } from '@/lib/auth-context'
import SmoothScroll from '@/components/smooth-scroll'

export const metadata: Metadata = {
  title: 'SupportNova — ResponseX Intelligence',
  description:
    'The enterprise accountability layer for customer support AI. Dual-pipeline generative reasoning and deterministic ground-truth validation.',
  icons: { icon: '/favicon.ico' },
}

export const viewport: Viewport = {
  themeColor: '#07080d',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <AuthProvider>
          <SmoothScroll />
          {children}
        </AuthProvider>
      </body>
    </html>
  )
}
