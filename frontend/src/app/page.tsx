"use client";
import { motion } from "framer-motion";
import { useState } from "react";

export default function Home() {
  const [command, setCommand] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);

  async function runCommand() {
    setLoading(true);
    setResponse("");
    try {
      const res = await fetch(process.env.NEXT_PUBLIC_API_URL + "/run_agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: command }),
      });
      const data = await res.json();
      setResponse(data.response);
    } catch (err: any) {
      setResponse("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative flex flex-col items-center justify-center min-h-screen text-center overflow-hidden px-6">
      {/* Animated background circles */}
      <div className="circles">
        <div className="circle"></div>
        <div className="circle"></div>
        <div className="circle"></div>
        <div className="circle"></div>
      </div>

      {/* Title */}
      <motion.h1
        className="text-5xl md:text-6xl font-extrabold z-10 text-transparent bg-clip-text bg-gradient-to-r from-white via-gray-300 to-gray-400 font-plusjakarta"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1 }}
      >
        Chat With Your Browser...
      </motion.h1>

      <motion.p
        className="text-gray-400 mt-3 mb-10 z-10 text-base md:text-lg font-plusjakarta"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
      >
        An intelligent MCP agent that navigates, extracts, and summarizes the internet.
      </motion.p>

      {/* Command input area */}
      <div className="w-full max-w-xl z-10">
        <textarea
          placeholder="Example: Go to Wikipedia and summarize Artificial Intelligence..."
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          rows={5}
          className="w-full p-4 rounded-xl bg-black/40 border border-gray-700 text-gray-100 
          focus:ring-2 focus:ring-gray-400 focus:outline-none resize-none backdrop-blur-md font-plusjakarta"
        />
        <button
          onClick={runCommand}
          disabled={loading}
          className="relative w-full mt-4 py-3 rounded-xl font-semibold font-plusjakarta
          text-gray-200 bg-gradient-to-b from-[#2a2a2a] to-[#1a1a1a]
          border border-gray-700 hover:from-[#3a3a3a] hover:to-[#222222]
          transition-all duration-300"
        >
          {loading ? "Running..." : "Run Command"}
        </button>
      </div>

      {/* Response box */}
      {response && (
        <motion.div
          className="w-full max-w-xl mt-8 p-6 rounded-xl border border-gray-700 
          bg-black/30 backdrop-blur-md text-left text-gray-200 shadow-[0_0_20px_rgba(255,255,255,0.05)] 
          hover:shadow-[0_0_30px_rgba(255,255,255,0.08)] transition-all duration-500 font-plusjakarta"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6 }}
        >
          <strong className="text-white">Response:</strong>
          <p className="mt-2 whitespace-pre-wrap text-gray-300">{response}</p>
        </motion.div>
      )}
    </main>
  );
}