"use client"

import {
  Check,
  ChevronRight,
  CircleSlash,
  FilePen,
  FileText,
  FolderTree,
  Loader2,
  MessageSquare,
  Search,
  ShieldAlert,
  SquareTerminal,
  TriangleAlert,
  Wrench,
  type LucideIcon,
} from "lucide-react"
import { useState } from "react"

import { DiffStats, DiffView } from "@/components/diff-view"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import type { AgentStep, FileDiff, ToolDecision } from "@/lib/api"
import { cn } from "@/lib/utils"

const ICONS: Record<string, LucideIcon> = {
  list_files: FolderTree,
  read_file: FileText,
  search_files: Search,
  write_file: FilePen,
  edit_file: FilePen,
  run_command: SquareTerminal,
  ask_user: MessageSquare,
}

export type ApproveHandler = (callId: string, decision: ToolDecision, answer?: string) => void

interface ToolStepProps {
  step: AgentStep
  onApprove?: ApproveHandler
}

/** Un appel d'outil de l'agent : ce qu'il fait, son résultat, ou ce qu'il attend de vous. */
export function ToolStep({ step, onApprove }: ToolStepProps) {
  const Icon = ICONS[step.name] ?? Wrench
  const asking = step.status === "asking"

  return (
    <div className={cn("rounded-lg border px-3 py-2", asking && "border-primary/60 bg-primary/5")}>
      <div className="flex items-center gap-2">
        <Icon className="size-4 shrink-0 text-muted-foreground" />
        <span className="truncate font-mono text-xs">{step.summary}</span>
        <Status step={step} />
      </div>

      {asking && step.kind === "question" ? (
        <Question step={step} onAnswer={(answer) => onApprove?.(step.id, "answer", answer)} />
      ) : asking ? (
        <>
          {step.diff ? <DiffView diff={step.diff} className="mt-2" /> : <Preview step={step} />}
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => onApprove?.(step.id, "once")}>
              Allow once
            </Button>
            <Button size="sm" variant="outline" onClick={() => onApprove?.(step.id, "always")}>
              Always allow {step.name}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onApprove?.(step.id, "deny")}>
              Deny
            </Button>
          </div>
        </>
      ) : step.diff && step.status === "done" ? (
        <Changes diff={step.diff} summary={step.output} />
      ) : (
        step.output && <Output text={step.output} failed={step.status !== "done"} />
      )}
    </div>
  )
}

function Status({ step }: { step: AgentStep }) {
  if (step.status === "asking") {
    const question = step.kind === "question"
    return (
      <span className="ml-auto flex shrink-0 items-center gap-1 text-xs text-primary">
        {question ? <MessageSquare className="size-3.5" /> : <ShieldAlert className="size-3.5" />}
        {question ? "Waiting for your answer" : "Needs your permission"}
      </span>
    )
  }

  const badge = {
    running: <Loader2 className="size-3.5 animate-spin" />,
    done: <Check className="size-3.5 text-muted-foreground" />,
    error: <TriangleAlert className="size-3.5 text-destructive" />,
    denied: <CircleSlash className="size-3.5 text-muted-foreground" />,
  }[step.status]

  return <span className="ml-auto shrink-0 text-xs text-muted-foreground">{badge}</span>
}

/** La question de l'agent : une réponse d'un clic, ou la vôtre, tapée à la main. */
function Question({ step, onAnswer }: { step: AgentStep; onAnswer: (answer: string) => void }) {
  const [other, setOther] = useState("")

  return (
    <div className="mt-2 flex flex-col gap-2">
      <p className="text-sm font-medium">{step.question}</p>
      {step.options && step.options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {step.options.map((option) => (
            <Button key={option} size="sm" variant="outline" onClick={() => onAnswer(option)}>
              {option}
            </Button>
          ))}
        </div>
      )}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (other.trim()) onAnswer(other.trim())
        }}
      >
        <Input
          value={other}
          onChange={(event) => setOther(event.target.value)}
          placeholder="Or type your own answer…"
          aria-label="Your answer"
        />
        <Button type="submit" size="sm" disabled={!other.trim()}>
          Answer
        </Button>
      </form>
    </div>
  )
}

/** Ce que l'agent s'apprête à faire, quand ce n'est pas une écriture : à lire avant d'autoriser. */
function Preview({ step }: { step: AgentStep }) {
  const args = step.arguments ?? {}
  const text =
    typeof args.command === "string"
      ? args.command
      : typeof args.new_string === "string"
        ? `- ${args.old_string ?? ""}\n+ ${args.new_string}`
        : typeof args.content === "string"
          ? args.content
          : JSON.stringify(args, null, 2)

  return (
    <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted p-2 text-xs whitespace-pre-wrap">
      {text.slice(0, 2000)}
    </pre>
  )
}

/** Une écriture faite : son résultat, et le diff à déplier pour revoir ce qui a changé. */
function Changes({ diff, summary }: { diff: FileDiff; summary: string }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group mt-1 flex w-full items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronRight className="size-3.5 shrink-0 transition-transform group-data-panel-open:rotate-90" />
        <span className="truncate">{summary}</span>
        <DiffStats diff={diff} className="ml-1" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <DiffView diff={diff} className="mt-1" />
      </CollapsibleContent>
    </Collapsible>
  )
}

function Output({ text, failed }: { text: string; failed: boolean }) {
  const lines = text.split("\n")

  return (
    <Collapsible>
      <CollapsibleTrigger className="group mt-1 flex w-full items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronRight className="size-3.5 shrink-0 transition-transform group-data-panel-open:rotate-90" />
        <span className={cn("truncate", failed && "text-destructive")}>{lines[0]}</span>
        {lines.length > 1 && <span className="shrink-0">+{lines.length - 1} lines</span>}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-muted p-2 text-xs whitespace-pre-wrap">
          {text}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  )
}
