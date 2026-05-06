export interface RuleHit {
  id: string;
  level: string;
  keywords_matched: string[];
  advice: string;
  evidence: string;
  matched_by?: "keyword" | "semantic" | "llm";
}

export interface AssessmentResult {
  assessment_id: string;
  session_id: string;
  user_input: string;
  symptoms: string[];
  risk_level: "high" | "mid" | "low";
  advice: string;
  evidence: string;
  matched_rules: RuleHit[];
  all_evaluated_rules: string[];
  rule_version: string;
  model_version: string;
  content_hash: string;
  created_at: string;
}

export interface HistoryItem {
  assessment_id: string;
  risk_level: "high" | "mid" | "low";
  summary: string;
  rule_version: string;
  created_at: string;
}

export interface HistoryResponse {
  trend: { high: number; mid: number; low: number };
  items: HistoryItem[];
}

export interface ChatMessage {
  role: "bot" | "user";
  text: string;
  msgType?: "text" | "assessment" | "history" | "contact" | "thinking";
  data?: AssessmentResult | HistoryResponse | Record<string, unknown>;
  /** 来自 SSE message 或紧随 risk 事件的助手文本，用于高风险行动条 */
  risk_level?: "high" | "mid" | "low";
  assessment_id?: string;
}
