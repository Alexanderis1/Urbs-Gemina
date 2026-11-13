import { isSampleMode } from "@/api/client";

export function AiDisclosure() {
  return (
    <div className="bg-stone-900 px-4 py-1 text-center text-xs text-stone-100">
      Answers and reports are prepared with AI assistance from open and simulated data. They support decisions by
      Roma Capitale officers; they do not make them.
    </div>
  );
}

export function SampleModeBanner() {
  if (!isSampleMode) return null;
  return (
    <div className="border-b border-simulated/40 bg-simulated/10 px-4 py-1 text-center text-xs font-medium text-simulated">
      SIMULATED · Sample-data mode: the tool API is not connected, so every value on screen is a placeholder.
    </div>
  );
}
