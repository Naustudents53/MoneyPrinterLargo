"use client";

export function PlatformGlyph({
  platform,
  size = 16,
}: {
  platform: string;
  size?: number;
}) {
  if (platform === "youtube" || platform === "yt") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="6" fill="#FF0000" opacity="0.15" />
        <path
          d="M19.6 7.4a2.5 2.5 0 00-1.76-1.77C16.4 5.25 12 5.25 12 5.25s-4.4 0-5.84.38A2.5 2.5 0 004.4 7.4C4 8.85 4 12 4 12s0 3.15.4 4.6a2.5 2.5 0 001.76 1.77C7.6 18.75 12 18.75 12 18.75s4.4 0 5.84-.38a2.5 2.5 0 001.76-1.77C20 15.15 20 12 20 12s0-3.15-.4-4.6z"
          fill="#FF4444"
          opacity="0.9"
        />
        <path d="M10 15.5l5-3.5-5-3.5v7z" fill="white" />
      </svg>
    );
  }
  if (platform === "twitter" || platform === "x") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="6" fill="rgba(255,255,255,0.06)" />
        <path
          d="M4 4l6.5 9L4 20h2l5.3-6.1L16 20h4l-6.8-9.3L19.5 4h-2l-4.9 5.6L8 4H4z"
          fill="#A8A29E"
        />
      </svg>
    );
  }
  return null;
}
