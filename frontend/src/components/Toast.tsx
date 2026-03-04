import { useEffect } from "react";

interface ToastProps {
  message: string;
  onDismiss: () => void;
}

/** Floating error/info strip. Auto-dismisses after 4 s. */
export function Toast({ message, onDismiss }: ToastProps) {
  useEffect(() => {
    const id = setTimeout(onDismiss, 4000);
    return () => clearTimeout(id);
  }, [message, onDismiss]);

  return (
    <div className="toast" role="alert">
      {message}
    </div>
  );
}
