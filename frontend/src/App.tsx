function App() {
  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center px-4">
      <main className="flex flex-col items-center gap-4 text-center">
        <h1 className="text-4xl font-semibold text-white tracking-tight">
          Market Briefing Agent
        </h1>
        <p className="text-zinc-400 text-lg max-w-md">
          Watch an AI agent research a stock — every step cited.
        </p>
        <span className="mt-2 inline-flex items-center rounded-full border border-cyan-400 px-3 py-1 text-xs font-medium text-cyan-400">
          coming soon
        </span>
      </main>
      <footer className="fixed bottom-4 text-xs text-zinc-400">
        Educational project — not financial advice.
      </footer>
    </div>
  );
}

export default App;
