"use client"

import { Swords, Trophy, X } from "lucide-react"
import { useSearchParams } from "next/navigation"
import { useState } from "react"

import { AppNav } from "@/components/app-nav"
import { Composer } from "@/components/composer"
import { HistoryList } from "@/components/history-list"
import { Message } from "@/components/message"
import { ModelPicker } from "@/components/model-picker"
import { Sidebar } from "@/components/sidebar"
import { Badge } from "@/components/ui/badge"
import { useComparison, type Contender, type ContenderState } from "@/hooks/use-comparison"
import { useModels } from "@/hooks/use-models"
import { useSavedList } from "@/hooks/use-saved-list"
import { deleteComparison, listComparisons, modelKey, type ModelInfo } from "@/lib/api"
import { findBest } from "@/lib/compare"
import { formatSeconds } from "@/lib/format"
import { cn } from "@/lib/utils"

const MAX_MODELS = 4

export function Compare() {
  const models = useModels()
  const comparisons = useSavedList(listComparisons, deleteComparison)
  const { comparisonId, prompt, contenders, running, error, run, stop, open, reset } =
    useComparison({
      persist: comparisons.status !== "error",
      onSaved: comparisons.refresh,
    })

  const searchParams = useSearchParams()
  // Les modèles peuvent venir de l'URL (sélection faite dans le catalogue). Sinon null :
  // l'utilisateur n'a encore rien choisi, on propose les deux premiers modèles.
  const [chosenKeys, setChosenKeys] = useState<string[] | null>(() => {
    const fromUrl = searchParams.getAll("model")
    return fromUrl.length > 0 ? fromUrl.slice(0, MAX_MODELS) : null
  })

  const selectedKeys = chosenKeys ?? models.models.slice(0, 2).map(modelKey)
  const selected = selectedKeys
    .map((key) => models.models.find((model) => modelKey(model) === key))
    .filter((model): model is ModelInfo => model !== undefined)
  const localProviders = new Set(models.providers.filter((p) => p.local).map((p) => p.name))

  const add = (key: string) => setChosenKeys([...selectedKeys, key])
  const remove = (key: string) => setChosenKeys(selectedKeys.filter((k) => k !== key))

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this comparison?")) return
    try {
      await comparisons.remove(id)
      if (id === comparisonId) reset()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex h-dvh">
      <Sidebar>
        <HistoryList
          items={comparisons.items.map((c) => ({
            id: c.id,
            title: c.prompt,
            subtitle: c.models.join(" · "),
          }))}
          status={comparisons.status}
          activeId={comparisonId}
          onSelect={open}
          onNew={reset}
          onDelete={handleDelete}
          newLabel="New comparison"
          emptyLabel="No comparisons yet."
        />
      </Sidebar>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b px-4 py-2.5">
          <AppNav compact className="md:hidden" />
          <div className="flex items-center gap-2 font-semibold tracking-tight">
            <Swords className="size-5 text-primary" />
            Compare models
          </div>
        </header>

        <section className="border-b px-4 py-3">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2">
            {selected.map((model) => (
              <span
                key={modelKey(model)}
                className="flex items-center gap-1.5 rounded-lg border bg-card py-1 pr-1 pl-2.5 font-mono text-xs"
              >
                {model.id}
                <span className="text-muted-foreground">{model.provider}</span>
                <button
                  type="button"
                  onClick={() => remove(modelKey(model))}
                  disabled={running}
                  aria-label={`Remove ${model.id}`}
                  className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  <X className="size-3.5" />
                </button>
              </span>
            ))}
            {selected.length < MAX_MODELS && (
              <ModelPicker
                models={models.models.filter((model) => !selectedKeys.includes(modelKey(model)))}
                providers={models.providers}
                value={null}
                onChange={add}
                loading={models.status === "loading"}
                disabled={running}
                placeholder="Add a model…"
              />
            )}
          </div>
        </section>

        <main className="flex-1 overflow-y-auto">
          {error ? (
            <p className="px-4 pt-[16vh] text-center text-sm text-destructive">{error}</p>
          ) : contenders.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-4 pt-[16vh] text-center">
              <Swords className="size-12 text-primary" strokeWidth={1.5} />
              <h1 className="text-2xl font-semibold tracking-tight">One question, several minds.</h1>
              <p className="max-w-md text-sm text-muted-foreground">
                Pick two to four models and compare their answers and speed. Local models run
                one at a time, since they share your GPU.
              </p>
            </div>
          ) : (
            <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6">
              <p className="max-w-[85%] self-end rounded-2xl bg-secondary px-4 py-2.5 whitespace-pre-wrap">
                {prompt}
              </p>
              <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(18rem,1fr))]">
                {contenders.map((contender) => (
                  <ContenderColumn
                    key={contender.key}
                    contender={contender}
                    local={localProviders.has(contender.model.provider)}
                  />
                ))}
              </div>
              {!running && <Summary contenders={contenders} localProviders={localProviders} />}
            </div>
          )}
        </main>

        <footer className="mx-auto w-full max-w-3xl px-4 pb-4">
          <Composer
            onSend={(text) => run(text, selected, localProviders)}
            onStop={stop}
            streaming={running}
            disabled={selected.length < 2}
            placeholder={
              selected.length < 2 ? "Pick at least two models" : "Ask all the selected models…"
            }
          />
        </footer>
      </div>
    </div>
  )
}

const STATE_LABELS: Record<ContenderState, string> = {
  queued: "Queued",
  running: "Answering…",
  done: "Done",
  error: "Error",
  stopped: "Stopped",
}

function ContenderColumn({ contender, local }: { contender: Contender; local: boolean }) {
  const { model, state } = contender
  // Un modèle local en file d'attente attend que le GPU se libère.
  const label = state === "queued" && local ? "Waiting for GPU" : STATE_LABELS[state]

  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-xl border bg-card/40 p-4">
      <header className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-mono text-xs" title={model.id}>
            {model.id}
          </p>
          <p className="text-xs text-muted-foreground">{model.provider}</p>
        </div>
        <Badge
          variant={state === "error" ? "destructive" : state === "done" ? "secondary" : "outline"}
          className={cn(state === "running" && "animate-pulse")}
        >
          {label}
        </Badge>
      </header>
      {state !== "queued" && (
        <Message message={contender.message} streaming={state === "running"} showModel={false} />
      )}
    </article>
  )
}

function Summary({
  contenders,
  localProviders,
}: {
  contenders: Contender[]
  localProviders: Set<string>
}) {
  const results = contenders.map((c) => ({ key: c.key, metrics: c.message.metrics }))
  if (results.filter((r) => r.metrics).length < 2) return null
  const best = findBest(results)
  const hasLocal = contenders.some((c) => localProviders.has(c.model.provider))

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold">Summary</h2>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Model</th>
              <th className="px-3 py-2 font-medium">Time to first token</th>
              <th className="px-3 py-2 font-medium">Speed</th>
              <th className="px-3 py-2 font-medium">Tokens</th>
              <th className="px-3 py-2 font-medium">Total time</th>
            </tr>
          </thead>
          <tbody>
            {contenders.map(({ key, model, message: { metrics } }) => (
              <tr key={key} className="border-t">
                <td className="px-3 py-2 font-mono text-xs">
                  {model.id} <span className="text-muted-foreground">{model.provider}</span>
                </td>
                <MetricCell
                  value={metrics?.ttft_ms}
                  format={formatSeconds}
                  best={best.ttft_ms === key}
                />
                <MetricCell
                  value={metrics?.tokens_per_second}
                  format={(v) => `${v} tok/s`}
                  best={best.tokens_per_second === key}
                />
                <MetricCell value={metrics?.completion_tokens} format={String} best={false} />
                <MetricCell
                  value={metrics?.total_ms}
                  format={formatSeconds}
                  best={best.total_ms === key}
                />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hasLocal && (
        <p className="text-xs text-muted-foreground">
          Local times include loading the model into VRAM, which is slower the first time.
        </p>
      )}
    </section>
  )
}

interface MetricCellProps {
  value: number | null | undefined
  format: (value: number) => string
  best: boolean
}

function MetricCell({ value, format, best }: MetricCellProps) {
  return (
    <td className={cn("px-3 py-2 font-mono text-xs", best && "font-semibold text-primary")}>
      {value == null ? "–" : format(value)}
      {best && <Trophy className="ml-1.5 inline size-3.5" aria-label="best" />}
    </td>
  )
}
