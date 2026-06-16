import Link from "next/link";
import type { AIProviderSettingSummary } from "@atlantebi/contracts";

import { createAIProviderSettingAction } from "./actions";
import { SubmitButton } from "./submit-button";
import { WorkspaceTabs } from "./semantic-workspace";
import { listAIProviderSettings } from "../../lib/ai-provider-settings/service";
import {
  canManageSemanticLayer,
  getActiveTenantContext
} from "../../lib/tenant";

type AIProviderWorkspaceParams = {
  connection?: string;
  message?: string;
};

const MESSAGE_COPY: Record<string, string> = {
  ai_provider_forbidden: "Solo owner e admin possono configurare provider AI.",
  ai_provider_internal_error: "Operazione provider AI fallita.",
  ai_provider_rate_limited: "Troppe operazioni AI provider in corso.",
  ai_provider_save_failed: "Configurazione AI non salvata.",
  ai_provider_saved: "Configurazione AI salvata.",
  ai_provider_secret_manager_unconfigured:
    "GCP_PROJECT_ID richiesto per salvare API key AI.",
  invalid_ai_provider: "Configurazione provider AI non valida."
};

export async function AIProviderWorkspace({
  searchParams
}: {
  searchParams: AIProviderWorkspaceParams;
}) {
  const context = await getActiveTenantContext();
  const canManage = canManageSemanticLayer(context.role);
  const settings = await listAIProviderSettings({ context });
  const message = searchParams.message
    ? MESSAGE_COPY[searchParams.message] ?? searchParams.message
    : null;

  return (
    <main className="min-h-screen px-4 py-8 sm:px-8 sm:py-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-7">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal sm:text-3xl">
              AI Provider
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--muted)]">
              Configurazione BYOK tenant-scoped per generare proposte
              semantiche strutturate. Atlante non paga ne gestisce il billing
              dei token.
            </p>
          </div>
          <Link
            className="border border-[color:var(--border)] px-4 py-2 text-sm font-medium"
            href="/semantic"
          >
            Semantic Layer
          </Link>
        </header>

        <WorkspaceTabs active="ai-provider" {...(searchParams.connection ? { connectionId: searchParams.connection } : {})} />

        {message ? (
          <p
            aria-live="polite"
            className="border-l-2 border-[color:var(--accent)] py-2 pl-4 text-sm"
            role="status"
          >
            {message}
          </p>
        ) : null}

        <section className="border-t border-[color:var(--border)] pt-6">
          <h2 className="text-base font-semibold">Configurazioni salvate</h2>
          {settings.length === 0 ? (
            <p className="mt-3 text-sm text-[color:var(--muted)]">
              Nessun provider AI configurato.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                <thead className="text-[color:var(--muted)]">
                  <tr>
                    {[
                      "Nome",
                      "Provider",
                      "Modello",
                      "Thinking",
                      "Stato",
                      "Default"
                    ].map((label) => (
                      <th
                        className="border-b border-[color:var(--border)] py-2 pr-4 font-medium"
                        key={label}
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {settings.map((setting) => (
                    <tr key={setting.id}>
                      <td className="border-b border-[color:var(--border)] py-3 pr-4">
                        {setting.display_name}
                      </td>
                      <td className="border-b border-[color:var(--border)] py-3 pr-4">
                        {setting.provider}
                      </td>
                      <td className="border-b border-[color:var(--border)] py-3 pr-4">
                        {setting.model_id}
                      </td>
                      <td className="border-b border-[color:var(--border)] py-3 pr-4">
                        {thinkingLabel(setting.thinking)}
                      </td>
                      <td className="border-b border-[color:var(--border)] py-3 pr-4">
                        {setting.status}
                      </td>
                      <td className="border-b border-[color:var(--border)] py-3">
                        {setting.is_default ? "si" : "no"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {canManage ? (
          <AIProviderForms
            {...(searchParams.connection
              ? { connectionId: searchParams.connection }
              : {})}
            tenantId={context.tenantId}
          />
        ) : (
          <p className="border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--muted)]">
            Il tuo ruolo non consente di configurare provider AI.
          </p>
        )}
      </div>
    </main>
  );
}

function AIProviderForms({
  connectionId,
  tenantId
}: {
  connectionId?: string;
  tenantId: string;
}) {
  return (
    <section className="border-t border-[color:var(--border)] pt-6">
      <h2 className="text-base font-semibold">Nuova configurazione default</h2>
      <div className="mt-4 grid gap-5 lg:grid-cols-3">
        <AIProviderForm
          {...(connectionId ? { connectionId } : {})}
          effortOptions={["none", "low", "medium", "high", "xhigh"]}
          modelId="gpt-5.5"
          modelLabel="GPT-5.5 / ChatGPT 5.5"
          provider="openai"
          tenantId={tenantId}
        />
        <AIProviderForm
          {...(connectionId ? { connectionId } : {})}
          effortOptions={["low", "medium", "high"]}
          modelId="claude-sonnet-4-6"
          modelLabel="Claude Sonnet 4.6"
          provider="anthropic"
          tenantId={tenantId}
        />
        <AIProviderForm
          {...(connectionId ? { connectionId } : {})}
          effortOptions={["low", "medium", "high", "xhigh", "max"]}
          modelId="claude-opus-4-8"
          modelLabel="Claude Opus 4.8"
          provider="anthropic"
          tenantId={tenantId}
        />
      </div>
    </section>
  );
}

function AIProviderForm({
  connectionId,
  effortOptions,
  modelId,
  modelLabel,
  provider,
  tenantId
}: {
  connectionId?: string;
  effortOptions: string[];
  modelId: string;
  modelLabel: string;
  provider: "openai" | "anthropic";
  tenantId: string;
}) {
  return (
    <div className="border border-[color:var(--border)] p-4">
      <h3 className="text-sm font-semibold">{modelLabel}</h3>
      <form
        action={createAIProviderSettingAction}
        className="mt-4 grid gap-4 text-sm"
      >
        {connectionId ? (
          <input name="connection_id" type="hidden" value={connectionId} />
        ) : null}
        <input name="provider" type="hidden" value={provider} />
        <input name="model_id" type="hidden" value={modelId} />
        <input name="tenant_id" type="hidden" value={tenantId} />
        <label className="grid gap-1">
          Nome
          <input
            className="border border-[color:var(--border)] bg-transparent px-3 py-2"
            defaultValue={modelLabel}
            maxLength={160}
            name="display_name"
            required
          />
        </label>
        <label className="grid gap-1">
          Effort / reasoning
          <select
            className="border border-[color:var(--border)] bg-transparent px-3 py-2"
            defaultValue="medium"
            name="thinking_effort"
            required
          >
            {effortOptions.map((effort) => (
              <option key={effort} value={effort}>
                {effort}
              </option>
            ))}
          </select>
        </label>
        {provider === "anthropic" ? (
          <label className="flex items-center gap-2">
            <input defaultChecked name="adaptive_thinking" type="checkbox" />
            Adaptive/dynamic thinking Anthropic
          </label>
        ) : null}
        <label className="grid gap-1">
          API key
          <input
            autoComplete="off"
            className="border border-[color:var(--border)] bg-transparent px-3 py-2"
            name="api_key"
            required
            type="password"
          />
        </label>
        <p className="max-w-2xl text-xs text-[color:var(--muted)]">
          La key viene salvata in Secret Manager. Il database conserva solo un
          riferimento tecnico e la UI non potra rileggerla.
        </p>
        <SubmitButton
          className="justify-self-start border border-[color:var(--accent)] px-4 py-2 text-sm font-medium disabled:cursor-wait disabled:opacity-60"
          idleLabel="Salva provider AI"
          pendingLabel="Salvataggio..."
        />
      </form>
    </div>
  );
}

function thinkingLabel(
  thinking: AIProviderSettingSummary["thinking"]
) {
  if (thinking.type === "openai_reasoning") {
    return `reasoning ${thinking.effort}`;
  }
  return `${thinking.enabled ? "adaptive" : "disabled"} ${thinking.effort}`;
}
