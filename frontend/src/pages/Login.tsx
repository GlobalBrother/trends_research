/**
 * Login — OTP-based authentication page
 * Step 1: Enter email → request OTP
 * Step 2: Enter 6-char OTP code → verify → store token
 */
import { useState } from "react";
import { TrendingUp, Mail, KeyRound, Loader2, ArrowLeft } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { requestOtp, verifyOtp } from "@/lib/api";

interface LoginProps {
  onLogin: (token: string, email: string, role: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [step, setStep] = useState<"email" | "otp">("email");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRequestOtp = async () => {
    if (!email.trim()) {
      toast.error("Please enter your email address");
      return;
    }
    setLoading(true);
    try {
      await requestOtp(email.trim());
      toast.success("OTP sent! Check your email.");
      setStep("otp");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to send OTP. Your email may not be whitelisted.";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async () => {
    if (!otp.trim()) {
      toast.error("Please enter the OTP code");
      return;
    }
    setLoading(true);
    try {
      const res = await verifyOtp(email.trim(), otp.trim());
      const { token, role } = res.data;
      toast.success("Login successful!");
      onLogin(token, email.trim(), role);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Invalid or expired OTP code.";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="w-full max-w-md mx-4">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center">
            <TrendingUp className="w-6 h-6 text-primary-foreground" />
          </div>
          <span className="text-2xl font-bold text-white tracking-tight">
            Trends Research
          </span>
        </div>

        {/* Card */}
        <div className="bg-card rounded-xl border border-border shadow-2xl p-8">
          <h2 className="text-xl font-semibold text-card-foreground mb-1 text-center">
            {step === "email" ? "Welcome back" : "Enter verification code"}
          </h2>
          <p className="text-sm text-muted-foreground mb-6 text-center">
            {step === "email"
              ? "Sign in with your whitelisted email address"
              : `We sent a code to ${email}`}
          </p>

          {step === "email" ? (
            <div className="space-y-4">
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  type="email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleRequestOtp()}
                  className="pl-10 h-11"
                  autoFocus
                />
              </div>
              <Button
                className="w-full h-11"
                onClick={handleRequestOtp}
                disabled={loading}
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                ) : null}
                Send login code
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Enter 6-character code"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.toUpperCase())}
                  onKeyDown={(e) => e.key === "Enter" && handleVerifyOtp()}
                  className="pl-10 h-11 text-center tracking-[0.3em] font-mono text-lg"
                  maxLength={6}
                  autoFocus
                />
              </div>
              <Button
                className="w-full h-11"
                onClick={handleVerifyOtp}
                disabled={loading}
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                ) : null}
                Verify and sign in
              </Button>
              <Button
                variant="ghost"
                className="w-full text-sm"
                onClick={() => {
                  setStep("email");
                  setOtp("");
                }}
              >
                <ArrowLeft className="w-3 h-3 mr-1" />
                Use a different email
              </Button>
            </div>
          )}
        </div>

        <p className="text-xs text-slate-500 text-center mt-6">
          Intelligence Platform v2.0
        </p>
      </div>
    </div>
  );
}
