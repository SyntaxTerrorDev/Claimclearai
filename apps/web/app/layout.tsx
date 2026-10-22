import { Geist_Mono, Montserrat, Playfair_Display } from 'next/font/google'
import type { Metadata, Viewport } from 'next'
import './globals.css'
const montserrat = Montserrat({ variable: '--font-montserrat', subsets: ['latin'], weight: ['400', '500', '600', '700'] })
const playfair = Playfair_Display({ variable: '--font-playfair', subsets: ['latin'], weight: ['500', '600', '700'], style: ['normal', 'italic'] })
const plexMono = Geist_Mono({ variable: '--font-plex-mono', subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'ClaimClear — Catch claim errors before submission',
  description: 'Audit clinical records and draft insurance claims against known rejection patterns before submission.',
}

export const viewport: Viewport = {
  colorScheme: 'dark light',
  themeColor: '#0D1114',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="bg-background">
      <body className={`${montserrat.variable} ${playfair.variable} ${plexMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  )
}
