import React, { useRef, useEffect, useState, useCallback } from "react";
import { contactTeam, sendChat } from "../api";
import type { ChatCallbacks } from "../api";
import { trackEvent } from "../components/EventTracker";
import type { AssessmentResult, ChatMessage, HistoryResponse } from "../types";
import AssessmentCard from "../components/AssessmentCard";

function parseRiskLevel(v: unknown): AssessmentResult["risk_level"] | undefined {
  if (v === "high" || v === "mid" || v === "low") return v;
  return undefined;
}

const QUICK_CHIPS = [
  { label: "持续低烧", text: "最近3天持续低烧，37.5°C左右" },
  { label: "皮肤红疹", text: "手臂出现红疹，有点痒" },
  { label: "恶心呕吐", text: "恶心想吐，食欲很差" },
  { label: "注射部位肿痛", text: "注射部位红肿疼痛超过48小时" },
  { label: "胸闷呼吸困难", text: "呼吸有点困难，胸闷" },
];

interface Props {
  messages: ChatMessage[];
  onMessagesChange: (msgs: ChatMessage[]) => void;
  sessionId: string;
  onAssessmentResult?: (result: AssessmentResult) => void;
}

export default function ChatPage({ messages, onMessagesChange, sessionId, onAssessmentResult }: Props) {
  const [input, setInput] = useState("");
  const [chipsVisible, setChipsVisible] = useState(true);
  const [thinking, setThinking] = useState(false);
  const chatAreaRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const onAssessmentResultRef = useRef(onAssessmentResult);
  /** 同一次对话流中，risk 事件先于助手 message 时，把等级挂到下一条文本气泡 */
  const pendingRiskForAssistantMsgRef = useRef<{
    risk_level: AssessmentResult["risk_level"];
    assessment_id: string;
  } | null>(null);

  useEffect(() => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTop = chatAreaRef.current.scrollHeight;
    }
  }, [messages, thinking]);

  useEffect(() => {
    onAssessmentResultRef.current = onAssessmentResult;
  }, [onAssessmentResult]);

  // Build conversation history for the LLM router
  function buildHistory(): { role: string; content: string }[] {
    return messages.map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      content: m.text,
    }));
  }

  function addMsg(
    msgs: ChatMessage[],
    role: "bot" | "user",
    text: string,
    msgType?: ChatMessage["msgType"],
    data?: ChatMessage["data"],
    meta?: Pick<ChatMessage, "risk_level" | "assessment_id">,
  ): ChatMessage[] {
    const next = [...msgs, { role, text, msgType, data, ...meta }];
    onMessagesChange(next);
    return next;
  }

  const doSend = useCallback((text: string) => {
    if (!text.trim()) return;
    setChipsVisible(false);

    // Add user message
    const updated = addMsg(messages, "user", text);
    setThinking(true);

    const history = updated.map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      content: m.text,
    }));

    // Partial assessment result being built during SSE
    let partial: Partial<AssessmentResult> = { session_id: sessionId };
    let intentType = "";

    const callbacks: ChatCallbacks = {
      onIntent: (data) => {
        intentType = data.type;
        if (data.type === "assessment") {
          // Show "evaluating" status
          const thinking_msg: ChatMessage = { role: "bot", text: "正在为您进行症状评估…", msgType: "thinking" };
          onMessagesChange([...updated, thinking_msg]);
        }
      },
      onMessage: (data) => {
        setThinking(false);
        const fromPayloadLevel = parseRiskLevel(data.risk_level);
        const fromPayloadAid = typeof data.assessment_id === "string" ? data.assessment_id : undefined;
        let risk_level = fromPayloadLevel;
        let assessment_id = fromPayloadAid;
        if (risk_level === undefined && pendingRiskForAssistantMsgRef.current) {
          risk_level = pendingRiskForAssistantMsgRef.current.risk_level;
          assessment_id = assessment_id ?? pendingRiskForAssistantMsgRef.current.assessment_id;
        } else if (risk_level === "high" && !assessment_id && pendingRiskForAssistantMsgRef.current?.risk_level === "high") {
          assessment_id = pendingRiskForAssistantMsgRef.current.assessment_id;
        }
        pendingRiskForAssistantMsgRef.current = null;
        const meta =
          risk_level === "high"
            ? { risk_level: "high" as const, ...(assessment_id ? { assessment_id } : {}) }
            : undefined;
        addMsg(updated, "bot", data.content, "text", undefined, meta);
      },
      onRisk: (data) => {
        const level = parseRiskLevel(data.risk_level);
        if (level === "high" && data.assessment_id) {
          pendingRiskForAssistantMsgRef.current = { risk_level: "high", assessment_id: data.assessment_id };
        } else {
          pendingRiskForAssistantMsgRef.current = null;
        }
        partial = { ...partial, risk_level: data.risk_level as AssessmentResult["risk_level"], assessment_id: data.assessment_id };
      },
      onAdvice: (data) => {
        partial = { ...partial, advice: data.advice };
      },
      onEvidence: (data) => {
        partial = { ...partial, evidence: data.evidence };
      },
      onRuleSource: (data) => {
        partial = { ...partial, matched_rules: data.matched_rules, all_evaluated_rules: data.all_evaluated_rules };
      },
      onAudit: (data) => {
        partial = {
          ...partial,
          rule_version: data.rule_version,
          model_version: data.model_version,
          content_hash: data.content_hash,
          created_at: data.created_at,
        };
      },
      onHistory: (data) => {
        setThinking(false);
        const count = data.items.length;
        const summary = count > 0
          ? `共找到 ${count} 条评估记录。高风险 ${data.trend.high} 次、中风险 ${data.trend.mid} 次、低风险 ${data.trend.low} 次。`
          : "暂无评估记录。";
        addMsg(updated, "bot", summary, "history", data);
      },
      onResult: (data) => {
        setThinking(false);
        if ("error" in data) {
          addMsg(updated, "bot", "未找到该评估记录。", "text");
        } else {
          const r = data as AssessmentResult;
          addMsg(updated, "bot", `评估结果 #${r.assessment_id}`, "assessment", r);
          onAssessmentResultRef.current?.(r);
        }
      },
      onContact: (data) => {
        setThinking(false);
        addMsg(updated, "bot", data.message || "已为您提交医疗团队联系请求。", "contact", data);
      },
      onComplete: () => {
        setThinking(false);
        pendingRiskForAssistantMsgRef.current = null;
        if (intentType === "assessment" && partial.assessment_id) {
          const finalResult: AssessmentResult = {
            assessment_id: partial.assessment_id!,
            session_id: sessionId,
            user_input: text,
            symptoms: [],
            risk_level: partial.risk_level || "low",
            advice: partial.advice || "",
            evidence: partial.evidence || "",
            matched_rules: partial.matched_rules || [],
            all_evaluated_rules: partial.all_evaluated_rules || [],
            rule_version: partial.rule_version || "",
            model_version: partial.model_version || "",
            content_hash: partial.content_hash || "",
            created_at: partial.created_at || new Date().toISOString(),
          };
          // Replace the "thinking" message with assessment card（卡片内已有风险展示，不重复挂 message 级 risk_level）
          const withResult = [...updated, {
            role: "bot" as const,
            text: `评估完成 — ${finalResult.risk_level === "high" ? "高风险" : finalResult.risk_level === "mid" ? "中风险" : "低风险"}`,
            msgType: "assessment" as const,
            data: finalResult,
          }];
          onMessagesChange(withResult);
          onAssessmentResultRef.current?.(finalResult);
        }
      },
      onError: (err) => {
        setThinking(false);
        console.error("Chat error:", err);
        addMsg(updated, "bot", "抱歉，处理您的消息时出现了问题，请稍后再试。", "text");
      },
    };

    abortRef.current = sendChat(sessionId, text, history, callbacks);
  }, [messages, sessionId, onMessagesChange]);

  function sendMsg() {
    const val = input.trim();
    if (!val) return;
    setInput("");
    doSend(val);
  }

  function quickSend(text: string) {
    doSend(text);
  }

  return (
    <>
      <div className="chat-area" ref={chatAreaRef}>
        {messages.map((m, i) => {
          // Assessment card
          if (m.role === "bot" && m.msgType === "assessment" && m.data) {
            return (
              <div key={i} className="bubble bot" style={{ maxWidth: "90%", background: "transparent", padding: 0 }}>
                <AssessmentCard
                  result={m.data as AssessmentResult}
                  onViewDetail={() => onAssessmentResult?.(m.data as AssessmentResult)}
                />
              </div>
            );
          }
          // History inline
          if (m.role === "bot" && m.msgType === "history" && m.data) {
            const hd = m.data as HistoryResponse;
            return (
              <div key={i} className="bubble bot" style={{ maxWidth: "90%" }}>
                <div>{m.text}</div>
                {hd.items.length > 0 && (
                  <div className="chat-history-card">
                    <div className="trend-mini">
                      <span className="trend-item"><span className="risk-dot high" /> {hd.trend.high}</span>
                      <span className="trend-item"><span className="risk-dot mid" /> {hd.trend.mid}</span>
                      <span className="trend-item"><span className="risk-dot low" /> {hd.trend.low}</span>
                    </div>
                    <div className="history-list-mini">
                      {hd.items.slice(0, 5).map((item) => (
                        <div key={item.assessment_id} className="history-row">
                          <span className={`h-badge ${item.risk_level}`}>
                            {item.risk_level === "high" ? "高" : item.risk_level === "mid" ? "中" : "低"}
                          </span>
                          <span>{item.summary}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          }
          // Thinking indicator
          if (m.role === "bot" && m.msgType === "thinking") {
            return <div key={i} className="bubble bot thinking">{m.text}</div>;
          }
          // Normal bubble（高风险助手文案旁展示紧急行动按钮）
          return (
            <div key={i} className={`bubble ${m.role}`}>
              <div>{m.text}</div>
              {m.role === "bot" && m.risk_level === "high" && (
                <button
                  type="button"
                  className="contact-btn chat-high-risk-cta"
                  onClick={async () => {
                    if (m.assessment_id) {
                      await contactTeam(m.assessment_id, sessionId, "高风险：立即线下就医/24h联系团队");
                      trackEvent("contact_team_clicked", sessionId, m.assessment_id);
                      alert("已通知医疗团队，请尽快线下就医；团队将在24小时内与您联系。");
                    } else {
                      alert("请尽快前往医院急诊科或门诊就诊。完成一次症状评估后，可在「评估结果」页联系医疗团队。");
                    }
                  }}
                >
                  立即线下就医 / 24h 联系团队
                </button>
              )}
            </div>
          );
        })}
        {thinking && !messages.some(m => m.msgType === "thinking") && (
          <div className="bubble bot typing" />
        )}
      </div>

      {chipsVisible && (
        <div className="quick-chips">
          {QUICK_CHIPS.map((c) => (
            <div key={c.label} className="chip" onClick={() => quickSend(c.text)}>
              {c.label}
            </div>
          ))}
        </div>
      )}

      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="描述您的症状…"
          onKeyDown={(e) => { if (e.key === "Enter") sendMsg(); }}
          disabled={thinking}
        />
        <button className="send-btn" onClick={sendMsg} disabled={thinking}>
          发送
        </button>
      </div>
    </>
  );
}
