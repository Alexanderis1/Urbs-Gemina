import { isDirectMode, isSampleMode } from "@/api/client";

export function AiDisclosure() {
  return (
    <div className="bg-stone-900 px-4 py-1 text-center text-xs text-stone-100">
      Answers and reports are prepared with AI assistance from open and simulated data. They support decisions by
      Roma Capitale officers; they do not make them.
    </div>
  );
}

export function SampleModeBanner() {
  if (isDirectMode)
    return (
      <div className="border-b border-stone-200 bg-stone-100 px-4 py-1 text-center text-xs text-stone-600">
        Live data from the public tool API at the citizen tier (no login). Office features need Lovable Cloud sign-in.
      </div>
    );
  if (!isSampleMode) return null;
  return (
    <div className="border-b border-amber-300 bg-amber-50 px-4 py-1 text-center text-xs font-medium text-amber-800">
      SAMPLE DATA · The tool API is not connected, so every value on screen is a placeholder. Labels show the kind each
      layer will have: real, estimated, or simulated (traffic loops only).
    </div>
  );
}
