"use client"

import { MessageSquare, RotateCw, Search, Swords } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { AppNav } from "@/components/app-nav"
import { Sidebar } from "@/components/sidebar"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select"
import { useCatalog } from "@/hooks/use-catalog"
import { modelKey, type ModelCard } from "@/lib/api"
import {
  CAPABILITY_LABELS,
  FILTERS,
  SORTS,
  filterModels,
  sortModels,
  type CatalogFilter,
  type CatalogSort,
} from "@/lib/catalog"
import { formatBytes, formatCount, formatSeconds } from "@/lib/format"
import { cn } from "@/lib/utils"

const MAX_COMPARED = 4

export function ModelsCatalog() {
  const catalog = useCatalog()
  const [query, setQuery] = useState("")
  const [filters, setFilters] = useState<Set<CatalogFilter>>(new Set())
  const [sort, setSort] = useState<CatalogSort>("name")
  const [picked, setPicked] = useState<string[]>([])

  const visible = sortModels(filterModels(catalog.models, query, filters), sort)
  const unavailable = catalog.providers.filter((p) => !p.available)

  const toggleFilter = (filter: CatalogFilter) =>
    setFilters((prev) => {
      const next = new Set(prev)
      if (next.has(filter)) next.delete(filter)
      else next.add(filter)
      return next
    })
  const togglePick = (key: string) =>
    setPicked((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]))
  // Plusieurs fois le même paramètre : /compare?model=a&model=b
  const compareHref = `/compare?${picked.map((key) => `model=${encodeURIComponent(key)}`).join("&")}`

  return (
    <div className="flex h-dvh">
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b px-4 py-2.5">
          <AppNav compact className="md:hidden" />
          <h1 className="font-semibold tracking-tight">Models</h1>
          {catalog.status === "ready" && (
            <span className="text-sm text-muted-foreground">
              {visible.length} of {catalog.models.length}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto"
            onClick={catalog.retry}
            aria-label="Refresh"
          >
            <RotateCw />
          </Button>
        </header>

        <section className="flex flex-col gap-3 border-b px-4 py-3">
          <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-2">
            <label className="relative min-w-56 flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search a model, a provider, a use…"
                aria-label="Search models"
                className="h-8 w-full rounded-lg border border-input bg-transparent pr-2.5 pl-8 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
              />
            </label>
            <Select
              value={sort}
              onValueChange={(next) => {
                if (typeof next === "string") setSort(next as CatalogSort)
              }}
            >
              <SelectTrigger size="sm" aria-label="Sort by" className="min-w-40">
                <span>Sort: {SORTS.find((s) => s.value === sort)?.label}</span>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false} align="end">
                {SORTS.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="mx-auto flex w-full max-w-6xl flex-wrap gap-1.5">
            {FILTERS.map(({ value, label, hint }) => (
              <button
                key={value}
                type="button"
                title={hint}
                aria-pressed={filters.has(value)}
                onClick={() => toggleFilter(value)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs transition-colors hover:bg-accent",
                  filters.has(value) && "border-primary bg-primary/15 text-primary hover:bg-primary/20",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-6">
            {unavailable.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Unavailable right now: {unavailable.map((p) => p.name).join(", ")}.
              </p>
            )}
            {catalog.status === "ready" && !catalog.statsAvailable && (
              <p className="text-xs text-muted-foreground">
                Measurements unavailable: the database cannot be reached.
              </p>
            )}

            {catalog.status === "error" ? (
              <div className="flex flex-col items-center gap-2 pt-[12vh] text-sm">
                <p className="text-destructive">{catalog.error}</p>
                <Button variant="outline" size="sm" onClick={catalog.retry}>
                  <RotateCw />
                  Retry
                </Button>
              </div>
            ) : catalog.status === "loading" ? (
              <p className="pt-[12vh] text-center text-sm text-muted-foreground">
                Loading models…
              </p>
            ) : visible.length === 0 ? (
              <p className="pt-[12vh] text-center text-sm text-muted-foreground">
                No model matches these filters.
              </p>
            ) : (
              <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(19rem,1fr))]">
                {visible.map((card) => {
                  const key = modelKey(card)
                  return (
                    <ModelCardView
                      key={key}
                      card={card}
                      picked={picked.includes(key)}
                      canPick={picked.length < MAX_COMPARED}
                      onTogglePick={() => togglePick(key)}
                    />
                  )
                })}
              </div>
            )}
          </div>
        </main>

        {picked.length > 0 && (
          <footer className="border-t px-4 py-3">
            <div className="mx-auto flex max-w-6xl items-center gap-3">
              <span className="text-sm">
                {picked.length} selected (up to {MAX_COMPARED})
              </span>
              <Button variant="ghost" size="sm" onClick={() => setPicked([])}>
                Clear
              </Button>
              {picked.length >= 2 ? (
                <Link href={compareHref} className={buttonVariants({ size: "sm", className: "ml-auto" })}>
                  <Swords />
                  Compare them
                </Link>
              ) : (
                <span className="ml-auto text-xs text-muted-foreground">
                  Pick at least two models to compare
                </span>
              )}
            </div>
          </footer>
        )}
      </div>
    </div>
  )
}

interface ModelCardViewProps {
  card: ModelCard
  picked: boolean
  canPick: boolean
  onTogglePick: () => void
}

function ModelCardView({ card, picked, canPick, onTogglePick }: ModelCardViewProps) {
  const embedding = card.capabilities.includes("embedding")
  const facts = [
    card.parameters_b != null && ["Size", `${card.parameters_b}B parameters`],
    card.context_length != null && ["Context", `${formatCount(card.context_length)} tokens`],
    card.size_bytes != null && ["On disk", formatBytes(card.size_bytes)],
    card.quantization && ["Quantization", card.quantization],
  ].filter((fact): fact is [string, string] => Boolean(fact))

  return (
    <article
      className={cn(
        "flex flex-col gap-3 rounded-xl border bg-card/40 p-4",
        picked && "border-primary ring-1 ring-primary/40",
      )}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate font-medium" title={card.name}>
            {card.name}
          </h2>
          <p className="truncate font-mono text-xs text-muted-foreground" title={card.id}>
            {card.id}
          </p>
        </div>
        <Badge variant={card.local ? "default" : "outline"}>
          {card.local ? "Local" : card.provider}
        </Badge>
      </header>

      {(card.capabilities.length > 0 || (card.free && !card.local)) && (
        <div className="flex flex-wrap gap-1.5">
          {card.capabilities.map((capability) => (
            <Badge key={capability} variant="secondary">
              {CAPABILITY_LABELS[capability] ?? capability}
            </Badge>
          ))}
          {card.free && !card.local && <Badge variant="secondary">Free</Badge>}
        </div>
      )}

      {facts.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-mono">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {card.description && (
        <p className="line-clamp-3 text-sm text-muted-foreground" title={card.description}>
          {card.description}
        </p>
      )}

      <p className="text-xs">
        {card.stats ? (
          <>
            <span className="text-muted-foreground">Measured here: </span>
            {card.stats.answers} {card.stats.answers === 1 ? "answer" : "answers"}
            {card.stats.avg_tokens_per_second != null &&
              ` · ${card.stats.avg_tokens_per_second} tok/s`}
            {card.stats.avg_ttft_ms != null &&
              ` · first token ${formatSeconds(card.stats.avg_ttft_ms)}`}
          </>
        ) : (
          <span className="text-muted-foreground">Not tried yet.</span>
        )}
      </p>

      {!embedding && (
        <footer className="mt-auto flex gap-2">
          <Link
            href={`/?model=${encodeURIComponent(modelKey(card))}`}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            <MessageSquare />
            Chat
          </Link>
          <Button
            variant={picked ? "default" : "ghost"}
            size="sm"
            onClick={onTogglePick}
            disabled={!picked && !canPick}
            aria-pressed={picked}
          >
            <Swords />
            {picked ? "Selected" : "Compare"}
          </Button>
        </footer>
      )}
    </article>
  )
}
