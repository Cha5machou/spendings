import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

/** Sign-in with Google through Firebase Auth. Disabled (no sign-in at all) unless the server says
 *  auth_enabled, so local use stays frictionless. The Firebase SDK is only loaded when needed. */

interface AuthContextValue {
  enabled: boolean
  email: string | null
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({ enabled: false, email: null, signOut: async () => {} })
export const useAuth = () => useContext(AuthContext)

let tokenProvider: (() => Promise<string | null>) | null = null

/** Bearer token for API calls, or null when signed out / auth disabled. */
export async function authToken(): Promise<string | null> {
  return tokenProvider ? tokenProvider() : null
}

interface PublicConfig {
  auth_enabled: boolean
  firebase: { apiKey: string; authDomain: string; projectId: string } | null
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'loading' | 'signed-out' | 'ready' | 'error'>('loading')
  const [enabled, setEnabled] = useState(false)
  const [email, setEmail] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [actions, setActions] = useState<{ signIn: () => Promise<void>; signOut: () => Promise<void> } | null>(null)

  useEffect(() => {
    let unsubscribe: (() => void) | undefined
    fetch('/api/config')
      .then((response) => response.json() as Promise<PublicConfig>)
      .then(async (config) => {
        if (!config.auth_enabled || !config.firebase) {
          setState('ready')
          return
        }
        setEnabled(true)
        const [{ initializeApp }, firebaseAuth] = await Promise.all([import('firebase/app'), import('firebase/auth')])
        const auth = firebaseAuth.getAuth(initializeApp(config.firebase))
        tokenProvider = async () => (auth.currentUser ? auth.currentUser.getIdToken() : null)
        setActions({
          signIn: async () => {
            setMessage(null)
            try {
              await firebaseAuth.signInWithPopup(auth, new firebaseAuth.GoogleAuthProvider())
            } catch (error) {
              setMessage((error as Error).message)
            }
          },
          signOut: () => firebaseAuth.signOut(auth),
        })
        unsubscribe = firebaseAuth.onAuthStateChanged(auth, async (user) => {
          if (!user) {
            setEmail(null)
            setState('signed-out')
            return
          }
          // Ask the server whether this account is allowed before showing the app.
          const token = await user.getIdToken()
          const response = await fetch('/api/accounts', { headers: { Authorization: `Bearer ${token}` } })
          if (response.status === 403) {
            setMessage(`${user.email} is not allowed to use this app.`)
            await firebaseAuth.signOut(auth)
            return
          }
          setEmail(user.email)
          setState('ready')
        })
      })
      .catch((error: Error) => {
        setMessage(error.message)
        setState('error')
      })
    return () => unsubscribe?.()
  }, [])

  if (state === 'loading') return <p className="muted" style={{ padding: 24 }}>Loading…</p>
  if (state === 'error') return <div className="alert error" style={{ margin: 24 }}>Could not start: {message}</div>
  if (state === 'signed-out') {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '100vh', padding: 16 }}>
        <div className="card" style={{ maxWidth: 360, textAlign: 'center' }}>
          <h1>Spendings</h1>
          <p className="muted small">Private app. Sign in with the Google account that has been given access.</p>
          {message && <div className="alert error">{message}</div>}
          <button className="primary" onClick={() => actions?.signIn()}>Sign in with Google</button>
        </div>
      </div>
    )
  }
  return <AuthContext.Provider value={{ enabled, email, signOut: async () => { await actions?.signOut() } }}>{children}</AuthContext.Provider>
}
