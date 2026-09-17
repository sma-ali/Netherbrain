"use client"

import {
  ArrowRight,
  Check,
  Copy,
  Loader2,
  MessageSquare,
  RefreshCw,
  Sparkles,
  Swords,
  TriangleAlert,
} from "lucide-react"
import Link from "next/link"
import { useEffect, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { EXAMPLES, ROLE_LABELS, compareHref, describeNeeds, pickKey } from "@/lib/advisor"
import {
  fetchBenchmarksStatus,
  recommendModels,
  syncBenchmarks,
  type BenchmarksStatus,
  type ModelPick,
  type Recommendation,
} from "@/lib/api"
import { formatAge } from "@/lib/format"
import { cn } from "@/lib/utils"

/** « Quel modèle pour mon projet ? » : une phrase, et le podium des modèles adaptés. */
export function ModelAdvisor() {
  const [query, setQuery] = useState("")
  const [result, setResult] = useState<Recommendation | null>(null)
  const [loading, setLoading] = useState(false)
  // Un premier podium est affiché (mots-clés) ; un modèle lit encore la demande pour l'affiner.
  const [refining, setRefining] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [benchmarks, setBenchmarks] = useState<BenchmarksStatus | null>(null)
  // La demande en cours : une nouvelle demande annule la précédente.
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchBenchmarksStatus(controller.signal)
      .then(setBenchmarks)
      .catch(() => {}) // sans état des benchmarks, le conseiller marche quand même
    return () => controller.abort()
  }, [])

  const ask = async (text: string) => {
    const trimmed = text.trim()
    if (trimmed.length < 3) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setQuery(trimmed)
    setLoading(true)
    setRefining(false)
    setError(null)
    try {
      // 1. Tout de suite : une lecture par mots-clés, pour ne pas faire attendre.
      const quick = await recommendModels(trimmed, { understand: false, signal: controller.signal })
      setResult(quick)
      setBenchmarks(quick.benchmarks)
      setLoading(false)
      // 2. Puis un LLM lit vraiment la demande : plus fin, mais plusieurs secondes en local.
      setRefining(true)
      const refined = await recommendModels(trimmed, { signal: controller.signal })
      setResult(refined)
      setBenchmarks(refined.benchmarks)
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
    } finally {
      // Une demande plus récente a pu prendre la main entre-temps : elle gère son propre état.
      if (controllerRef.current === controller) {
        setLoading(false)
        setRefining(false)
      }
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-2xl border bg-card/40 p-5">
      <div className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Sparkles className="size-5 text-primary" />
          Which model for your project?
        </h2>
        <p className="text-sm text-muted-foreground">
          Describe what you want to build or do: Netherbrain ranks the models that fit, and explains
          why.
        </p>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          void ask(query)
        }}
        className="flex gap-2"
      >
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. A Discord bot that summarizes French PDFs, running locally"
          aria-label="Describe your project"
          maxLength={1000}
          className="h-10 min-w-0 flex-1 rounded-lg border border-input bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
        <Button type="submit" className="h-10" disabled={loading || query.trim().length < 3}>
          {loading ? <Loader2 className="animate-spin" /> : <ArrowRight />}
          Recommend
        </Button>
      </form>

      {!result && !loading && (
        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => void ask(example)}
              className="rounded-full border px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              {example}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Reading your request… a local model can take a few seconds to load.
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && !loading && <Results result={result} refining={refining} />}

      <BenchmarksFooter status={benchmarks} onUpdated={setBenchmarks} />
    </section>
  )
}

function Results({ result, refining }: { result: Recommendation; refining: boolean }) {
  const compare = compareHref(result.picks, result.query)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-muted-foreground">Understood as</span>
        {describeNeeds(result.needs).map((label) => (
          <Badge key={label} variant="secondary">
            {label}
          </Badge>
        ))}
        <span className="flex items-center gap-1.5 text-muted-foreground">
          ·
          {refining ? (
            <>
              <Loader2 className="size-3.5 animate-spin" />
              quick read from keywords, a model is reading your request to refine it…
            </>
          ) : result.understood_by === "keywords" ? (
            "from keywords (no model could read it in time)"
          ) : (
            `read by ${result.understood_by}`
          )}
        </span>
      </div>

      {result.warnings.map((warning) => (
        <p key={warning} className="flex items-center gap-2 text-xs text-muted-foreground">
          <TriangleAlert className="size-3.5 shrink-0" />
          {warning}
        </p>
      ))}

      {result.picks.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No model fits these needs. Try a less strict request, or install a model with the
          capabilities it requires.
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-3">
          {result.picks.map((pick) => (
            <PickCard key={`${pick.role}-${pick.model}`} pick={pick} />
          ))}
        </div>
      )}

      {compare && (
        <Link
          href={compare}
          className={buttonVariants({ variant: "outline", size: "sm", className: "self-start" })}
        >
          <Swords />
          Compare them on your request
        </Link>
      )}
    </div>
  )
}

function PickCard({ pick }: { pick: ModelPick }) {
  const key = pickKey(pick)

  return (
    <article
      className={cn(
        "flex flex-col gap-2 rounded-xl border bg-background/60 p-4",
        pick.role === "best" && "border-primary ring-1 ring-primary/40",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-primary">{ROLE_LABELS[pick.role]}</span>
        <Badge variant={pick.local && pick.ready ? "default" : "outline"}>
          {!pick.ready ? "Not installed" : pick.local ? "Local" : pick.provider}
        </Badge>
      </div>
      <h3 className="truncate font-mono text-sm font-medium" title={pick.model}>
        {pick.model}
      </h3>
      {pick.benchmark && (
        <p className="text-xs text-muted-foreground">Benchmarked as {pick.benchmark}</p>
      )}

      <ul className="flex flex-col gap-1 text-xs">
        {pick.reasons.map((reason) => (
          <li key={reason} className="flex gap-1.5">
            <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
            <span>{reason}</span>
          </li>
        ))}
      </ul>
      {pick.warnings.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
          {pick.warnings.map((warning) => (
            <li key={warning} className="flex gap-1.5">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto pt-1">
        {key ? (
          <Link
            href={`/?model=${encodeURIComponent(key)}`}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            <MessageSquare />
            Chat
          </Link>
        ) : (
          pick.pull_command && <PullCommand command={pick.pull_command} />
        )}
      </div>
    </article>
  )
}

/** La commande pour installer le modèle, à copier d'un clic. */
function PullCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)

  return (
    <div className="flex items-center gap-1 rounded-md bg-muted py-1 pr-1 pl-2 font-mono text-xs">
      <code className="min-w-0 flex-1 truncate" title={command}>
        {command}
      </code>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label="Copy the command"
        onClick={() => void navigator.clipboard?.writeText(command).then(() => setCopied(true))}
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </div>
  )
}

interface BenchmarksFooterProps {
  status: BenchmarksStatus | null
  onUpdated: (status: BenchmarksStatus) => void
}

/** D'où viennent les benchmarks (la source doit être citée), et depuis quand. */
function BenchmarksFooter({ status, onUpdated }: BenchmarksFooterProps) {
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!status) return null

  const update = async () => {
    setUpdating(true)
    setError(null)
    try {
      onUpdated(await syncBenchmarks())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setUpdating(false)
    }
  }

  const source = (
    <a
      href={status.url}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-2 hover:text-foreground"
    >
      {status.source}
    </a>
  )
  const problem = error ?? status.error

  return (
    <footer className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
      {status.configured ? (
        <>
          <span>
            Live benchmarks by {source}
            {status.models > 0 && ` · ${status.models} models`}
            {status.fetched_at && ` · updated ${formatAge(status.fetched_at)}`}
          </span>
          <Button variant="ghost" size="sm" onClick={() => void update()} disabled={updating}>
            {updating ? <Loader2 className="animate-spin" /> : <RefreshCw />}
            Update now
          </Button>
        </>
      ) : (
        <span>
          Live benchmarks are off: add a free {source} API key as{" "}
          <code className="font-mono">NETHERBRAIN_ARTIFICIAL_ANALYSIS_API_KEY</code>. Until then,
          rankings rely on Netherbrain&apos;s built-in model grid.
        </span>
      )}
      {problem && <span className="text-destructive">{problem}</span>}
    </footer>
  )
}
