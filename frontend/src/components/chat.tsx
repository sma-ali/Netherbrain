"use client"

import {
  BookOpen,
  BrainCircuit,
  Folder,
  GitBranch,
  RotateCw,
  SquarePen,
  Wrench,
} from "lucide-react"
import { useSearchParams } from "next/navigation"
import { useEffect, useRef, useState } from "react"

import { AddProjectDialog } from "@/components/add-project-dialog"
import { AppNav } from "@/components/app-nav"
import { Composer } from "@/components/composer"
import { ConversationTree } from "@/components/conversation-tree"
import { Message } from "@/components/message"
import { ModelPicker } from "@/components/model-picker"
import { Sidebar } from "@/components/sidebar"
import { Button } from "@/components/ui/button"
import { useChat } from "@/hooks/use-chat"
import { useModels } from "@/hooks/use-models"
import { useSavedList } from "@/hooks/use-saved-list"
import {
  deleteConversation,
  deleteDocument,
  deleteProject,
  listConversations,
  listDocuments,
  listProjects,
  modelKey,
  type ConversationSummary,
  type Project,
  type ProviderStatus,
} from "@/lib/api"
import { cn } from "@/lib/utils"

export function Chat() {
  const models = useModels()
  const conversations = useSavedList(listConversations, deleteConversation)
  // On enregistre tant que l'historique répond. S'il est indisponible, le chat continue
  // de fonctionner sans rien enregistrer (dégradation gracieuse).
  const { conversationId, messages, status, send, stop, open, reset, approve } = useChat({
    persist: conversations.status !== "error",
    onSaved: conversations.refresh,
  })

  const projects = useSavedList(listProjects, deleteProject)
  // Le projet de la conversation affichée, ou celui d'une nouvelle conversation.
  const [projectId, setProjectId] = useState<string | null>(null)
  const project = projects.items.find((p) => p.id === projectId) ?? null
  const [addingProject, setAddingProject] = useState(false)

  // Mode agent : il faut un projet dont le dossier existe, et un modèle qui sait appeler
  // des outils. Sans l'historique côté serveur, il n'y a même pas de conversation.
  const [agent, setAgent] = useState(false)

  const documents = useSavedList(listDocuments, deleteDocument)
  const readyDocuments = documents.items.filter((d) => d.status === "ready").length
  const [useDocuments, setUseDocuments] = useState(false)
  // Le RAG n'a de sens qu'avec l'historique (côté serveur) et au moins un document prêt.
  const canUseDocuments = conversations.status !== "error" && readyDocuments > 0

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
    open(conversation.id)
  }

  const newChat = (inProject: string | null) => {
    setProjectId(inProject)
    reset()
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this conversation?")) return
    try {
      await conversations.remove(id)
      if (id === conversationId) reset()
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
  const agentHint = !project
    ? "Start a chat inside a project first"
    : !project.available
      ? "The project's folder is missing"
      : model?.tools !== true
        ? `${model?.id ?? "This model"} cannot use tools`
        : "Let the model read, search and change the project's files"

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

      <div className="flex min-w-0 flex-1 flex-col">
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
          <div className="mb-2 flex gap-2">
            <button
              type="button"
              aria-pressed={agent && canUseAgent}
              disabled={!canUseAgent}
              onClick={() => setAgent((value) => !value)}
              title={agentHint}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50",
                agent &&
                  canUseAgent &&
                  "border-primary bg-primary/15 text-primary hover:bg-primary/20",
              )}
            >
              <Wrench className="size-3.5" />
              Agent
            </button>
            <button
              type="button"
              aria-pressed={useDocuments && canUseDocuments}
              disabled={!canUseDocuments}
              onClick={() => setUseDocuments((value) => !value)}
              title={
                canUseDocuments
                  ? "Answer from your documents, with citations"
                  : "Import documents first, on the Documents page"
              }
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50",
                useDocuments &&
                  canUseDocuments &&
                  "border-primary bg-primary/15 text-primary hover:bg-primary/20",
              )}
            >
              <BookOpen className="size-3.5" />
              Use my documents{readyDocuments > 0 && ` (${readyDocuments})`}
            </button>
          </div>
          <Composer
            onSend={(text) =>
              model &&
              send(text, model, {
                useDocuments: useDocuments && canUseDocuments,
                projectId,
                agent: agent && canUseAgent,
              })
            }
            onStop={stop}
            streaming={streaming}
            disabled={!model}
            placeholder={
              agent && canUseAgent
                ? `Ask the agent to change ${project?.name}…`
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
}

function EmptyState({ error, ready, hasModels, unavailable, onRetry, project }: EmptyStateProps) {
  const retry = (
    <Button variant="outline" size="sm" onClick={onRetry}>
      <RotateCw />
      Retry
    </Button>
  )

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
        <div className="flex flex-col items-center gap-2 text-sm">
          <p className="text-destructive">No model available. Is Ollama running?</p>
          {retry}
        </div>
      ) : project ? (
        <p className="max-w-md text-sm text-muted-foreground">
          New chat in this project. The model sees its list of files
          {project.instructions_file && ` and follows its ${project.instructions_file}`}.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Pick a model and ask anything. Local models run on your own GPU.
        </p>
      )}
      {!error && unavailable.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Unavailable right now: {unavailable.map((p) => p.name).join(", ")}.
          {hasModels && " The other models still work."}
        </p>
      )}
    </div>
  )
}
