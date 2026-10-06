# AI decision flow

A flowchart you can draw in the browser, where **every box is a yes/no question
put to a language model**. The answer picks which arrow the run follows. Drag out
a support triage tree, type in a customer message, press **Run flow**, and watch
it light up box by box.

Execution runs on **Inngest**, one step per node. The canvas is **React Flow**,
and the side panel is built from **shadcn/ui** components.

Verified on 6 Oct 2026 against a real model running on my laptop:
**qwen3.5:4b on Ollama**. No account, no key, no cost.

![The editor after a completed run](docs/run-refund.png)

Green boxes have been visited and carry the answer they gave. The blue dashed
line is the path actually taken. The panel on the right is the execution log.

## Run it — two terminals

```bash
npm install
cp .env.example .env.local        # LLM_STUB=1 runs with no model installed

# Terminal 1
npm run dev

# Terminal 2
npx inngest-cli@latest dev -u http://localhost:3000/api/inngest
```

Open **http://localhost:3000** for the editor and **http://localhost:8288** for
the Inngest dashboard.

```bash
npm test      # seven checks, no server and no key needed
```

**Trap — `INNGEST_DEV=1` is not optional.** Without it the JavaScript SDK assumes
it is talking to Inngest Cloud, `/api/inngest` answers **500**, and the log says
`In cloud mode but no signing key found`. The Python SDK infers this from
`is_production=False`; the JS one wants the environment variable. And if the Dev
Server started while that route was broken, it logs *"apps synced, disabling
auto-discovery"* and stops looking — restart it after you fix the route, or your
function list stays empty for no visible reason.

## Using a real model

`LLM_STUB=1` runs everything on keyword rules, so the app works with nothing
installed. For a real model, put this in `.env.local` and restart `npm run dev`
(Next.js reads env files only at startup):

```
LLM_STUB=0
LLM_BASE_URL=http://localhost:11434/v1/
LLM_API_KEY=ollama                 # ignored by Ollama, but the client needs something
LLM_MODEL=qwen3.5:4b
LLM_REASONING_EFFORT=none
```

Then `ollama pull qwen3.5:4b`. A hosted provider is the same three lines with a
different URL, key and model name; the code does not change.

**Trap: a thinking model with `max_tokens: 4` answers nothing.** qwen3.5 writes
a hidden reasoning pass before its answer, and that pass spends the 4-token
budget, so the visible reply comes back empty and every node fails.
`LLM_REASONING_EFFORT=none` switches the thinking off. Leave that line out for a
provider that rejects the field.

The client also sets a **30-second timeout** (the OpenAI SDK default is ten
minutes) and **zero SDK retries**, because Inngest already retries a failed step
and the two would stack.

## Making a model answer only YES or NO

The brief says the model must return only `YES` or `NO`. It won't, left alone.
Models say "Yes.", "**YES**", or a helpful paragraph explaining itself. So the
rule is enforced rather than hoped for, in three layers:

1. **Ask narrowly** — a system prompt saying one word only, `temperature: 0` so
   the same question gives the same answer, and `max_tokens: 4` so it physically
   cannot ramble.
2. **Squeeze the reply** — strip markdown and punctuation, uppercase it, take the
   first word.
3. **Refuse to guess** — if it is still neither word, ask once more, then fail the
   run loudly.

That third point is the one that matters. Guessing a branch would send the run
down the wrong path and never tell anyone, which for a decision tree is the worst
possible failure: a confident wrong answer.

```js
normalize("Yes.")                              // "YES"
normalize("**YES**")                           // "YES"
normalize("NO - the customer wants pricing")   // "NO"
normalize("maybe")                             // null  -> the run fails, loudly
```

## What actually ran

Same flow, three messages, run through Inngest against the real model. I wrote
down the path each one *should* take before running it, so this is a check,
not a judgement made after seeing the answers. 3 of 3 matched:

```
input   : My headphones arrived broken and I want a refund.
  Is this a support request?            -> YES
  Is the customer asking for a refund?  -> YES
  outcome: Send to Refunds              (predicted: Refunds)

input   : The app keeps crashing when I open settings, please help.
  Is this a support request?            -> YES
  Is the customer asking for a refund?  -> NO
  outcome: Send to Support              (predicted: Support)

input   : What does the enterprise plan cost for 50 seats?
  Is this a support request?            -> NO
  outcome: Send to Sales                (predicted: Sales)
```

The model's raw replies were the bare words `YES` and `NO` every time, so the
cleanup step had nothing to fix here. It stays, because the next model will not
be so tidy. Each node took about a second; a whole run, one to two.

Three runs is a smoke test, not an accuracy score. It shows the wiring and the
branching are real, not that the model is right about every message.

![Inngest runs](docs/inngest-runs.png)

## When a flow is wired wrong

Every one of these was run against the real API, not imagined:

```
dead end        -> failed: Node "a" answered YES but has no YES edge.
no start node   -> failed: No start node: every node has an incoming edge.
a real loop     -> failed after 20 steps: the flow probably loops.
empty flow      -> 400: The flow has no nodes
```

**A badly wired flow fails without retrying**, and that is on purpose. Inngest
retries things that might work next time — a model timing out, a network blip. A
node with no YES edge will have no YES edge on the tenth attempt either, and each
retry would re-ask every earlier question and pay for it again.

The 20-step limit exists because a flow drawn in a browser can easily point back
at itself, and without a cap that is an infinite loop billing you per lap.

## One node, one step

```ts
const result = await step.run(`decide-${node.id}`, async () => {
  const { answer, raw } = await decide(node.prompt, input);
  return { nodeId: node.id, prompt: node.prompt, answer, raw };
});
```

Inngest saves each step's result once it succeeds. If the function crashes at
node four, the retry starts at node four — it does not re-ask nodes one to three.
With a paid model that is the difference between one wasted call and four.

## Phase 4 — what I built

- **Visual execution state** — nodes go blue while running, green when done, red on failure
- **Animated active edges** — the path taken is thick, blue and moving
- **Execution logs panel** — every question and its answer, in order
- **Save / load** — `localStorage`, so a refresh doesn't lose your flow
- **JSON export / import** — download a flow, hand it to someone else
- **Error handling** — four different broken-flow cases, each with a readable reason
- **Better node styling** — questions show their answer inline; terminal nodes look different

## Layout

```
src/lib/decide.ts    the only file that talks to a model  (+ the stub)
src/lib/graph.ts     start node, and where an answer leads -- plain functions
src/lib/runs.ts      where runs live while they happen (a Map; a database is the upgrade)
src/inngest/         the function that walks the graph, one step per node
src/app/api/run/     POST to start (202), GET to poll
src/app/page.tsx     the canvas, and the side panel
src/components/ui/   shadcn/ui components: button, textarea, badge, card
```

`graph.ts` is separate from the AI and from Inngest on purpose: it is plain
functions over plain data, which is why the traversal tests run in milliseconds
with no server, no key and no network.

## A bug worth keeping

The stub first read `prompt + input` together as one blob of text. Every question
then answered itself **YES** — because "Is this a **support** request?" contains
the word "support". All three test messages reached the same outcome and it
looked like a working flow.

A stub that always agrees is worse than no stub, because it makes broken wiring
look correct. It only showed up because I ran three inputs that *should* have
diverged and compared the outcomes, rather than checking that one run completed.
