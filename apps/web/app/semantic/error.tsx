"use client";

export default function SemanticWorkspaceError({
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="min-h-screen px-4 py-10 sm:px-8">
      <section className="mx-auto max-w-3xl border-y border-[color:var(--border)] py-10">
        <h1 className="text-xl font-semibold">Semantic Workspace non disponibile</h1>
        <p className="mt-3 text-sm text-[color:var(--muted)]">
          Il caricamento non e stato completato. Riprova; se il problema persiste,
          verifica lo stato della connessione e degli artifact semantici.
        </p>
        <button
          className="mt-5 border border-[color:var(--accent)] px-4 py-2 text-sm font-medium"
          onClick={reset}
          type="button"
        >
          Riprova
        </button>
      </section>
    </main>
  );
}
