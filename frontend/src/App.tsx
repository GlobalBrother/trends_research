import { Suspense, lazy, useState, useEffect, useCallback } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import DashboardLayout from "./components/layout/DashboardLayout";
import { validateToken, isAdmin } from "./lib/api";
import { Redirect } from "wouter";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const TrendExplorer = lazy(() => import("./pages/TrendExplorer"));
const ResearchProjects = lazy(() => import("./pages/ResearchProjects"));
const Reports = lazy(() => import("./pages/Reports"));
const SavedViews = lazy(() => import("./pages/SavedViews"));
const Alerts = lazy(() => import("./pages/Alerts"));
const Settings = lazy(() => import("./pages/Settings"));
const MyAds = lazy(() => import("./pages/MyAds"));
const Login = lazy(() => import("./pages/Login"));
const NotFound = lazy(() => import("./pages/NotFound"));

function RouteFallback() {
  return (
    <div className="flex items-center justify-center h-full min-h-[40vh] bg-background">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  );
}

/** Wrapper that redirects non-admin users away from admin-only routes */
function AdminRoute({ component: Component }: { component: React.ComponentType }) {
  if (!isAdmin()) {
    return <Redirect to="/" />;
  }
  return <Component />;
}

function AuthenticatedRouter() {
  return (
    <DashboardLayout>
      <Suspense fallback={<RouteFallback />}>
        <Switch>
          <Route path="/" component={Dashboard} />
          <Route path="/explorer" component={TrendExplorer} />
          <Route path="/projects" component={ResearchProjects} />
          <Route path="/reports" component={Reports} />
          <Route path="/saved" component={SavedViews} />
          <Route path="/alerts" component={Alerts} />
          <Route path="/my-ads" component={MyAds} />
          <Route path="/settings">{() => <AdminRoute component={Settings} />}</Route>
          <Route path="/404" component={NotFound} />
          <Route component={NotFound} />
        </Switch>
      </Suspense>
    </DashboardLayout>
  );
}

function AppRouter() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      setAuthed(false);
      return;
    }
    validateToken(token)
      .then(() => setAuthed(true))
      .catch(() => {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("auth_email");
        localStorage.removeItem("auth_role");
        setAuthed(false);
      });
  }, []);

  const handleLogin = useCallback((token: string, email: string, role: string) => {
    localStorage.setItem("auth_token", token);
    localStorage.setItem("auth_email", email);
    localStorage.setItem("auth_role", role);
    setAuthed(true);
  }, []);

  // Still checking auth
  if (authed === null) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (!authed) {
    return (
      <Suspense fallback={<RouteFallback />}>
        <Switch>
          <Route path="/login">
            <Login onLogin={handleLogin} />
          </Route>
          <Route>
            <Login onLogin={handleLogin} />
          </Route>
        </Switch>
      </Suspense>
    );
  }

  return <AuthenticatedRouter />;
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="light" switchable>
        <TooltipProvider>
          <Toaster />
          <AppRouter />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
