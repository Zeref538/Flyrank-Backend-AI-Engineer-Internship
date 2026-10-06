"use client";

import {
  addEdge,
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { sampleGraph } from "@/lib/sample";
import type { Graph, Run } from "@/lib/types";

const STORAGE_KEY = "ai-decision-flow";

/** React Flow speaks its own node/edge shape, so translate at the boundary. */
function toFlow(graph: Graph): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      position: n.position,
      data: { prompt: n.prompt, terminal: !!n.terminal, name: n.label ?? "", label: "" },
      type: "default",
    })),
    edges: graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.branch,
      data: { branch: e.branch },
    })),
  };
}

function fromFlow(nodes: Node[], edges: Edge[]): Graph {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      prompt: String(n.data?.prompt ?? ""),
      terminal: !!n.data?.terminal,
      label: String(n.data?.name ?? ""),
      position: n.position,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      branch: (e.data?.branch as "YES" | "NO") ?? "YES",
    })),
  };
}

function nodeStyle(state: string, terminal: boolean) {
  const background =
    state === "active"
      ? "#1d4ed8"
      : state === "failed"
        ? "#7f1d1d"
        : state === "done"
          ? "#14532d"
          : terminal
            ? "#242938"
            : "#171a21";
  return {
    background,
    color: "#e6e8ec",
    border: "1px solid " + (state === "active" ? "#60a5fa" : "#2a2f3a"),
    borderRadius: 10,
    padding: 10,
    width: 230,
    fontSize: 12,
    whiteSpace: "pre-wrap" as const,
  };
}

export default function Page() {
  const initial = toFlow(sampleGraph);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.edges);
  const [selected, setSelected] = useState<string | null>(null);
  const [input, setInput] = useState("My headphones arrived broken and I want a refund.");
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [branch, setBranch] = useState<"YES" | "NO">("YES");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // localStorage keeps your flow across a refresh. It is per-browser and never
  // reaches the server, which is fine for a draft and wrong for anything shared.
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    try {
      const f = toFlow(JSON.parse(saved) as Graph);
      setNodes(f.nodes);
      setEdges(f.edges);
    } catch {
      /* a corrupt save must not stop the app loading */
    }
  }, [setNodes, setEdges]);

  const save = () => localStorage.setItem(STORAGE_KEY, JSON.stringify(fromFlow(nodes, edges)));

  const onConnect = useCallback(
    (c: Connection) =>
      setEdges((eds) =>
        addEdge({ ...c, id: "e" + Date.now(), label: branch, data: { branch } }, eds),
      ),
    [setEdges, branch],
  );

  const addNode = () => {
    const id = "n" + Date.now().toString(36);
    setNodes((ns) => [
      ...ns,
      {
        id,
        position: { x: 120 + Math.random() * 300, y: 120 + Math.random() * 200 },
        data: { prompt: "New question?", terminal: false, name: "", label: "" },
        type: "default",
      },
    ]);
  };

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(fromFlow(nodes, edges), null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "flow.json";
    a.click();
  };

  const importJson = (file: File) => {
    file.text().then((text) => {
      try {
        const g = JSON.parse(text) as Graph;
        if (!Array.isArray(g.nodes)) throw new Error("no nodes array");
        const f = toFlow(g);
        setNodes(f.nodes);
        setEdges(f.edges);
        setError(null);
      } catch (e) {
        setError("That file is not a flow: " + (e instanceof Error ? e.message : String(e)));
      }
    });
  };

  const start = async () => {
    setError(null);
    setRun(null);
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input, graph: fromFlow(nodes, edges) }),
    });
    const body = await res.json();
    if (!res.ok) {
      setError(body.error ?? "Could not start the run");
      return;
    }

    // 202 came back. From here the client polls until the run stops running --
    // the same accept-then-poll shape as the background job assignment.
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const r = await fetch("/api/run/" + body.runId);
      if (!r.ok) return;
      const current: Run = await r.json();
      setRun(current);
      if (current.status !== "running" && pollRef.current) clearInterval(pollRef.current);
    }, 600);
  };

  // Paint the run onto the canvas: which node is live, which are finished.
  const stepIds = run?.steps.map((s) => s.nodeId) ?? [];
  const lastId = stepIds[stepIds.length - 1];
  const styledNodes = nodes.map((n) => {
    const terminal = !!n.data?.terminal;
    const answered = run?.steps.find((s) => s.nodeId === n.id);
    let state = "idle";
    if (run?.status === "failed" && lastId === n.id) state = "failed";
    else if (run?.status === "running" && lastId === n.id) state = "active";
    else if (stepIds.includes(n.id)) state = "done";
    else if (run?.status === "done" && run.outcome && n.data?.name === run.outcome) state = "done";

    const text = terminal
      ? String(n.data?.name || n.id)
      : String(n.data?.prompt ?? "") + (answered ? "\n→ " + answered.answer : "");
    return { ...n, style: nodeStyle(state, terminal), data: { ...n.data, label: text } };
  });

  // An edge was taken if the run answered its branch at that edge's source node.
  const taken = new Set(
    (run?.steps ?? []).flatMap((s) =>
      edges.filter((e) => e.source === s.nodeId && e.data?.branch === s.answer).map((e) => e.id),
    ),
  );
  const styledEdges = edges.map((e) => ({
    ...e,
    animated: taken.has(e.id),
    style: {
      stroke: taken.has(e.id) ? "#60a5fa" : e.data?.branch === "YES" ? "#4d7c0f" : "#b91c1c",
      strokeWidth: taken.has(e.id) ? 3 : 1.5,
    },
    labelStyle: { fill: "#e6e8ec", fontSize: 11 },
  }));

  const selectedNode = nodes.find((n) => n.id === selected);

  return (
    <main className="flex h-screen">
      <div className="flex-1">
        <ReactFlow
          nodes={styledNodes}
          edges={styledEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, n) => setSelected(n.id)}
          fitView
          colorMode="dark"
        >
          <Background />
          <Controls />
          <MiniMap pannable zoomable />
        </ReactFlow>
      </div>

      <aside className="w-[380px] shrink-0 space-y-5 overflow-y-auto border-l border-border bg-card/40 p-4">
        <div>
          <h1 className="font-heading text-lg font-semibold">AI decision flow</h1>
          <p className="text-xs text-muted-foreground">
            Every node asks the model one question. The answer picks the edge.
          </p>
        </div>

        <div className="space-y-2">
          <label htmlFor="flow-input" className="text-xs text-muted-foreground">
            Text to classify
          </label>
          <Textarea id="flow-input" value={input} onChange={(e) => setInput(e.target.value)} rows={3} />
          <div className="flex flex-wrap gap-2">
            <Button onClick={start}>Run flow</Button>
            <Button variant="outline" onClick={addNode}>
              Add node
            </Button>
            <Button variant="outline" onClick={save}>
              Save
            </Button>
            <Button variant="outline" onClick={exportJson}>
              Export
            </Button>
            <Button variant="outline" onClick={() => fileRef.current?.click()}>
              Import
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && importJson(e.target.files[0])}
            />
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">New connections are the</p>
          <div className="flex gap-2">
            {(["YES", "NO"] as const).map((b) => (
              <Button
                key={b}
                size="sm"
                variant={branch === b ? "default" : "outline"}
                aria-pressed={branch === b}
                className={branch === b ? (b === "YES" ? "bg-lime-700 text-white" : "bg-red-700 text-white") : ""}
                onClick={() => setBranch(b)}
              >
                {b} path
              </Button>
            ))}
          </div>
        </div>

        {selectedNode ? (
          <div className="space-y-2">
            <label htmlFor="node-prompt" className="text-xs text-muted-foreground">
              Prompt for {selectedNode.id}
            </label>
            <Textarea
              id="node-prompt"
              value={String(selectedNode.data?.prompt ?? "")}
              onChange={(e) =>
                setNodes((ns) =>
                  ns.map((n) =>
                    n.id === selected ? { ...n, data: { ...n.data, prompt: e.target.value } } : n,
                  ),
                )
              }
              rows={3}
            />
          </div>
        ) : null}

        {error ? (
          <Card size="sm" className="border-destructive/50 bg-destructive/15">
            <CardContent className="text-xs">{error}</CardContent>
          </Card>
        ) : null}

        <div className="space-y-2">
          <h2 className="text-xs font-medium text-muted-foreground">Execution log</h2>
          {!run ? <p className="text-xs text-muted-foreground">Nothing has run yet.</p> : null}
          {run ? (
            <div className="space-y-3 text-xs">
              <div className="flex items-center gap-2">
                <code className="text-muted-foreground">{run.id}</code>
                <Badge
                  variant={run.status === "failed" ? "destructive" : run.status === "done" ? "default" : "secondary"}
                >
                  {run.status}
                </Badge>
              </div>
              <ol className="space-y-2">
                {run.steps.map((s, i) => (
                  <li key={i} className="rounded-md border border-border p-2">
                    <div>{s.prompt}</div>
                    <Badge
                      variant={s.answer ? "default" : "destructive"}
                      className={
                        "mt-1 " +
                        (s.answer === "YES" ? "bg-lime-700 text-white" : s.answer === "NO" ? "bg-red-700 text-white" : "")
                      }
                    >
                      {s.answer ?? "no answer"}
                    </Badge>
                    {s.error ? <div className="mt-1 text-destructive">{s.error}</div> : null}
                  </li>
                ))}
              </ol>
              {run.outcome ? (
                <Card size="sm" className="border-lime-700/50 bg-lime-900/30">
                  <CardContent>
                    Outcome: <strong>{run.outcome}</strong>
                  </CardContent>
                </Card>
              ) : null}
              {run.error ? (
                <Card size="sm" className="border-destructive/50 bg-destructive/15">
                  <CardContent>{run.error}</CardContent>
                </Card>
              ) : null}
            </div>
          ) : null}
        </div>
      </aside>
    </main>
  );
}
