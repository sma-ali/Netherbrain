"use client"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { ModelInfo } from "@/lib/api"

interface ModelPickerProps {
  models: ModelInfo[]
  value: string | null
  onChange: (model: string) => void
  loading: boolean
  disabled: boolean
}

export function ModelPicker({ models, value, onChange, loading, disabled }: ModelPickerProps) {
  const placeholder = loading ? "Loading models…" : "No model"

  return (
    <Select
      value={value}
      onValueChange={(next) => {
        if (typeof next === "string") onChange(next)
      }}
      disabled={disabled || models.length === 0}
    >
      <SelectTrigger size="sm" aria-label="Model" className="min-w-44 font-mono text-xs">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="end">
        {models.map((model) => (
          <SelectItem key={`${model.provider}/${model.id}`} value={model.id}>
            <span className="font-mono text-xs">{model.id}</span>
            <span className="ml-auto text-xs text-muted-foreground">{model.provider}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
