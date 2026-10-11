import { CheckCircle2, TriangleAlert, X } from 'lucide-react';
import { createContext, useCallback, useContext, useRef, useState } from 'react';
import type { ReactNode } from 'react';

type Tone = 'success' | 'error';
interface Toast { id: number; tone: Tone; message: string }

const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const dismiss = (id: number) => setToasts((current) => current.filter((toast) => toast.id !== id));
  const notify = useCallback((message: string, tone: Tone = 'success') => {
    const id = nextId.current++;
    setToasts((current) => [...current.slice(-3), { id, tone, message }]);
    window.setTimeout(() => dismiss(id), 5000);
  }, []);
  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toast-region" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.tone}`} role={toast.tone === 'error' ? 'alert' : 'status'}>
            {toast.tone === 'success' ? <CheckCircle2 size={16} /> : <TriangleAlert size={16} />}
            <span>{toast.message}</span>
            <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(toast.id)}><X size={14} /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
