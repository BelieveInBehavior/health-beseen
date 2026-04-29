import React from "react";
import type { AssessmentResult } from "../types";

const LEVEL_LABEL: Record<string, string> = {
  high: "高风险",
  mid: "中风险",
  low: "低风险",
};

interface Props {
  result: AssessmentResult;
  onViewDetail?: () => void;
}

export default function AssessmentCard({ result, onViewDetail }: Props) {
  const level = result.risk_level;
  return (
    <div className={`assessment-card ${level}`} onClick={onViewDetail}>
      <div className="ac-header">
        <span className={`risk-dot ${level}`} />
        <span className={`ac-level ${level}`}>{LEVEL_LABEL[level] || level}</span>
      </div>
      <div className="ac-advice">{result.advice}</div>
      {result.matched_rules.length > 0 && (
        <div className="ac-rules">
          {result.matched_rules.map((r) => (
            <span key={r.id} className="rule-tag hit">{r.id}</span>
          ))}
        </div>
      )}
      {onViewDetail && <div className="ac-more">点击查看详情 &rarr;</div>}
    </div>
  );
}
