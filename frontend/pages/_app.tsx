import '../styles/globals.css'
import type { AppProps } from 'next/app'
import { IBM_Plex_Sans } from 'next/font/google'
import { DashboardProvider } from '../state/dashboard/dashboardContext'
import { AuthGuard } from '../components/layout/AuthGuard'
import { AuthProvider } from '../state/auth/AuthContext'

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  weight: ['400', '500', '600', '700'],
})

export default function App({ Component, pageProps }: AppProps) {
  return (
    <main className={`${ibmPlexSans.className} ${ibmPlexSans.variable}`}>
      <AuthProvider>
        <AuthGuard>
          <DashboardProvider>
            <Component {...pageProps} />
          </DashboardProvider>
        </AuthGuard>
      </AuthProvider>
    </main>
  )
}
