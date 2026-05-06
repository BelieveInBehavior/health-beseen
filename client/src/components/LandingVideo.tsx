import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

function landingSrc(): string {
  const base = import.meta.env.BASE_URL;
  if (base.endsWith("/")) return `${base}landing.mp4`;
  return `${base}/landing.mp4`;
}

/** 每次进入应用全屏自动播放落地视频，播完进入主界面；静音以满足浏览器自动播放策略。 */
export default function LandingVideo({ src }: { src?: string }) {
  const resolved = src ?? landingSrc();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const aliveRef = useRef(true);
  const [show, setShow] = useState(true);

  const dismiss = useCallback(() => {
    setShow(false);
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!show) return;
    const el = videoRef.current;
    if (!el) return;
    el.defaultMuted = true;
    el.muted = true;
    const p = el.play();
    if (p !== undefined) {
      p.catch(() => {
        /* 部分浏览器需用户手势；静音 autoplay 通常仍可用 */
      });
    }
  }, [show, resolved]);

  const onVideoError = useCallback(
    (e: React.SyntheticEvent<HTMLVideoElement>) => {
      const code = e.currentTarget.error?.code;
      /* React Strict Mode 会先卸载再挂载，浏览器中止加载 → MEDIA_ERR_ABORTED，勿当成失败 */
      if (code === MediaError.MEDIA_ERR_ABORTED) return;
      if (!aliveRef.current) return;
      console.warn("[LandingVideo] 无法加载或解码视频，跳过落地层:", resolved);
      setShow(false);
    },
    [resolved],
  );

  if (!show || typeof document === "undefined") return null;

  return createPortal(
    <div className="landing-video-overlay" aria-hidden={false}>
      <video
        ref={videoRef}
        className="landing-video"
        src={resolved}
        playsInline
        autoPlay
        muted
        preload="auto"
        onEnded={dismiss}
        onError={onVideoError}
      />
    </div>,
    document.body,
  );
}
