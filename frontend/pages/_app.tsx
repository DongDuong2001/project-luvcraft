import '../styles/globals.css'
import type { AppProps } from 'next/app'
import { DashboardProvider } from '../state/dashboardContext'

export default function App({ Component, pageProps }: AppProps) {
  return (
    <DashboardProvider>
      <Component {...pageProps} />
    </DashboardProvider>
  )
}
