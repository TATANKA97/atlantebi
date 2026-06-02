import { ENGINE_VALUES } from "@atlantebi/contracts";

export default function Home() {
  return (
    <main className="min-h-screen px-8 py-10">
      <section className="mx-auto flex max-w-3xl flex-col gap-6">
        <div>
          <h1 className="text-4xl font-semibold tracking-normal">Atlante BI</h1>
          <p className="mt-3 text-base leading-7 text-[color:var(--muted)]">
            Fondazione tecnica attiva. Questo step espone solo confini di
            prodotto, contract e healthcheck.
          </p>
        </div>
        <dl className="grid gap-3 border-t border-[color:var(--border)] pt-6 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-[color:var(--muted)]">Customer DB engines</dt>
            <dd className="mt-1 font-medium">{ENGINE_VALUES.join(", ")}</dd>
          </div>
          <div>
            <dt className="text-[color:var(--muted)]">Customer secrets</dt>
            <dd className="mt-1 font-medium">GCP Secret Manager reference only</dd>
          </div>
        </dl>
      </section>
    </main>
  );
}
