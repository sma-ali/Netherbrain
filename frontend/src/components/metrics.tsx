"use client"

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { ChatMetrics } from "@/lib/api"

const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`

export function Metrics({ metrics }: { metrics: ChatMetrics }) {
  const items = [
    metrics.ttft_ms != null && {
      label: `TTFT ${seconds(metrics.ttft_ms)}`,
      hint: "Time to first token: how long before the model starts answering (includes loading it into VRAM).",
    },
    metrics.tokens_per_second != null && {
      label: `${metrics.tokens_per_second} tok/s`,
      hint: "Generation speed, in tokens per second.",
    },
    metrics.completion_tokens != null && {
      label: `${metrics.completion_tokens} tokens`,
      hint: `Tokens generated, reasoning included. Prompt: ${metrics.prompt_tokens ?? "?"} tokens.`,
    },
    { label: seconds(metrics.total_ms), hint: "Total response time." },
  ].filter((item) => item !== false)

  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Tooltip key={item.hint}>
          <TooltipTrigger className="rounded-md border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
            {item.label}
          </TooltipTrigger>
          <TooltipContent>{item.hint}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  )
}
