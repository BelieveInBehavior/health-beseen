import React, { useEffect, useState } from "react";
import type { HistoryResponse, HistoryItem } from "../types";
import { getHistory } from "../api";

const LEVEL_LABELS: Record<string, string> = { high: "高风险", mid: "中风险", low: "低风险" };
const LEVEL_COLORS: Record<string, string> = { high: "#E24B4A", mid: "#EF9F27", low: "#639922" };

interface Props {
  sessionId: string;
  onViewResult: (assessmentId: string) => void;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function HistoryPage({ sessionId, onViewResult }: Props) {
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const resp = await getHistory(sessionId);
        setData(resp);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId]);

  if (loading) {
    return (
      <div className="history-scroll">
        <div className="history-empty">加载中…</div>
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="history-scroll">
        <div className="history-empty">暂无历史记录，完成一次评估后将在此显示</div>
      </div>
    );
  }

  const total = data.items.length;

  return (
    <div className="history-scroll">
      {/* Trend bars */}
      <div style={{
        background: "var(--bg-primary)",
        border: "0.5px solid var(--border-tertiary)",
        borderRadius: 10,
        padding: "14px 16px",
        marginBottom: 2,
      }}>
        <div className="trend-label">
          <span>近期风险趋势（{total}次评估）</span>
        </div>
        {(["high", "mid", "low"] as const).map((level) => {
          const count = data.trend[level] || 0;
          const pct = total > 0 ? Math.round((count / total) * 100) : 0;
          return (
            <div key={level} className="trend-bar-row">
              <span className="trend-label-sm">{LEVEL_LABELS[level]}</span>
              <div
                className="trend-bar"
                style={{ width: `${pct}%`, background: LEVEL_COLORS[level] }}
              />
              <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{count}次</span>
            </div>
          );
        })}
      </div>

      {/* History items */}
      {data.items.map((item) => (
        <div
          key={item.assessment_id}
          className="history-item"
          onClick={() => onViewResult(item.assessment_id)}
        >
          <span className={`h-badge ${item.risk_level}`}>
            {LEVEL_LABELS[item.risk_level]}
          </span>
          <div className="h-meta">
            <div className="h-title">{item.summary}</div>
            <div className="h-time">
              {formatTime(item.created_at)} · {item.rule_version}
            </div>
          </div>
          <span className="h-arrow">›</span>
        </div>
      ))}
    </div>
  );
}
