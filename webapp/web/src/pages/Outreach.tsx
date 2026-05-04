import { Mail } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function Outreach() {
  return (
    <>
      <Header
        title="Outreach Local"
        description="Scraping de Google Maps + envío de emails outreach."
      />
      <PageShell>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-accent" /> Estado
            </CardTitle>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={Mail}
              title="Outreach se ejecuta desde el CLI"
              description="Esta funcionalidad requiere un binario Go y SMTP configurado. Ajusta las credenciales SMTP y el niche del scraper en Configuración. La ejecución desde la webapp llegará en una próxima versión."
              action={
                <div className="flex gap-2">
                  <Button asChild variant="outline">
                    <Link to="/settings">Configurar SMTP</Link>
                  </Button>
                  <Button asChild variant="brand">
                    <a
                      href="https://github.com/gosom/google-maps-scraper"
                      target="_blank"
                      rel="noreferrer"
                    >
                      Ver scraper
                    </a>
                  </Button>
                </div>
              }
            />
          </CardContent>
        </Card>
      </PageShell>
    </>
  );
}
