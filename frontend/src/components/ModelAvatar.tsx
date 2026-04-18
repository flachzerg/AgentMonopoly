import type { CSSProperties } from "react";

import { resolveModelAvatar } from "../lib/modelAvatar";

export function ModelAvatar({
  officialModelId,
  displayName,
  vendorName,
  size = 40,
  className = "",
  variant = "default",
}: {
  readonly officialModelId?: string | null;
  readonly displayName?: string | null;
  readonly vendorName?: string | null;
  readonly size?: number;
  readonly className?: string;
  readonly variant?: "default" | "bare";
}) {
  const avatar = resolveModelAvatar({
    officialModelId,
    displayName,
    vendorName,
  });

  return (
    <span
      className={["model-avatar", variant === "bare" ? "model-avatar--bare" : "", className].join(" ").trim()}
      style={
        {
          width: `${size}px`,
          height: `${size}px`,
          ["--avatar-accent" as string]: avatar.accent,
          ["--avatar-surface" as string]: avatar.background,
        } as CSSProperties
      }
      aria-hidden="true"
    >
      {avatar.src === null ? (
        <span className="model-avatar__fallback">{avatar.fallback}</span>
      ) : (
        <img src={avatar.src} alt="" className="model-avatar__image" loading="lazy" />
      )}
    </span>
  );
}
