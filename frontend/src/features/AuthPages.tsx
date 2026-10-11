import { ArrowRight, LoaderCircle, LockKeyhole, UserPlus } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { safeNext } from '../components/RouteGuards';
import { useAuth } from '../lib/auth';

const USERNAME_PATTERN = /^[A-Za-z0-9_.-]{3,80}$/;

function useSubmit(action: () => Promise<void>) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Something went wrong. Try again.');
    } finally {
      setPending(false);
    }
  };
  return { error, setError, pending, submit };
}

export function LoginPage() {
  const { login, sessionMessage } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const { error, pending, submit } = useSubmit(async () => {
    await login(username.trim(), password);
    navigate(safeNext(params.get('next')), { replace: true });
  });
  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit} noValidate={false}>
        <div className="auth-card-heading"><span className="auth-icon"><LockKeyhole size={18} /></span><div><h1>Sign in</h1><p>Access your research workspace.</p></div></div>
        {sessionMessage && <p className="auth-notice" role="status">{sessionMessage}</p>}
        <label>Username<input name="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} maxLength={80} autoFocus /></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} maxLength={256} /></label>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button className="primary-button large" disabled={pending}>{pending && <LoaderCircle className="spin" size={15} />} Sign in <ArrowRight size={15} /></button>
        <p className="auth-switch">New to NyayaAI? <Link to={`/register${params.get('next') ? `?next=${encodeURIComponent(params.get('next') ?? '')}` : ''}`}>Create an account</Link></p>
      </form>
    </div>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const { error, setError, pending, submit } = useSubmit(async () => {
    await register(username.trim(), password);
    navigate(safeNext(params.get('next')), { replace: true });
  });
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!USERNAME_PATTERN.test(username.trim())) {
      setError('Usernames are 3–80 characters: letters, numbers, dots, dashes, or underscores.');
      return;
    }
    if (password.length < 8) {
      setError('Passwords must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('The passwords do not match.');
      return;
    }
    void submit(event);
  };
  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="auth-card-heading"><span className="auth-icon"><UserPlus size={18} /></span><div><h1>Create an account</h1><p>New accounts have the researcher role.</p></div></div>
        <label>Username<input name="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} maxLength={80} pattern="[A-Za-z0-9_.\-]+" aria-describedby="username-hint" autoFocus /></label>
        <small id="username-hint" className="field-hint">Letters, numbers, dots, dashes, and underscores.</small>
        <label>Password<input name="password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} maxLength={256} aria-describedby="password-hint" /></label>
        <small id="password-hint" className="field-hint">At least 8 characters. A longer passphrase is stronger.</small>
        <label>Confirm password<input name="confirm" type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required minLength={8} maxLength={256} /></label>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button className="primary-button large" disabled={pending}>{pending && <LoaderCircle className="spin" size={15} />} Create account <ArrowRight size={15} /></button>
        <p className="auth-switch">Already registered? <Link to="/login">Sign in</Link></p>
      </form>
    </div>
  );
}
