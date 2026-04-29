import React, { useEffect } from "react";
import type { AssessmentResult, RuleHit } from "../types";
import RiskBadge from "../components/RiskBadge";
import { trackEvent } from "../components/EventTracker";
import { contactTeam } from "../api";

interface Props {
  result: AssessmentResult | null;
  loading: boolean;
  sessionId: string;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function ResultPage({ result, loading, sessionId }: Props) {
  useEffect(() => {
    if (result) {
      trackEvent("result_viewed", sessionId, result.assessment_id);
    }
  }, [result, sessionId]);

  if (loading) {
    return (
      <div className="result-loading">
        <div className="spinner" />
        <span>评估中，请稍候…</span>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="result-loading">
        <span style={{ color: "var(--text-secondary)" }}>
          暂无评估结果，请先在"症状描述"页面提交评估
        </span>
      </div>
    );
  }

  const matchedIds = new Set(result.matched_rules.map((r) => r.id));

  async function handleContact() {
    if (!result) return;
    await contactTeam(result.assessment_id, sessionId, "用户主动联系");
    trackEvent("contact_team_clicked", sessionId, result.assessment_id);
    alert("已向医疗团队发送协同请求，团队将在24小时内联系您。");
  }

  return (
    <div className="result-scroll">
      <RiskBadge level={result.risk_level} />

      <div className="section-card">
        <div className="section-title">下一步建议</div>
        <div className="advice-text">{result.advice}</div>
      </div>

      <div className="section-card">
        <div className="section-title">命中规则</div>
        <div style={{ marginBottom: 8 }}>
          {result.matched_rules.map((r) => (
            <span key={r.id} className="rule-tag hit">{r.id}: {r.keywords_matched.join("、")}</span>
          ))}
          {result.all_evaluated_rules
            .filter((id) => !matchedIds.has(id))
            .slice(0, 4)
            .map((id) => (
              <span key={id} className="rule-tag">{id}</span>
            ))}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          绿色标签 = 本次命中规则
        </div>
      </div>

      <div className="section-card">
        <div className="section-title">审计信息</div>
        <div className="audit-row"><span>生成时间</span><span>{formatTime(result.created_at)}</span></div>
        <div className="audit-row"><span>规则版本</span><span>{result.rule_version}</span></div>
        <div className="audit-row"><span>模型版本</span><span>{result.model_version}</span></div>
        <div className="audit-row">
          <span>Assessment ID</span>
          <span style={{ fontFamily: "monospace" }}>#{result.assessment_id}</span>
        </div>
        <div className="audit-row">
          <span>内容哈希</span>
          <span style={{ fontFamily: "monospace", fontSize: 10 }}>{result.content_hash.slice(0, 16)}…</span>
        </div>
      </div>

      <div className="section-card">
        <div className="section-title">证据依据</div>
        <div className="advice-text" style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {result.evidence}
        </div>
      </div>

      {result.risk_level === "high" && (
        <button className="contact-btn" onClick={handleContact}>
          联系医疗团队
        </button>
      )}
    </div>
  );
}
