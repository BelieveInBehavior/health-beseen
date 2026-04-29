/**
 * Event Tracker SDK — 5 个核心埋点事件上报。
 *
 * 1. assessment_started   — 开始正式评估
 * 2. assessment_submitted  — 收到 SSE complete
 * 3. result_viewed         — 结果页渲染
 * 4. contact_team_clicked  — 点击联系团队
 * 5. assessment_closed     — 离开结果页 / 开始新评估
 */

const API_BASE = "/api";

export type EventName =
  | "assessment_started"
  | "assessment_submitted"
  | "result_viewed"
  | "contact_team_clicked"
  | "assessment_closed";

export async function trackEvent(
  eventName: EventName,
  sessionId: string,
  assessmentId?: string,
  payload?: Record<string, unknown>
): Promise<void> {
  try {
    await fetch(`${API_BASE}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_name: eventName,
        session_id: sessionId,
        assessment_id: assessmentId ?? null,
        payload: payload ?? {},
      }),
    });
  } catch {
    // 埋点失败不阻塞主流程
  }
}
