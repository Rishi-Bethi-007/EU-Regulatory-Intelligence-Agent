import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { supabase } from '../lib/supabase'

export default function AuthPage() {
  const { signIn, signUp } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'signin' | 'signup'>('signin')

  // Sign in state
  const [siEmail,   setSiEmail]   = useState('')
  const [siPass,    setSiPass]    = useState('')
  const [siConsent, setSiConsent] = useState(false)
  const [siError,   setSiError]   = useState('')
  const [siLoading, setSiLoading] = useState(false)

  // Sign up state
  const [suEmail,    setSuEmail]    = useState('')
  const [suPass,     setSuPass]     = useState('')
  const [suPass2,    setSuPass2]    = useState('')
  const [suConsent,  setSuConsent]  = useState(false)
  const [suError,    setSuError]    = useState('')
  const [suLoading,  setSuLoading]  = useState(false)
  const [needsVerify, setNeedsVerify] = useState(false)
  const [verifyEmail, setVerifyEmail] = useState('')

  // Google OAuth — Supabase handles the entire redirect flow automatically
  const handleGoogleSignIn = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/`,
      },
    })
    if (error) console.error('Google OAuth error:', error.message)
    // No further action needed — Supabase redirects to Google,
    // then back to redirectTo, and onAuthStateChange fires automatically.
  }

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!siConsent) { setSiError('You must accept the consent checkbox.'); return }
    setSiError(''); setSiLoading(true)
    try {
      await signIn(siEmail, siPass)
      navigate('/')
    } catch (err: any) {
      const msg = err?.message ?? String(err)
      if (msg.includes('Invalid') || msg.includes('invalid_credentials')) {
        setSiError('Incorrect email or password.')
      } else if (msg.includes('Email not confirmed') || msg.includes('email_not_confirmed')) {
        setSiError('Email not verified yet. Check your inbox and click the verification link.')
      } else {
        setSiError(msg)
      }
    } finally {
      setSiLoading(false)
    }
  }

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!suConsent) { setSuError('You must accept the consent checkbox.'); return }
    if (suPass.length < 8) { setSuError('Password must be at least 8 characters.'); return }
    if (suPass !== suPass2) { setSuError('Passwords do not match.'); return }
    setSuError(''); setSuLoading(true)
    try {
      const { needsVerification } = await signUp(suEmail, suPass)
      if (needsVerification) {
        setVerifyEmail(suEmail)
        setNeedsVerify(true)
      } else {
        navigate('/')
      }
    } catch (err: any) {
      const msg = err?.message ?? String(err)
      if (msg.includes('already registered') || msg.includes('already exists')) {
        setSuError('An account with this email already exists. Please sign in.')
      } else {
        setSuError(msg)
      }
    } finally {
      setSuLoading(false)
    }
  }

  // Email verification pending screen
  if (needsVerify) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md card text-center">
        <div className="text-5xl mb-4">📧</div>
        <h2 className="text-xl font-bold text-green-400 mb-2">Check your email</h2>
        <p className="text-gray-400 mb-1">A verification link has been sent to:</p>
        <p className="text-white font-semibold text-lg mb-6">{verifyEmail}</p>
        <div className="bg-gray-800 rounded-lg p-4 text-sm text-gray-300 text-left mb-6">
          <strong className="text-white">Click the link in the email</strong> to verify your account,
          then come back here and sign in.<br /><br />
          Can't find it? Check your spam/junk folder.
        </div>
        <div className="flex gap-3">
          <button className="btn-primary flex-1"
            onClick={() => { setNeedsVerify(false); setTab('signin') }}>
            ✅ I've verified — Sign in
          </button>
          <button className="btn-secondary" onClick={() => setNeedsVerify(false)}>
            ← Back
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">

        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-6xl mb-3">🇪🇺</div>
          <h1 className="text-2xl font-bold text-white">EU Regulatory Intelligence Agent</h1>
          <p className="text-gray-400 mt-1">Multi-agent EU AI Act and GDPR compliance research</p>
        </div>

        <div className="card">
          {/* Google sign-in button — shown above tabs, works for both sign in and sign up */}
          <button
            onClick={handleGoogleSignIn}
            className="w-full flex items-center justify-center gap-3 bg-white hover:bg-gray-100
                       text-gray-800 font-semibold px-4 py-2.5 rounded-lg transition-colors mb-4"
          >
            {/* Google SVG logo */}
            <svg width="18" height="18" viewBox="0 0 18 18">
              <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
              <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
              <path fill="#FBBC05" d="M3.964 10.706A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.706V4.962H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.038l3.007-2.332z"/>
              <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.962L3.964 7.294C4.672 5.163 6.656 3.58 9 3.58z"/>
            </svg>
            Continue with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-px bg-gray-700" />
            <span className="text-xs text-gray-500">or use email</span>
            <div className="flex-1 h-px bg-gray-700" />
          </div>

          {/* Email/password tabs */}
          <div className="flex gap-1 bg-gray-800 rounded-lg p-1 mb-6">
            {(['signin', 'signup'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
                  tab === t ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'
                }`}
              >
                {t === 'signin' ? '🔑 Sign in' : '✨ Create account'}
              </button>
            ))}
          </div>

          {/* Sign in */}
          {tab === 'signin' && (
            <form onSubmit={handleSignIn} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Email</label>
                <input className="input" type="email" placeholder="you@example.com"
                  value={siEmail} onChange={e => setSiEmail(e.target.value)} required />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Password</label>
                <input className="input" type="password" placeholder="Your password"
                  value={siPass} onChange={e => setSiPass(e.target.value)} required />
              </div>
              <div className="bg-gray-800 rounded-lg p-3 border border-gray-700">
                <label className="flex items-start gap-2 cursor-pointer">
                  <input type="checkbox" checked={siConsent}
                    onChange={e => setSiConsent(e.target.checked)} className="mt-0.5 rounded" />
                  <span className="text-xs text-gray-300">
                    <strong className="text-white">Data processing consent (GDPR Article 6)</strong><br />
                    I consent to this system processing my research queries and storing results
                    to provide regulatory compliance guidance.
                  </span>
                </label>
              </div>
              {siError && <p className="text-red-400 text-sm">{siError}</p>}
              <button type="submit" disabled={siLoading || !siConsent} className="btn-primary w-full">
                {siLoading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>
          )}

          {/* Sign up */}
          {tab === 'signup' && (
            <form onSubmit={handleSignUp} className="space-y-4">
              <p className="text-sm text-gray-400">
                Create a free account to start researching EU AI Act and GDPR compliance.
              </p>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Email</label>
                <input className="input" type="email" placeholder="you@example.com"
                  value={suEmail} onChange={e => setSuEmail(e.target.value)} required />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Password</label>
                <input className="input" type="password" placeholder="At least 8 characters"
                  value={suPass} onChange={e => setSuPass(e.target.value)} required />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Confirm password</label>
                <input className="input" type="password" placeholder="Repeat password"
                  value={suPass2} onChange={e => setSuPass2(e.target.value)} required />
              </div>
              <div className="bg-gray-800 rounded-lg p-3 border border-gray-700">
                <label className="flex items-start gap-2 cursor-pointer">
                  <input type="checkbox" checked={suConsent}
                    onChange={e => setSuConsent(e.target.checked)} className="mt-0.5 rounded" />
                  <span className="text-xs text-gray-300">
                    <strong className="text-white">Data processing consent (GDPR Article 6)</strong><br />
                    I consent to this system processing my research queries and storing results
                    to provide regulatory compliance guidance.
                  </span>
                </label>
              </div>
              {suError && <p className="text-red-400 text-sm">{suError}</p>}
              <button type="submit" disabled={suLoading || !suConsent} className="btn-primary w-full">
                {suLoading ? 'Creating account...' : 'Create account'}
              </button>
            </form>
          )}

          <p className="text-center text-xs text-gray-500 mt-4">
            Your data is processed under GDPR. See the <strong>EU Compliance</strong> page
            to access or erase your data at any time.
          </p>
        </div>
      </div>
    </div>
  )
}
