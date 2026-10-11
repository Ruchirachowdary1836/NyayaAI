import { Compass } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../lib/auth';

export function NotFoundPage() {
  const { status } = useAuth();
  return (
    <div className="auth-page">
      <div className="empty-state-card not-found">
        <Compass size={26} />
        <h1>Page not found</h1>
        <p>The page you requested does not exist or has moved.</p>
        <Link className="primary-button" to={status === 'authenticated' ? '/dashboard' : '/'}>
          {status === 'authenticated' ? 'Back to your dashboard' : 'Back to the home page'}
        </Link>
      </div>
    </div>
  );
}
