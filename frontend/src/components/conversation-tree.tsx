"use client"

import {
  ChevronRight,
  Folder,
  FolderPlus,
  Plus,
  SquarePen,
  Trash2,
  TriangleAlert,
} from "lucide-react"
import { useState, type ReactNode } from "react"

import { HistoryRow, HistoryUnavailable } from "@/components/history-list"
import { Button } from "@/components/ui/button"
import type { ConversationSummary, Project } from "@/lib/api"
import { groupConversations } from "@/lib/projects"
import { cn } from "@/lib/utils"

interface ConversationTreeProps {
  projects: Project[]
  conversations: ConversationSummary[]
  status: "loading" | "ready" | "error"
  activeConversationId: string | null
  activeProjectId: string | null
  onSelect: (conversation: ConversationSummary) => void
  /** Nouvelle conversation, dans le projet donné (null : une simple discussion). */
  onNewChat: (projectId: string | null) => void
  onDelete: (id: string) => void
  onAddProject: () => void
  onDeleteProject: (project: Project) => void
}

/**
 * La barre latérale du chat, façon Claude Code : chaque projet (un dossier) avec ses
 * conversations, puis les discussions qui n'appartiennent à aucun projet.
 */
export function ConversationTree({
  projects,
  conversations,
  status,
  activeConversationId,
  activeProjectId,
  onSelect,
  onNewChat,
  onDelete,
  onAddProject,
  onDeleteProject,
}: ConversationTreeProps) {
  // Les projets repliés par l'utilisateur ; tous sont dépliés par défaut.
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set())
  const { byProject, loose } = groupConversations(conversations, projects)

  const toggle = (id: string) =>
    setCollapsed((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const row = (conversation: ConversationSummary) => (
    <HistoryRow
      key={conversation.id}
      item={{ id: conversation.id, title: conversation.title ?? "Untitled" }}
      active={conversation.id === activeConversationId}
      onSelect={() => onSelect(conversation)}
      onDelete={onDelete}
    />
  )

  return (
    <>
      <div className="border-t px-3 pt-3 pb-2">
        <Button variant="outline" className="w-full justify-start" onClick={() => onNewChat(null)}>
          <Plus />
          New chat
        </Button>
      </div>

      <nav aria-label="History" className="flex-1 overflow-y-auto px-2 pb-4">
        {status === "error" ? (
          <HistoryUnavailable />
        ) : (
          <>
            <SectionTitle
              action={
                <IconButton label="Add a project" onClick={onAddProject}>
                  <FolderPlus />
                </IconButton>
              }
            >
              Projects
            </SectionTitle>
            {status === "ready" && projects.length === 0 && (
              <button
                type="button"
                onClick={onAddProject}
                className="w-full rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                Link a folder to chat about its code.
              </button>
            )}
            <ul className="flex flex-col gap-0.5">
              {projects.map((project) => {
                const open = !collapsed.has(project.id)
                const items = byProject.get(project.id) ?? []
                const current = project.id === activeProjectId && activeConversationId === null
                return (
                  <li key={project.id}>
                    <div
                      className={cn(
                        "group relative flex items-center rounded-md hover:bg-accent",
                        current && "bg-accent",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => toggle(project.id)}
                        aria-expanded={open}
                        title={project.available ? project.path : `Folder not found: ${project.path}`}
                        className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 pr-14 pl-1 text-left text-sm"
                      >
                        <ChevronRight
                          className={cn(
                            "size-3.5 shrink-0 text-muted-foreground transition-transform",
                            open && "rotate-90",
                          )}
                        />
                        {project.available ? (
                          <Folder className="size-4 shrink-0 text-primary" />
                        ) : (
                          <TriangleAlert className="size-4 shrink-0 text-destructive" />
                        )}
                        <span className="truncate">{project.name}</span>
                      </button>
                      <div className="absolute right-1 flex opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                        <IconButton
                          label={`New chat in ${project.name}`}
                          onClick={() => onNewChat(project.id)}
                        >
                          <SquarePen />
                        </IconButton>
                        <IconButton
                          label={`Remove the project ${project.name}`}
                          onClick={() => onDeleteProject(project)}
                          destructive
                        >
                          <Trash2 />
                        </IconButton>
                      </div>
                    </div>
                    {open && (
                      <ul className="ml-3 flex flex-col gap-0.5 border-l pl-1.5">
                        {items.length === 0 ? (
                          <li className="px-2 py-1 text-xs text-muted-foreground">
                            No conversations yet.
                          </li>
                        ) : (
                          items.map(row)
                        )}
                      </ul>
                    )}
                  </li>
                )
              })}
            </ul>

            <SectionTitle>Chats</SectionTitle>
            {status === "ready" && loose.length === 0 ? (
              <p className="px-2 text-xs text-muted-foreground">No conversations yet.</p>
            ) : (
              <ul className="flex flex-col gap-0.5">{loose.map(row)}</ul>
            )}
          </>
        )}
      </nav>
    </>
  )
}

function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mt-3 mb-1 flex items-center justify-between px-2 first:mt-1">
      <h2 className="text-xs font-medium text-muted-foreground">{children}</h2>
      {action}
    </div>
  )
}

interface IconButtonProps {
  label: string
  onClick: () => void
  destructive?: boolean
  children: ReactNode
}

function IconButton({ label, onClick, destructive = false, children }: IconButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        "rounded p-1 text-muted-foreground hover:text-foreground [&_svg]:size-3.5",
        destructive && "hover:text-destructive",
      )}
    >
      {children}
    </button>
  )
}
