import { describe, expect, it } from "vitest"

import type { ConversationSummary, Project } from "./api"
import { basename, breadcrumbs, groupConversations } from "./projects"

const project = (id: string): Project => ({
  id,
  name: id,
  path: id,
  created_at: "",
  available: true,
  git_branch: null,
  instructions_file: null,
})

const conversation = (id: string, projectId: string | null): ConversationSummary => ({
  id,
  title: id,
  project_id: projectId,
  created_at: "",
  updated_at: "",
})

describe("groupConversations", () => {
  it("puts each conversation under its project, keeping the order", () => {
    const groups = groupConversations(
      [conversation("c1", "p1"), conversation("c2", null), conversation("c3", "p1")],
      [project("p1"), project("p2")],
    )

    expect(groups.byProject.get("p1")?.map((c) => c.id)).toEqual(["c1", "c3"])
    expect(groups.byProject.get("p2")).toEqual([])
    expect(groups.loose.map((c) => c.id)).toEqual(["c2"])
  })

  it("treats a conversation of an unknown project as a simple chat", () => {
    const groups = groupConversations([conversation("c1", "gone")], [])

    expect(groups.loose.map((c) => c.id)).toEqual(["c1"])
  })
})

describe("breadcrumbs", () => {
  it("gives every step of the path", () => {
    expect(breadcrumbs("apps/web")).toEqual([
      { name: "apps", path: "apps" },
      { name: "web", path: "apps/web" },
    ])
  })

  it("is empty at the root", () => {
    expect(breadcrumbs("")).toEqual([])
  })
})

describe("basename", () => {
  it("keeps the last part of a path", () => {
    expect(basename("/home/me/Projects")).toBe("Projects")
    expect(basename("/workspace/")).toBe("workspace")
  })
})
