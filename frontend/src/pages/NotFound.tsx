import { useLocation } from "wouter";
import { AlertCircle, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  const [, setLocation] = useLocation();

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="text-center max-w-md">
        <div className="inline-flex items-center justify-center w-14 h-14 bg-muted mb-6">
          <AlertCircle className="w-7 h-7 text-muted-foreground" />
        </div>
        <p className="section-label mb-2">Error 404</p>
        <h1 className="text-3xl font-bold tracking-tight mb-2">Page Not Found</h1>
        <p className="text-sm text-muted-foreground leading-relaxed mb-6">
          The page you are looking for does not exist or has been moved.
        </p>
        <Button
          size="sm"
          className="h-8 text-xs gap-1.5"
          onClick={() => setLocation("/")}
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Dashboard
        </Button>
      </div>
    </div>
  );
}
