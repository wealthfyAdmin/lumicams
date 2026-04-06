import { redirect } from "next/navigation";

/**
 * Root route – immediately redirect to /dashboard.
 * Middleware will redirect unauthenticated users to /login.
 */
export default function RootPage() {
  redirect("/dashboard");
}
