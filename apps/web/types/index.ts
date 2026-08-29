export interface AuthUser {
  id: string;
  email: string;
  username: string;
  is_verified: boolean;
  is_admin: boolean;
}

export interface Profile {
  user_id: string;
  username: string;
  avatar_url: string | null;
  country_code: string;
  xp: number;
  mystery_count: number;
  solved_count: number;
  solve_rate: number;
  current_streak: number;
  longest_streak: number;
  countries_encountered: string[];
  categories_completed: string[];
  average_solve_seconds: number | null;
  badge_count: number;
}

export interface Me {
  id: string;
  email: string;
  is_verified: boolean;
  is_admin: boolean;
  created_at: string;
  profile: Profile;
}

export interface MysteryTeaser {
  id: string;
  category: string;
  difficulty: number;
  summary: string;
}

export interface Clue {
  id: string;
  text: string;
  media_url: string | null;
}

export interface Stage {
  id: string;
  stage_number: number;
  is_final: boolean;
  context: string | null;
  unlocked: boolean;
  your_clue: Clue | null;
}

export interface MysteryDetail {
  id: string;
  title: string;
  category: string;
  difficulty: number;
  flavor_text: string | null;
  stages: Stage[];
}

export interface PartnerTeaser {
  country_code: string;
  timezone_region: string;
  interests: string[];
  language: string;
  puzzle_experience_level: string;
}

export interface Evidence {
  id: string;
  title: string;
  content: string;
  source_url: string | null;
  submitted_by: string;
  created_at: string;
}

export type SessionStatus = "WAITING" | "ACTIVE" | "SOLVED" | "FAILED" | "EXPIRED" | "CANCELLED";

export interface SessionDetail {
  id: string;
  status: SessionStatus;
  current_stage_number: number;
  started_at: string;
  expires_at: string;
  seconds_remaining: number;
  solved_at: string | null;
  your_role: string;
  mystery: MysteryDetail;
  partner: PartnerTeaser | null;
  partner_id: string | null;
  evidence: Evidence[];
  wrong_attempt_count: number;
}

export interface MatchmakingStatus {
  status: "idle" | "waiting" | "matched";
  session_id: string | null;
  expires_at: string | null;
  partner_country_code: string | null;
}

export interface AnswerResponse {
  is_correct: boolean;
  session_status: SessionStatus;
  current_stage_number: number;
  message: string;
  xp_awarded: number;
  new_badges: string[];
}

export interface ChatMessage {
  id: string;
  session_id: string;
  sender_id: string | null;
  type: "normal" | "evidence" | "discovery" | "system" | "partner_joined";
  content: string;
  created_at: string;
}

export interface Badge {
  id: string;
  code: string;
  name: string;
  description: string;
  icon: string;
  earned: boolean;
  earned_at: string | null;
}

export interface Memory {
  id: string;
  session_id: string;
  mystery_title: string;
  partner_country_code: string;
  solved: boolean;
  solve_seconds: number | null;
  anonymous_message: string | null;
  day_number: number;
  created_at: string;
}

export const CATEGORY_LABELS: Record<string, string> = {
  internet_hunt: "Internet Hunt",
  visual: "Visual",
  geo: "Geo Mystery",
  audio: "Audio",
  logic: "Logic",
  cipher: "Cipher",
  investigation: "Investigation",
  pattern: "Pattern",
  arg: "ARG",
};
