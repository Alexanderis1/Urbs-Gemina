// Lovable Cloud (Supabase) client. Lovable sets these two variables when the project uses Cloud.
// Without them the app runs without login (sample mode, demo tier switch).
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const URL = (import.meta.env.VITE_SUPABASE_URL as string | undefined) ?? "";
const KEY = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined) ?? "";

export const supabase: SupabaseClient | null = URL && KEY ? createClient(URL, KEY) : null;
export const SUPABASE_URL = URL;
