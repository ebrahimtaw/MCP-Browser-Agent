"use client";

import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Baked in at build time by Next, so it must be set in the Vercel project
// settings *before* the build that should pick it up.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// The backend gives up at 240s; allow a little more so its own 504 (which
// carries a useful message) wins the race against the client aborting.
const CLIENT_TIMEOUT_MS = 280_000;

interface Screenshot {
  url: string;
  title: string;
  /** data:image/jpeg;base64,... of what the headless browser saw. */
  image: string;
}

interface AgentResponse {
  response?: string;
  screenshots?: Screenshot[];
  detail?: string;
}

const SESSION_KEY = "mcp-agent-session-id";

/**
 * One id per browser tab, so two people never share browsing history. Resolved
 * lazily at submit time rather than in an effect: it is only ever needed on the
 * client, and sessionStorage does not exist during server rendering.
 */
function getSessionId(): string {
  try {
    let id = window.sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      window.sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    // Storage blocked (private browsing, third-party cookie rules). A fresh id
    // per request is still correct, it just loses follow-up context.
    return crypto.randomUUID();
  }
}

export default function Home() {
  const [command, setCommand] = useState("");
  const [response, setResponse] = useState("");
  const [screenshots, setScreenshots] = useState<Screenshot[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  // A browsing run routinely takes 30-90s; without a ticking clock the UI
  // looks hung and people reload mid-run.
  useEffect(() => {
    if (!loading) return;
    const started = Date.now();
    const timer = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [loading]);

  async function runCommand() {
    if (!command.trim() || loading) return;

    setLoading(true);
    setResponse("");
    setScreenshots([]);
    setError("");
    setElapsed(0);

    if (!API_URL) {
      setError(
        "NEXT_PUBLIC_API_URL is not set in this build. Set it in the Vercel " +
          "project settings and redeploy.",
      );
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    // `signal.reason` is populated on every abort, so it cannot tell a timeout
    // apart from a user cancel. Track which one fired explicitly.
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, CLIENT_TIMEOUT_MS);

    try {
      const res = await fetch(`${API_URL}/run_agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: command, session_id: getSessionId() }),
        signal: controller.signal,
      });

      const data = (await res.json().catch(() => ({}))) as AgentResponse;

      if (!res.ok) {
        // FastAPI puts the real reason in `detail`; surfacing it is the
        // difference between a debuggable failure and a blank box.
        setError(data.detail ?? `Request failed with status ${res.status}.`);
        return;
      }
      setResponse(data.response ?? "");
      setScreenshots(data.screenshots ?? []);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError(
          timedOut
            ? `The agent did not respond within ${CLIENT_TIMEOUT_MS / 1000}s.`
            : "Request cancelled.",
        );
      } else {
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(
          `Could not reach the agent backend (${message}). It may be asleep — ` +
            "wait a few seconds and try again.",
        );
      }
    } finally {
      clearTimeout(timeout);
      abortRef.current = null;
      setLoading(false);
    }
  }

  function cancel() {
    abortRef.current?.abort();
  }

  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6 py-16 text-center">
      {/* Animated background circles */}
      <div className="circles">
        <div className="circle"></div>
        <div className="circle"></div>
        <div className="circle"></div>
        <div className="circle"></div>
      </div>

      <motion.h1
        className="font-plusjakarta z-10 bg-gradient-to-r from-white via-gray-300 to-gray-400 bg-clip-text text-5xl font-extrabold text-transparent md:text-6xl"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1 }}
      >
        Chat With Your Browser...
      </motion.h1>

      <motion.p
        className="font-plusjakarta z-10 mt-3 mb-10 text-base text-gray-400 md:text-lg"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
      >
        An intelligent MCP agent that navigates, extracts, and summarizes the
        internet.
      </motion.p>

      <div className="z-10 w-full max-w-xl">
        <textarea
          placeholder="Example: Go to Wikipedia and summarize Artificial Intelligence..."
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              void runCommand();
            }
          }}
          rows={5}
          disabled={loading}
          className="font-plusjakarta w-full resize-none rounded-xl border border-gray-700 bg-black/40 p-4 text-gray-100 backdrop-blur-md focus:ring-2 focus:ring-gray-400 focus:outline-none disabled:opacity-60"
        />

        <div className="mt-4 flex gap-3">
          <button
            onClick={() => void runCommand()}
            disabled={loading || !command.trim()}
            className="font-plusjakarta relative flex-1 rounded-xl border border-gray-700 bg-gradient-to-b from-[#2a2a2a] to-[#1a1a1a] py-3 font-semibold text-gray-200 transition-all duration-300 hover:from-[#3a3a3a] hover:to-[#222222] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? `Browsing... ${elapsed}s` : "Run Command"}
          </button>
          {loading && (
            <button
              onClick={cancel}
              className="font-plusjakarta rounded-xl border border-gray-700 px-5 py-3 text-gray-400 transition-colors hover:text-gray-200"
            >
              Cancel
            </button>
          )}
        </div>

        <p className="font-plusjakarta mt-3 text-xs text-gray-600">
          The agent drives a real headless browser, so a run usually takes
          30&ndash;90 seconds. Press &#8984;/Ctrl + Enter to submit.
        </p>
      </div>

      {error && (
        <motion.div
          className="font-plusjakarta z-10 mt-8 w-full max-w-xl rounded-xl border border-red-900/60 bg-red-950/30 p-6 text-left text-red-200 backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4 }}
        >
          <strong className="text-red-100">Something went wrong</strong>
          <p className="mt-2 text-sm whitespace-pre-wrap">{error}</p>
        </motion.div>
      )}

      {screenshots.length > 0 && (
        <motion.div
          className="z-10 mt-8 w-full max-w-xl text-left"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="font-plusjakarta mb-3 text-sm font-semibold tracking-wide text-gray-400 uppercase">
            What the agent saw
          </h2>
          <div className="flex flex-col gap-4">
            {screenshots.map((shot, i) => (
              <figure
                key={`${shot.url}-${i}`}
                className="overflow-hidden rounded-xl border border-gray-700 bg-black/30 backdrop-blur-md"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- data URI, nothing for the Image optimizer to fetch */}
                <img
                  src={shot.image}
                  alt={shot.title || `Step ${i + 1}`}
                  className="w-full border-b border-gray-800"
                  loading="lazy"
                />
                <figcaption className="font-plusjakarta p-3 text-xs">
                  <span className="text-gray-300">
                    {i + 1}. {shot.title || "Untitled page"}
                  </span>
                  {shot.url && (
                    <span className="mt-1 block break-all text-gray-500">
                      {shot.url}
                    </span>
                  )}
                </figcaption>
              </figure>
            ))}
          </div>
        </motion.div>
      )}

      {response && (
        <motion.div
          className="font-plusjakarta z-10 mt-8 w-full max-w-xl rounded-xl border border-gray-700 bg-black/30 p-6 text-left text-gray-200 shadow-[0_0_20px_rgba(255,255,255,0.05)] backdrop-blur-md transition-all duration-500 hover:shadow-[0_0_30px_rgba(255,255,255,0.08)]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6 }}
        >
          <strong className="text-white">Response:</strong>
          {/* The agent is instructed to answer in Markdown, so render it as
              such instead of dumping the raw source on the page. */}
          <div className="agent-markdown mt-3 text-gray-300">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{response}</ReactMarkdown>
          </div>
        </motion.div>
      )}
    </main>
  );
}
