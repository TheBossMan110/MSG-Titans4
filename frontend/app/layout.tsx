import type { Metadata, Viewport } from 'next'
import { Fraunces, Instrument_Sans, JetBrains_Mono } from 'next/font/google'
import './globals.css'
import { AuthProvider } from '@/lib/auth-context'
import SmoothScroll from '@/components/motion/smooth-scroll'
import { ToastProvider } from '@/components/ui/feedback'
import { ChatLauncher } from '@/components/app/chat'

// Three faces, one job each. Self-hosted through next/font: no layout shift,
// no request to a font CDN at runtime.
const fraunces = Fraunces({
  subsets: ['latin'],
  axes: ['opsz', 'SOFT'],
  style: ['normal', 'italic'],
  variable: '--font-fraunces',
  display: 'swap',
})

const instrument = Instrument_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-instrument',
  display: 'swap',
})

const jetbrains = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-jetbrains',
  display: 'swap',
})

export const metadata: Metadata = {
  title: {
    default: 'SupportNova — ResponseX Intelligence',
    template: '%s · SupportNova',
  },
  description:
    'AI understands every complaint. Independent rules verify every decision. Nothing reaches a customer that the second did not confirm.',
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : 'http://localhost:3000')),
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/icon.svg', type: 'image/svg+xml' },
      { url: '/brand/favicon-32.png', type: 'image/png', sizes: '32x32' },
      { url: '/brand/favicon-16.png', type: 'image/png', sizes: '16x16' },
      { url: '/brand/icon-192.png', type: 'image/png', sizes: '192x192' },
    ],
    apple: '/apple-touch-icon.png',
  },
  openGraph: {
    title: 'SupportNova — ResponseX Intelligence',
    description: 'AI understands every complaint. Independent rules verify every decision.',
    images: [{ url: '/brand/og.png', width: 1200, height: 630, alt: 'SupportNova' }],
    type: 'website',
  },
  twitter: { card: 'summary_large_image', images: ['/brand/og.png'] },
}

export const viewport: Viewport = {
  themeColor: '#f5f0e8',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${instrument.variable} ${jetbrains.variable}`}
      suppressHydrationWarning
    >
      <body suppressHydrationWarning>
        <AuthProvider>
          <ToastProvider>
            <SmoothScroll />
            {children}
            <ChatLauncher />
          </ToastProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
