import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { json, mockApi, renderApp, researcher } from '../test/harness';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('authentication and route protection', () => {
  it('redirects anonymous visitors from protected pages to sign in', async () => {
    mockApi();
    renderApp('/library', { signedIn: false });
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('signs in, stores the session, and returns to the requested page', async () => {
    const { calls } = mockApi(
      (url, init) => url.pathname === '/api/v1/auth/token' && init.method === 'POST'
        ? json({ access_token: 'issued-token', token_type: 'bearer', role: 'user', username: 'researcher', expires_in: 3600 })
        : undefined,
      (url) => url.pathname === '/api/v1/experiments/runs' ? json({ experiments: [], total: 0 }) : undefined,
      (url) => url.pathname === '/api/v1/experiments/benchmarks' ? json([]) : undefined,
    );
    window.history.replaceState(null, '');
    renderApp('/login?next=%2Fexperiments', { signedIn: false });
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'researcher' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'long-password' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('heading', { name: 'Measure what matters.' })).toBeInTheDocument();
    expect(window.localStorage.getItem('nyayaai-token')).toBe('issued-token');
    const login = calls.find((call) => call.url.pathname === '/api/v1/auth/token');
    expect(JSON.parse(String(login?.init.body))).toEqual({ username: 'researcher', password: 'long-password' });
  });

  it('shows the server error for rejected credentials', async () => {
    mockApi((url) => url.pathname === '/api/v1/auth/token' ? json({ detail: 'Incorrect username or password' }, 401) : undefined);
    renderApp('/login', { signedIn: false });
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'researcher' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect username or password');
    expect(window.localStorage.getItem('nyayaai-token')).toBeNull();
  });

  it('validates registration input before calling the API', async () => {
    const { calls } = mockApi();
    renderApp('/register', { signedIn: false });
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'new_user' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'long-password' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'different-password' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The passwords do not match.');
    expect(calls.some((call) => call.url.pathname === '/api/v1/auth/register')).toBe(false);
  });

  it('restores a session after refresh and signs out on an expired token', async () => {
    mockApi((url) => url.pathname === '/api/v1/auth/me' ? json({ detail: 'Invalid or expired access token' }, 401) : undefined);
    renderApp('/dashboard');
    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
    expect(window.localStorage.getItem('nyayaai-token')).toBeNull();
  });

  it('keeps non-admin users out of the admin page', async () => {
    mockApi();
    renderApp('/admin');
    expect(await screen.findByText('Administrator access required')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /administration/i })).not.toBeInTheDocument();
  });

  it('logs out through the API and clears the session', async () => {
    const { calls } = mockApi((url) => url.pathname === '/api/v1/auth/logout' ? new Response(null, { status: 204 }) : undefined);
    renderApp('/dashboard');
    await screen.findByText(`Welcome, ${researcher.username}.`);
    fireEvent.click(screen.getByRole('button', { name: /sign out/i }));
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    await waitFor(() => expect(calls.some((call) => call.url.pathname === '/api/v1/auth/logout')).toBe(true));
    expect(window.localStorage.getItem('nyayaai-token')).toBeNull();
  });
});

describe('post-login redirect safety', () => {
  it('only allows same-app paths', async () => {
    const { safeNext } = await import('../components/RouteGuards');
    expect(safeNext('/experiments/abc?x=1')).toBe('/experiments/abc?x=1');
    for (const unsafe of ['//evil.example', String.raw`/\evil.example`, 'https://evil.example', String.raw`/ok\..`, null, '']) {
      expect(safeNext(unsafe)).toBe('/dashboard');
    }
  });
});
