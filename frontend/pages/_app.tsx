import '../styles/globals.css'
import type { AppProps } from 'next/app'
import { IBM_Plex_Sans } from 'next/font/google'
import { DashboardProvider } from '../state/dashboardContext'

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  weight: ['400', '500', '600', '700'],
})

export default function App({ Component, pageProps }: AppProps) {
  return (
    <main className={ibmPlexSans.variable}>
      <DashboardProvider>
        <Component {...pageProps} />
      </DashboardProvider>
    </main>
  )
}
