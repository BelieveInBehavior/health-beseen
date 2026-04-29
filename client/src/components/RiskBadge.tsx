import React from "react";

interface Props {
  level: "high" | "mid" | "low";
  size?: "normal" | "small";
}

const LABELS: Record<string, string> = {
  high: "高风险",
  mid: "中风险",
  low: "低风险",
};

export default function RiskBadge({ level, size = "normal" }: Props) {
  if (size === "small") {
    return <span className={`h-badge ${level}`}>{LABELS[level]}</span>;
  }
  return (
    <div className={`risk-banner ${level}`}>
      <div className={`risk-dot ${level}`} />
      <div>
        <div className={`risk-label ${level}`}>{LABELS[level]}</div>
        <div
          style={{
            fontSize: 12,
            color: level === "high" ? "#A32D2D" : level === "mid" ? "#854F0B" : "#3B6D11",
            marginTop: 2,
          }}
        >
          {level === "high"
            ? "建议24小时内联系医疗团队"
            : level === "mid"
              ? "建议联系团队或密切观察"
              : "继续观察与记录"}
        </div>
      </div>
    </div>
  );
}
