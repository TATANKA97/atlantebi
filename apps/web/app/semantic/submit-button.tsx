"use client";

import { useFormStatus } from "react-dom";

export function SubmitButton({
  ariaLabel,
  className,
  idleLabel,
  pendingLabel
}: {
  ariaLabel?: string;
  className: string;
  idleLabel: string;
  pendingLabel: string;
}) {
  const { pending } = useFormStatus();

  return (
    <button
      aria-label={ariaLabel}
      className={className}
      disabled={pending}
      type="submit"
    >
      {pending ? pendingLabel : idleLabel}
    </button>
  );
}
