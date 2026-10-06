import OpenAI from "openai";
import type { ReasoningEffort } from "openai/resources/shared";

/**
 * Ask the model a yes/no question and get back exactly "YES" or "NO".
 *
 * The brief says "the model must return only YES or NO". It won't, on its own.
 * Models answer "Yes.", "**YES**", or a helpful paragraph. So the rule is
 * enforced here, not hoped for: squeeze the reply down, check it against the two
 * words we accept, and if it is neither, try once more and then fail loudly.
 * Guessing a branch would send the run down the wrong path silently, which is
 * the worst possible failure for a decision tree.
 */

const SYSTEM =
  "You are a strict classifier. Answer with exactly one word: YES or NO. " +
  "No punctuation, no explanation, no other words.";

export function normalize(reply: string): "YES" | "NO" | null {
  // Strip markdown, punctuation and whitespace, then look at the first word.
  const word = reply
    .replace(/[*_`#]/g, "")
    .trim()
    .toUpperCase()
    .split(/[^A-Z]+/)
    .filter(Boolean)[0];
  return word === "YES" || word === "NO" ? word : null;
}

/**
 * Deterministic stand-in so the whole app runs with no API key and no spend.
 *
 * It looks at the INPUT only. An earlier version searched prompt + input
 * together and every question answered itself YES, because "Is this a support
 * request?" contains the word "support". A stub that always agrees is worse
 * than no stub -- it makes a broken flow look like a working one.
 */
const TOPICS: Record<string, string[]> = {
  support: ["broken", "crash", "crashing", "not working", "error", "bug", "help", "issue", "problem", "refund"],
  refund: ["refund", "money back", "return it", "reimburse"],
  sales: ["price", "pricing", "cost", "costs", "quote", "plan", "enterprise", "buy"],
  urgent: ["urgent", "asap", "immediately", "critical"],
};

function stubAnswer(prompt: string, input: string): string {
  const question = prompt.toLowerCase();
  const text = input.toLowerCase();
  const topic = Object.keys(TOPICS).find((t) => question.includes(t));
  if (topic) return TOPICS[topic].some((w) => text.includes(w)) ? "YES" : "NO";
  // No topic recognised: fall back to any meaningful word from the question
  // appearing in the text, so custom prompts still branch both ways.
  const words = question.replace(/[^a-z ]/g, " ").split(/ +/).filter((w) => w.length > 4);
  return words.some((w) => text.includes(w)) ? "YES" : "NO";
}

export const usingStub = () =>
  process.env.LLM_STUB === "1" || !process.env.LLM_API_KEY;

export async function decide(prompt: string, input: string): Promise<{ answer: "YES" | "NO"; raw: string }> {
  if (usingStub()) {
    const raw = stubAnswer(prompt, input);
    return { answer: raw as "YES" | "NO", raw };
  }

  const client = new OpenAI({
    apiKey: process.env.LLM_API_KEY,
    baseURL: process.env.LLM_BASE_URL || "http://localhost:11434/v1/",
    // The SDK waits TEN MINUTES by default and retries twice on its own. Inngest
    // already retries a failed step, so the SDK's retries would stack on top.
    timeout: Number(process.env.LLM_TIMEOUT_MS || 30_000),
    maxRetries: 0,
  });
  // Reasoning models (qwen3.5 on Ollama) think before answering, and with
  // max_tokens 4 the thinking eats the whole budget: the visible answer comes
  // back empty. LLM_REASONING_EFFORT=none switches thinking off. Unset = not sent,
  // because not every provider accepts the field.
  const effort = process.env.LLM_REASONING_EFFORT as ReasoningEffort | undefined;

  let last = "";
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await client.chat.completions.create({
      model: process.env.LLM_MODEL || "qwen3.5:4b",
      temperature: 0,          // same question, same answer
      max_tokens: 4,           // it cannot ramble if it has no room to
      ...(effort ? { reasoning_effort: effort } : {}),
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: `Question: ${prompt}\n\nText: ${input}` },
      ],
    });
    last = res.choices[0]?.message?.content ?? "";
    const answer = normalize(last);
    if (answer) return { answer, raw: last };
  }
  throw new Error(`Model would not answer YES or NO. Last reply: ${JSON.stringify(last)}`);
}
