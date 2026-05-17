import { Link } from "react-router-dom";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Compass } from "lucide-react";

export function NotFound() {
  return (
    <>
      <Header eyebrow="Ruta" title="404" description="Pagina no encontrada" />
      <PageShell>
        <section className="page-hero">
          <div className="page-hero-inner justify-center text-center">
            <div className="mx-auto max-w-xl">
              <div className="mx-auto mb-5 inline-flex rounded-2xl bg-primary/10 p-4 text-primary">
                <Compass className="h-8 w-8" />
              </div>
              <span className="eyebrow block mb-2">404</span>
              <h1 className="page-title">Esta ruta no existe</h1>
              <p className="page-subtitle mx-auto">
                Vuelve al dashboard para seguir operando el estudio.
              </p>
              <Button asChild variant="brand" className="mt-5">
                <Link to="/">Volver al dashboard</Link>
              </Button>
            </div>
          </div>
        </section>
      </PageShell>
    </>
  );
}
