import React, { useState, useRef, useCallback } from "react";
import ChatPage from "./pages/ChatPage";
import ResultPage from "./pages/ResultPage";
import HistoryPage from "./pages/HistoryPage";
import { getResult } from "./api";
import { trackEvent } from "./components/EventTracker";
import type { AssessmentResult, ChatMessage } from "./types";

type Tab = "chat" | "result" | "history";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "症状描述" },
  { id: "result", label: "评估结果" },
  { id: "history", label: "历史记录" },
];

function getSessionId(): string {
  let id = sessionStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("session_id", id);
  }
  return id;
}

export default function App() {
  const sessionId = useRef(getSessionId()).current;
  const [activeTab, setActiveTab] = useState<Tab>("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "bot",
      text: "您好，我是您的症状评估助理。请告诉我您目前的身体状况，比如不适感、发生时间、严重程度等。我会帮您评估是否需要关注。",
    },
  ]);
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [loading, setLoading] = useState(false);

  // Called by ChatPage when an assessment completes
  const handleAssessmentResult = useCallback((newResult: AssessmentResult) => {
    setResult(newResult);
    trackEvent("assessment_submitted", sessionId, newResult.assessment_id);
  }, [sessionId]);

  const handleViewResult = useCallback(async (assessmentId: string) => {
    setLoading(true);
    setActiveTab("result");
    try {
      const data = await getResult(assessmentId);
      setResult(data as AssessmentResult);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  function switchTab(tab: Tab) {
    if (activeTab === "result" && tab !== "result" && result) {
      trackEvent("assessment_closed", sessionId, result.assessment_id);
    }
    setActiveTab(tab);
  }

  // Switch to result tab when user wants detail view
  const handleViewDetail = useCallback((r: AssessmentResult) => {
    setResult(r);
    setActiveTab("result");
    trackEvent("result_viewed", sessionId, r.assessment_id);
  }, [sessionId]);

  return (
    <div className="app">
      <div className="tab-bar">
        {TABS.map((t) => (
          <div
            key={t.id}
            className={`tab ${activeTab === t.id ? "active" : ""}`}
            onClick={() => switchTab(t.id)}
          >
            {t.label}
          </div>
        ))}
      </div>

      <div className={`page ${activeTab === "chat" ? "active" : ""}`} id="tab-chat">
        <ChatPage
          messages={messages}
          onMessagesChange={setMessages}
          sessionId={sessionId}
          onAssessmentResult={handleAssessmentResult}
        />
      </div>

      <div className={`page ${activeTab === "result" ? "active" : ""}`} id="tab-result">
        <ResultPage result={result} loading={loading} sessionId={sessionId} />
      </div>

      <div className={`page ${activeTab === "history" ? "active" : ""}`} id="tab-history">
        <HistoryPage sessionId={sessionId} onViewResult={handleViewResult} />
      </div>
    </div>
  );
}
