"use client";

import Link from "next/link";
import { ButtonLink, useDetectedOS } from "@voca/ui";
import type { DetectedOS } from "@voca/ui";
import { BUILDS, type BuildKey } from "@/lib/releases";
import styles from "./DownloadCTA.module.css";

const MAP: Record<Exclude<DetectedOS, "linux" | "unknown">, BuildKey> = {
  "mac-arm64": "mac-arm64",
  "mac-x64": "mac-x64",
  windows: "windows-x64",
};

export function DownloadCTA() {
  const os = useDetectedOS();
  const key = os in MAP ? MAP[os as keyof typeof MAP] : null;
  const build = key ? BUILDS[key] : null;

  return (
    <div className={styles.wrap}>
      {build ? (
        <ButtonLink size="lg" href={`/api/download?os=${build.platform}&arch=${build.arch}`}>
          <DownloadGlyph />
          Download for {build.label.replace("macOS — ", "Mac ").replace(" — ", " ")}
        </ButtonLink>
      ) : (
        <ButtonLink size="lg" href="/api/download">
          <DownloadGlyph />
          Download
        </ButtonLink>
      )}
      <Link href="/download" className={styles.all}>
        {build ? "Other platforms" : "Choose your platform"} →
      </Link>
    </div>
  );
}

function DownloadGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M8 1.5v8.5m0 0L4.5 6.5M8 10l3.5-3.5M2.5 12.5h11"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
