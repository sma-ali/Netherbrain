"use client"

import {
  Check,
  ChevronRight,
  CircleSlash,
  FilePen,
  FileText,
  FolderTree,
  Loader2,
  Search,
  ShieldAlert,
  SquareTerminal,
  TriangleAlert,
  Wrench,
  type LucideIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import type { AgentStep, ToolDecision } from "@/lib/api"
import { cn } from "@/lib/utils"

const ICONS: Record<string, LucideIcon> = {
  list_files: FolderTree,
  read_file: FileText,
  search_files: Search,
  write_file: FilePen,
  edit_file: FilePen,
  run_command: SquareTerminal,
}

interface ToolStepProps {
  step: AgentStep
  onApprove?: (callId: string, decision: ToolDecision) => void
}

/** Un appel d'outil de l'agent : ce qu'il fait, son résultat, et la demande d'autorisation. */
export function ToolStep({ step, onApprove }: ToolStepProps) {
  const Icon = ICONS[step.name] ?? Wrench
  const asking = step.status === "asking"

  return (
    <div className={cn("rounded-lg border px-3 py-2", asking && "border-primary/60 bg-primary/5")}>
      <div className="flex items-center gap-2">
        <Icon className="size-4 shrink-0 text-muted-foreground" />
        <span className="truncate font-mono text-xs">{step.summary}</span>
        <Status status={step.status} />
      </div>

      {asking ? (
        <>
          <Preview step={step} />
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
      ) : (
        step.output && <Output text={step.output} failed={step.status !== "done"} />
      )}
    </div>
  )
}

function Status({ status }: { status: AgentStep["status"] }) {
  const badge = {
    running: <Loader2 className="size-3.5 animate-spin" />,
    asking: (
      <span className="flex items-center gap-1 text-primary">
        <ShieldAlert className="size-3.5" />
        Needs your permission
      </span>
    ),
    done: <Check className="size-3.5 text-muted-foreground" />,
    error: <TriangleAlert className="size-3.5 text-destructive" />,
    denied: <CircleSlash className="size-3.5 text-muted-foreground" />,
  }[status]

  return <span className="ml-auto shrink-0 text-xs text-muted-foreground">{badge}</span>
}

/** Ce que l'agent s'apprête à faire : à lire avant d'autoriser. */
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
