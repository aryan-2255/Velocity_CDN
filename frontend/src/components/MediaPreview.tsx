import { api } from "../api";

type Kind = "video" | "audio" | "image" | "pdf" | "text" | "other";

function kindOf(contentType: string): Kind {
  if (contentType.startsWith("video/")) return "video";
  if (contentType.startsWith("audio/")) return "audio";
  if (contentType.startsWith("image/")) return "image";
  if (contentType === "application/pdf") return "pdf";
  if (contentType.startsWith("text/") || contentType === "application/json") return "text";
  return "other";
}

/** Plays or shows a file straight from the CDN. The browser requests the URL
 *  itself rather than going through fetch(), so video seeking uses real HTTP
 *  range requests against the edge instead of buffering the whole file first. */
export function MediaPreview({
  fileKey,
  contentType,
  region,
  onClose,
}: {
  fileKey: string;
  contentType: string;
  region?: string;
  onClose: () => void;
}) {
  const url = api.contentUrl(fileKey, region);
  const kind = kindOf(contentType);

  return (
    <div
      className="mt-3 rounded border p-3"
      style={{ borderColor: "var(--border)", background: "var(--plane)" }}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="truncate text-xs font-medium" style={{ color: "var(--text-primary)" }}>
          {fileKey}
          <span className="ml-2 font-normal" style={{ color: "var(--text-muted)" }}>
            {contentType}
            {region ? ` · via ${region}` : ""}
          </span>
        </span>
        <div className="flex shrink-0 items-center gap-3">
          <a
            href={url}
            download={fileKey.split("/").pop()}
            className="text-xs font-medium"
            style={{ color: "var(--series-1)" }}
          >
            Download
          </a>
          <button onClick={onClose} className="text-xs" style={{ color: "var(--text-muted)" }}>
            Close
          </button>
        </div>
      </div>

      {kind === "video" && (
        <video src={url} controls preload="metadata" className="max-h-80 w-full rounded bg-black" />
      )}
      {kind === "audio" && <audio src={url} controls className="w-full" />}
      {kind === "image" && (
        <img src={url} alt={fileKey} className="max-h-80 w-full rounded object-contain" />
      )}
      {kind === "pdf" && <iframe src={url} title={fileKey} className="h-80 w-full rounded border-0" />}
      {kind === "text" && (
        <iframe src={url} title={fileKey} className="h-56 w-full rounded border-0 bg-white" />
      )}
      {kind === "other" && (
        <p className="py-4 text-center text-xs" style={{ color: "var(--text-muted)" }}>
          No inline preview for {contentType}. Use Download.
        </p>
      )}

      <p className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
        Served through the CDN, so this counts as a real request and appears in the feed below.
        Video seeking issues HTTP range requests, which the edge answers from its cached copy.
      </p>
    </div>
  );
}
