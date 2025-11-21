export type QType = "open" | "mc";

export type RaterItem = {
  answerId: string;
  questionId: string;
  userId: string;
  qtype: QType;
  category: string;
  prompt: string | null;
  answer: string | null;
  initialScore: number | null; // 0..1 ή 0..10 ανάλογα τι δίνεις
  createdAt: string;           // ISO string
  teacher01: number | null;    // 0..1
  teacher02: number | null;    // 0..1
};

export type SummaryRow = {
  userId: string;
  total: number;        // σύνολο απαντήσεων για τον χρήστη
  pending: number;      // πόσες εκκρεμούν για αυτόν τον rater
  avgLLM?: number | null;
  avgHuman?: number | null;
  lastAt?: string | null;
};

export type ClearResponse = {
  ok: boolean;
  message?: string;
  before?: Record<string, number>;
  after?: Record<string, number>;
};


export type SubmitRating = { answerId: string; score: number }; // 0..1
