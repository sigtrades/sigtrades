import { useEffect } from "react";
import { useAuth } from "../store/auth";

export default function AuthBootstrap({ children }: { children: React.ReactNode }) {
  const hydrate = useAuth((s) => s.hydrate);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  return <>{children}</>;
}
