import React from "react";
import { Play, Image as ImageIcon, ExternalLink, AlertCircle } from "lucide-react";

interface MediaPreviewProps {
  url?: string;
  type?: "video" | "image" | "auto";
  thumbnail?: string;
  platform?: string;
  className?: string;
}

export function MediaPreview({ url, type = "auto", thumbnail, platform, className = "" }: MediaPreviewProps) {
  const [error, setError] = React.useState(false);

  if (!url) return null;

  // 1. Handle TikTok
  if (platform?.toLowerCase() === "tiktok" || url.includes("tiktok.com")) {
    const videoId = url.match(/\/v\/(\d+)/)?.[1] || url.match(/\/video\/(\d+)/)?.[1];
    if (videoId) {
      return (
        <div className={`aspect-[9/16] w-full max-w-[350px] mx-auto rounded-lg overflow-hidden bg-black border border-border ${className}`}>
          <iframe
            src={`https://www.tiktok.com/embed/v2/${videoId}`}
            className="w-full h-full"
            allowFullScreen
            scrolling="no"
            allow="autoplay; encrypted-media"
          />
        </div>
      );
    }
  }

  // 2. Handle YouTube
  if (platform?.toLowerCase() === "youtube" || url.includes("youtube.com") || url.includes("youtu.be")) {
    let videoId = "";
    if (url.includes("youtube.com/watch")) {
      videoId = new URL(url).searchParams.get("v") || "";
    } else if (url.includes("youtu.be/")) {
      videoId = url.split("/").pop() || "";
    } else if (url.includes("youtube.com/embed/")) {
      videoId = url.split("/").pop() || "";
    }
    
    if (videoId) {
      return (
        <div className={`aspect-video w-full rounded-lg overflow-hidden bg-black border border-border ${className}`}>
          <iframe
            src={`https://www.youtube.com/embed/${videoId}`}
            className="w-full h-full"
            allowFullScreen
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          />
        </div>
      );
    }
  }

  // 3. Handle Direct Video (MP4, etc.)
  const isVideo = type === "video" || url.endsWith(".mp4") || url.endsWith(".webm") || url.includes("static-gp.gethookd.ai") && url.includes(".mp4");
  if (isVideo && !error) {
    return (
      <div className={`relative rounded-lg overflow-hidden bg-black border border-border ${className}`}>
        <video
          src={url}
          poster={thumbnail}
          controls
          className="w-full h-auto max-h-[500px]"
          onError={() => setError(true)}
        >
          Your browser does not support the video tag.
        </video>
      </div>
    );
  }

  // 4. Handle Image
  const isImage = type === "image" || url.match(/\.(jpg|jpeg|png|webp|gif|avif)/i) || (url.includes("static-gp.gethookd.ai") && !url.includes(".mp4"));
  if ((isImage || error) && !url.includes("tiktok.com")) {
    return (
      <div className={`relative rounded-lg overflow-hidden bg-muted border border-border ${className}`}>
        <img
          src={url}
          alt="Preview"
          className="w-full h-auto max-h-[500px] object-contain"
          onError={(e) => {
            (e.target as HTMLImageElement).src = thumbnail || "";
          }}
        />
        {error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/50 text-white p-4 text-center">
            <AlertCircle className="w-8 h-8 mb-2 opacity-50" />
            <p className="text-xs">Failed to load media. <a href={url} target="_blank" rel="noopener noreferrer" className="underline">View original</a></p>
          </div>
        )}
      </div>
    );
  }

  // Fallback
  return (
    <div className={`flex flex-col items-center justify-center p-8 rounded-lg border border-dashed border-border bg-muted/30 ${className}`}>
      <ExternalLink className="w-8 h-8 text-muted-foreground mb-3 opacity-20" />
      <p className="text-xs text-muted-foreground text-center mb-4">No interactive preview available for this source.</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-[11px] font-medium text-primary hover:underline px-3 py-1.5 border border-primary/20 rounded-md bg-primary/5"
      >
        View original on {platform || "platform"}
      </a>
    </div>
  );
}
