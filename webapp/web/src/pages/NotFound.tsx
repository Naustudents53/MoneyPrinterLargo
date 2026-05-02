import { Link } from "react-router-dom";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Compass } from "lucide-react";

export function NotFound() {
  return (
    <>
      <Header title="404" description="Página no encontrada" />
      <PageShell>
        <div className="text-center py-24 space-y-4">
          <div className="inline-flex rounded-full bg-primary/10 p-4">
            <Compass className="h-8 w-8 text-primary" />
          </div>
          <h2 className="font-display text-3xl font-bold">Esta ruta no existe</h2>
          <p className="text-muted-foreground">Quizá te equivocaste de URL.</p>
          <Button asChild variant="brand">
            <Link to="/">Volver al dashboard</Link>
          </Button>
        </div>
      </PageShell>
    </>
  );
}
