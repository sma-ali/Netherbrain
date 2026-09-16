"use client"

import { Eye } from "lucide-react"
import { Fragment } from "react"

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
} from "@/components/ui/select"
import { modelKey, type ModelInfo, type ProviderStatus } from "@/lib/api"
import { cn } from "@/lib/utils"

interface ModelPickerProps {
  models: ModelInfo[]
  providers: ProviderStatus[]
  value: string | null
  onChange: (key: string) => void
  loading: boolean
  disabled: boolean
  /** Texte affiché quand aucun modèle n'est sélectionné. */
  placeholder?: string
}

export function ModelPicker({
  models,
  providers,
  value,
  onChange,
  loading,
  disabled,
  placeholder = "No model",
}: ModelPickerProps) {
  const selected = models.find((model) => modelKey(model) === value)

  return (
    <Select
      value={value}
      onValueChange={(next) => {
        if (typeof next === "string") onChange(next)
      }}
      disabled={disabled || models.length === 0}
    >
      <SelectTrigger size="sm" aria-label="Model" className="max-w-72 min-w-44 font-mono text-xs">
        <span className="truncate">
          {selected ? selected.id : loading ? "Loading models…" : placeholder}
        </span>
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="end" className="min-w-72">
        {providers.map((provider, index) => (
          <Fragment key={provider.name}>
            {index > 0 && <SelectSeparator />}
            <SelectGroup>
              <SelectLabel
                className="flex items-center gap-1.5"
                title={provider.error ?? undefined}
              >
                <span
                  className={cn(
                    "size-1.5 rounded-full",
                    provider.available ? "bg-emerald-500" : "bg-destructive",
                  )}
                />
                {provider.name}
                {!provider.available && <span className="text-destructive">unavailable</span>}
              </SelectLabel>
              {models
                .filter((model) => model.provider === provider.name)
                .map((model) => (
                  <SelectItem key={modelKey(model)} value={modelKey(model)}>
                    <span className="font-mono text-xs">{model.id}</span>
                    {model.vision && (
                      <Eye
                        className="ml-auto size-3.5 self-center text-muted-foreground"
                        aria-label="Reads images"
                      />
                    )}
                  </SelectItem>
                ))}
            </SelectGroup>
          </Fragment>
        ))}
      </SelectContent>
    </Select>
  )
}
