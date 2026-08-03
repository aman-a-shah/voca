/**
 * Single source of truth for downloads + updates.
 *
 * Binaries are published as GitHub Release assets by .github/workflows/release.yml
 * with stable names, so `releases/latest/download/<asset>` always resolves to the
 * newest build. The API routes and the download page both import from here.
 */

export const REPO = process.env.NEXT_PUBLIC_GH_REPO || "aman-a-shah/voca";

/**
 * Public repo that hosts the published installers and their GitHub Release.
 *
 * The source repo (`REPO`) is private, so its release assets 404 for the public.
 * Installers are therefore mirrored to a separate *public* repo and every
 * download / version lookup resolves against this one. Falls back to `REPO` when
 * unset, so local dev (or making the source repo public) keeps working unchanged.
 */
export const RELEASES_REPO =
  process.env.NEXT_PUBLIC_RELEASES_REPO || REPO;

/**
 * Where the "Download" buttons send people.
 *
 * Direct `releases/latest/download/<asset>` links only work while the published
 * asset names match {@link BUILDS}; when they drift (a rename, a release that
 * never shipped an asset) GitHub answers with a 404 page. Pointing the buttons
 * at the repo itself keeps them correct no matter what the latest release
 * happens to contain.
 */
export const REPO_URL = `https://github.com/${REPO}`;

/** Fallback version shown before the GitHub API responds (keep in sync with dictate/__init__.py). */
export const FALLBACK_VERSION = "1.0.1";

export type Platform = "mac" | "windows" | "linux";
export type Arch = "arm64" | "x64";

export type BuildKey = "mac-arm64" | "mac-x64" | "windows-x64";

export const BUILDS: Record<
  BuildKey,
  { label: string; sublabel: string; platform: Platform; arch: Arch; asset: string; ext: string }
> = {
  "mac-arm64": {
    label: "macOS — Apple Silicon",
    sublabel: "M1, M2, M3, M4",
    platform: "mac",
    arch: "arm64",
    asset: "Voca-mac-arm64.dmg",
    ext: ".dmg",
  },
  "mac-x64": {
    label: "macOS — Intel",
    sublabel: "2020 & earlier Macs",
    platform: "mac",
    arch: "x64",
    asset: "Voca-mac-x64.dmg",
    ext: ".dmg",
  },
  "windows-x64": {
    label: "Windows",
    sublabel: "Windows 10 & 11, 64-bit",
    platform: "windows",
    arch: "x64",
    asset: "VocaSetup-windows-x64.exe",
    ext: ".exe",
  },
};

export function latestAssetUrl(asset: string): string {
  return `https://github.com/${RELEASES_REPO}/releases/latest/download/${asset}`;
}

/** Map an OS/arch query to a build key. */
export function resolveBuild(os?: string | null, arch?: string | null): BuildKey | null {
  const o = (os || "").toLowerCase();
  const a = (arch || "").toLowerCase();
  if (o === "mac" || o === "macos" || o === "darwin") {
    return a === "arm64" || a === "aarch64" ? "mac-arm64" : "mac-x64";
  }
  if (o === "windows" || o === "win") return "windows-x64";
  return null;
}

export type ReleaseInfo = {
  version: string;
  notes: string;
  publishedAt: string | null;
  htmlUrl: string;
};

/**
 * Fetch the latest published release from GitHub (cached). Falls back to a static
 * version so the site/endpoints never hard-fail if the API is unreachable.
 */
export async function getLatestRelease(): Promise<ReleaseInfo> {
  try {
    const res = await fetch(`https://api.github.com/repos/${RELEASES_REPO}/releases/latest`, {
      headers: { Accept: "application/vnd.github+json" },
      next: { revalidate: 1800 },
    });
    if (!res.ok) throw new Error(`GitHub ${res.status}`);
    const data = await res.json();
    return {
      version: String(data.tag_name || FALLBACK_VERSION).replace(/^v/, ""),
      notes: String(data.body || ""),
      publishedAt: data.published_at ?? null,
      htmlUrl: data.html_url ?? `https://github.com/${RELEASES_REPO}/releases`,
    };
  } catch {
    return {
      version: FALLBACK_VERSION,
      notes: "",
      publishedAt: null,
      htmlUrl: `https://github.com/${RELEASES_REPO}/releases`,
    };
  }
}
