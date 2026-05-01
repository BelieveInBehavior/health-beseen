import type { AssessmentResult, HistoryResponse, RuleHit } from "./types";

// ──────────────── Chat API (Agent 模式) ────────────────

export interface ChatCallbacks {
  onIntent?: (data: { type: string }) => void;
  onMessage?: (data: { content: string }) => void;
  onRisk?: (data: { risk_level: string; assessment_id: string }) => void;
  onAdvice?: (data: { advice: string }) => void;
  onEvidence?: (data: { evidence: string }) => void;
  onRuleSource?: (data: { matched_rules: RuleHit[]; all_evaluated_rules: string[] }) => void;
  onAudit?: (data: {
    rule_version: string;
    model_version: string;
    content_hash: string;
    created_at: string;
    assessment_id: string;
  }) => void;
  onHistory?: (data: HistoryResponse) => void;
  onResult?: (data: AssessmentResult) => void;
  onContact?: (data: { id: string; status: string; message: string }) => void;
  /** 工作区工具（list_files / read_file / read_document / write_file / delete_file / bash）原始结果 */
  onToolResult?: (data: { tool: string; result: Record<string, unknown> }) => void;
  onComplete?: (data: { status: string; assessment_id?: string }) => void;
  onError?: (err: unknown) => void;
}

interface ParsedSSEEvent {
  eventName: string;
  data: unknown;
}

function parseSSEChunk(part: string): ParsedSSEEvent | null {
  const lines = part.trim().split(/\r?\n/);
  let eventName = "";
  let dataStr = "";

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      // Support both `data:xxx` and `data: xxx`
      dataStr += line.slice("data:".length).trim();
    }
  }

  if (!eventName || !dataStr) return null;

  try {
    return { eventName, data: JSON.parse(dataStr) };
  } catch {
    return null;
  }
}

/** 统一对话入口 — SSE 流式接收 */
export function sendChat(
  sessionId: string,
  message: string,
  history: { role: string; content: string }[],
  callbacks: ChatCallbacks,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message,
          history,
        }),
        signal: controller.signal,
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const parsedEvent = parseSSEChunk(part);
          if (!parsedEvent) continue;
          const { eventName, data: parsed } = parsedEvent;
          switch (eventName) {
            case "intent": callbacks.onIntent?.(parsed); break;
            case "message": callbacks.onMessage?.(parsed); break;
            case "risk": callbacks.onRisk?.(parsed); break;
            case "advice": callbacks.onAdvice?.(parsed); break;
            case "evidence": callbacks.onEvidence?.(parsed); break;
            case "rule_source": callbacks.onRuleSource?.(parsed); break;
            case "audit": callbacks.onAudit?.(parsed); break;
            case "history": callbacks.onHistory?.(parsed); break;
            case "result": callbacks.onResult?.(parsed); break;
            case "contact": callbacks.onContact?.(parsed); break;
            case "tool_result": callbacks.onToolResult?.(parsed as { tool: string; result: Record<string, unknown> }); break;
            case "complete": callbacks.onComplete?.(parsed); break;
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        callbacks.onError?.(err);
      }
    }
  })();

  return controller;
}

const API_BASE = "http://localhost:8000/api";

/** 提交评估 — 通过 SSE 流式接收结果 */
export function submitAssessment(
  sessionId: string,
  userInput: string,
  onRisk: (data: { risk_level: string; assessment_id: string }) => void,
  onAdvice: (data: { advice: string }) => void,
  onEvidence: (data: { evidence: string }) => void,
  onRuleSource: (data: { matched_rules: RuleHit[]; all_evaluated_rules: string[] }) => void,
  onAudit: (data: {
    rule_version: string;
    model_version: string;
    content_hash: string;
    created_at: string;
    assessment_id: string;
  }) => void,
  onComplete: (data: { assessment_id: string }) => void,
  onError?: (err: unknown) => void
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(`${API_BASE}/assess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          user_input: userInput,
        }),
        signal: controller.signal,
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const parsedEvent = parseSSEChunk(part);
          if (!parsedEvent) continue;
          const { eventName, data: parsed } = parsedEvent;
          switch (eventName) {
            case "risk": onRisk(parsed); break;
            case "advice": onAdvice(parsed); break;
            case "evidence": onEvidence(parsed); break;
            case "rule_source": onRuleSource(parsed); break;
            case "audit": onAudit(parsed); break;
            case "complete": onComplete(parsed); break;
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError?.(err);
      }
    }
  })();

  return controller;
}

/** 获取单条评估结果 */
export async function getResult(assessmentId: string): Promise<AssessmentResult> {
  const resp = await fetch(`${API_BASE}/result/${assessmentId}`);
  return resp.json();
}

/** 获取历史记录 */
export async function getHistory(sessionId: string): Promise<HistoryResponse> {
  const resp = await fetch(`${API_BASE}/history?session_id=${sessionId}`);
  return resp.json();
}

/** 创建协同请求 */
export async function contactTeam(
  assessmentId: string,
  sessionId: string,
  reason: string = ""
): Promise<{ id: string; status: string }> {
  const resp = await fetch(`${API_BASE}/contact-team`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      assessment_id: assessmentId,
      session_id: sessionId,
      reason,
    }),
  });
  return resp.json();
}
