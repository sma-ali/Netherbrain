"use client"

import { BrainCircuit, Folder, GitBranch, RotateCw, SquarePen, Upload, Wrench } from "lucide-react"
import { useSearchParams } from "next/navigation"
import { useEffect, useRef, useState, type DragEvent } from "react"

import { AddProjectDialog } from "@/components/add-project-dialog"
import { AppNav } from "@/components/app-nav"
import { AttachmentChips } from "@/components/attachment-chips"
import { Composer } from "@/components/composer"
import { ConversationTree } from "@/components/conversation-tree"
import { Message } from "@/components/message"
import { ModelPicker } from "@/components/model-picker"
import { Sidebar } from "@/components/sidebar"
import { Button } from "@/components/ui/button"
import { useAttachments } from "@/hooks/use-attachments"
import { useChat } from "@/hooks/use-chat"
import { useModels } from "@/hooks/use-models"
import { useSavedList } from "@/hooks/use-saved-list"
import {
  deleteConversation,
  deleteProject,
  listConversations,
  listProjects,
  modelKey,
  type ConversationSummary,
  type Project,
  type ProviderStatus,
} from "@/lib/api"
import { filesFromDrop, imageBlocker, type PickedFile } from "@/lib/attachments"
import { cn } from "@/lib/utils"

export function Chat() {
  const models = useModels()
  const conversations = useSavedList(listConversations, deleteConversation)
  // On enregistre tant que l'historique répond. S'il est indisponible, le chat continue
  // de fonctionner sans rien enregistrer (dégradation gracieuse).
  const { conversationId, messages, status, send, stop, open, reset, approve, ensureConversation } =
    useChat({
      persist: conversations.status !== "error",
      onSaved: conversations.refresh,
    })

  const projects = useSavedList(listProjects, deleteProject)
  // Le projet de la conversation affichée, ou celui d'une nouvelle conversation.
  const [projectId, setProjectId] = useState<string | null>(null)
  const project = projects.items.find((p) => p.id === projectId) ?? null
  const [addingProject, setAddingProject] = useState(false)

  // Mode agent : actif par défaut, comme dans Claude Code, dès qu'il est possible (un projet
  // dont le dossier existe, et un modèle qui sait appeler des outils).
  const [agent, setAgent] = useState(true)

  // Les fichiers joints partent avec le prochain message. Ils vivent côté serveur : sans
  // l'historique, on ne peut pas en joindre.
  const attachments = useAttachments()
  const canAttach = conversations.status !== "error"
  const [dragging, setDragging] = useState(false)

  const searchParams = useSearchParams()
  // Le catalogue peut présélectionner un modèle via l'URL : /?model=ollama/qwen3:8b
  const [selectedKey, setSelectedKey] = useState<string | null>(() => searchParams.get("model"))
  // État dérivé : on prend le premier modèle (les locaux sont en tête) tant que l'utilisateur
  // n'en a pas choisi un.
  const model = models.models.find((m) => modelKey(m) === selectedKey) ?? models.models[0] ?? null

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  // Suit la réponse pendant qu'elle s'affiche, sauf si l'utilisateur est remonté pour lire.
  useEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [messages])

  const handleScroll = () => {
    const el = scrollRef.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  const openConversation = (conversation: ConversationSummary) => {
    setProjectId(conversation.project_id)
    attachments.clear()
    open(conversation.id)
  }

  const newChat = (inProject: string | null) => {
    setProjectId(inProject)
    attachments.clear()
    reset()
  }

  const attach = (picked: PickedFile[]) => {
    if (canAttach) void attachments.add(picked, () => ensureConversation(projectId))
  }

  // Glisser-déposer : des fichiers ou des dossiers entiers, n'importe où sur la conversation.
  const carriesFiles = (event: DragEvent) => event.dataTransfer.types.includes("Files")

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!canAttach || !carriesFiles(event)) return
    event.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    // dragleave se déclenche aussi en passant sur un élément enfant : on n'efface la zone
    // de dépôt qu'en quittant vraiment la conversation.
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!canAttach || !carriesFiles(event)) return
    event.preventDefault()
    setDragging(false)
    void filesFromDrop(event.dataTransfer).then(attach)
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this conversation?")) return
    try {
      await conversations.remove(id)
      if (id === conversationId) newChat(projectId)
    } catch (error) {
      window.alert(error instanceof Error ? error.message : String(error))
    }
  }

  const handleDeleteProject = async (removed: Project) => {
    const question = `Remove the project "${removed.name}"? Its conversations are kept, and its folder is not touched.`
    if (!window.confirm(question)) return
    try {
      await projects.remove(removed.id)
      if (removed.id === projectId) setProjectId(null)
      // Ses conversations n'ont plus de projet : elles passent dans « Chats ».
      conversations.refresh()
    } catch (error) {
      window.alert(error instanceof Error ? error.message : String(error))
    }
  }

  const handleProjectCreated = (created: Project) => {
    setAddingProject(false)
    projects.refresh()
    newChat(created.id)
  }

  const streaming = status === "streaming"
  const canUseAgent =
    conversations.status !== "error" &&
    project !== null &&
    project.available &&
    model?.tools === true
  const agentOn = agent && canUseAgent
  const agentHint = !project?.available
    ? "The project's folder is missing"
    : model?.tools !== true
      ? `${model?.id ?? "This model"} cannot use tools: pick another model`
      : agentOn
        ? "The model can read, search and change the project's files, asking you first"
        : "Let the model read, search and change the project's files"

  const handleSend = (text: string) => {
    if (!model) return
    void send(text, model, { projectId, agent: agentOn, attachments: attachments.ready })
    attachments.clear()
  }

  return (
    <div className="flex h-dvh">
      <Sidebar>
        <ConversationTree
          projects={projects.items}
          conversations={conversations.items}
          status={conversations.status}
          activeConversationId={conversationId}
          activeProjectId={projectId}
          onSelect={openConversation}
          onNewChat={newChat}
          onDelete={handleDelete}
          onAddProject={() => setAddingProject(true)}
          onDeleteProject={handleDeleteProject}
        />
      </Sidebar>
      <AddProjectDialog
        open={addingProject}
        onOpenChange={setAddingProject}
        onCreated={handleProjectCreated}
      />

      <div
        className="relative flex min-w-0 flex-1 flex-col"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {dragging && (
          <div className="pointer-events-none absolute inset-3 z-20 flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-primary bg-background/85 text-center backdrop-blur-sm">
            <Upload className="size-8 text-primary" />
            <p className="font-medium">Drop files or folders to attach them</p>
            <p className="text-xs text-muted-foreground">
              Images, PDFs and any text file: code, Markdown, CSV…
            </p>
          </div>
        )}

        <header className="flex items-center gap-3 border-b px-4 py-2.5">
          <AppNav compact className="md:hidden" />
          {project && <ProjectBadge project={project} />}
          <div className="ml-auto flex items-center gap-2">
            <ModelPicker
              models={models.models}
              providers={models.providers}
              value={model ? modelKey(model) : null}
              onChange={setSelectedKey}
              loading={models.status === "loading"}
              disabled={streaming}
            />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => newChat(projectId)}
              disabled={messages.length === 0}
              aria-label="New chat"
            >
              <SquarePen />
            </Button>
          </div>
        </header>

        <main ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
            {messages.length === 0 ? (
              <EmptyState
                error={models.error}
                ready={models.status === "ready"}
                hasModels={models.models.length > 0}
                unavailable={models.providers.filter((p) => !p.available)}
                onRetry={models.retry}
                project={project}
                agent={agentOn}
              />
            ) : (
              messages.map((message, index) => (
                <Message
                  key={message.id}
                  message={message}
                  streaming={streaming && index === messages.length - 1}
                  onApprove={approve}
                />
              ))
            )}
          </div>
        </main>

        <footer className="mx-auto w-full max-w-3xl px-4 pb-4">
          <Composer
            onSend={handleSend}
            onStop={stop}
            streaming={streaming}
            disabled={!model}
            busy={attachments.busy}
            blocked={imageBlocker(attachments.items, model, models.models)}
            onAttach={canAttach ? attach : undefined}
            attachments={
              attachments.items.length > 0 ? (
                <AttachmentChips items={attachments.items} onRemove={attachments.remove} />
              ) : undefined
            }
            toolbar={
              project && (
                <button
                  type="button"
                  aria-pressed={agentOn}
                  disabled={!canUseAgent}
                  onClick={() => setAgent((value) => !value)}
                  title={agentHint}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50",
                    agentOn && "border-primary bg-primary/15 text-primary hover:bg-primary/20",
                  )}
                >
                  <Wrench className="size-3.5" />
                  Agent
                </button>
              )
            }
            placeholder={
              agentOn
                ? `Ask the agent to work on ${project?.name}…`
                : project && model
                  ? `Ask about ${project.name}…`
                  : undefined
            }
          />
        </footer>
      </div>
    </div>
  )
}

/** Le projet de la conversation, comme l'en-tête de Claude Code : dossier, branche, consignes. */
function ProjectBadge({ project }: { project: Project }) {
  return (
    <div className="flex min-w-0 items-center gap-3 text-sm">
      <span className="flex min-w-0 items-center gap-1.5 font-medium" title={project.path}>
        <Folder className="size-4 shrink-0 text-primary" />
        <span className="truncate">{project.name}</span>
      </span>
      {project.git_branch && (
        <span className="hidden items-center gap-1 font-mono text-xs text-muted-foreground sm:flex">
          <GitBranch className="size-3.5" />
          {project.git_branch}
        </span>
      )}
      {project.instructions_file && (
        <span
          className="hidden font-mono text-xs text-muted-foreground lg:inline"
          title="Sent to the model as the project's instructions"
        >
          {project.instructions_file}
        </span>
      )}
      {!project.available && <span className="text-xs text-destructive">Folder not found</span>}
    </div>
  )
}

interface EmptyStateProps {
  error: string | null
  ready: boolean
  hasModels: boolean
  unavailable: ProviderStatus[]
  onRetry: () => void
  project: Project | null
  agent: boolean
}

function EmptyState({
  error,
  ready,
  hasModels,
  unavailable,
  onRetry,
  project,
  agent,
}: EmptyStateProps) {
  const retry = (
    <Button variant="outline" size="sm" onClick={onRetry}>
      <RotateCw />
      Retry
    </Button>
  )
  // Ollama (le fournisseur local) arrêté : le cas le plus fréquent, avec la commande pour le relancer.
  const localDown = unavailable.some((provider) => provider.local)

  return (
    <div className="flex flex-col items-center gap-3 pt-[18vh] text-center">
      <BrainCircuit className="size-12 text-primary" strokeWidth={1.5} />
      <h1 className="text-2xl font-semibold tracking-tight">
        {project ? project.name : "Many minds, one interface."}
      </h1>
      {error ? (
        <div className="flex flex-col items-center gap-2 text-sm">
          <p className="text-destructive">{error}</p>
          {retry}
        </div>
      ) : ready && !hasModels ? (
        <p className="text-sm text-destructive">No model available.</p>
      ) : project ? (
        <p className="max-w-md text-sm text-muted-foreground">
          {agent
            ? "The agent can read, search and change this project's files. It asks before writing anything or running a command."
            : "New chat in this project. The model sees its list of files."}
          {project.instructions_file && ` It follows ${project.instructions_file}.`}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Pick a model and ask anything. Drop files, folders or images to talk about them.
        </p>
      )}
      {!error && unavailable.length > 0 && (
        <div className="flex max-w-md flex-col items-center gap-2 text-xs text-muted-foreground">
          <p>
            Unavailable right now: {unavailable.map((p) => p.name).join(", ")}.
            {hasModels && " The other models still work."}
          </p>
          {localDown && (
            <p>
              Local models need Ollama running. On Linux or WSL:{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono">
                sudo systemctl start ollama
              </code>
            </p>
          )}
          {retry}
        </div>
      )}
    </div>
  )
}
