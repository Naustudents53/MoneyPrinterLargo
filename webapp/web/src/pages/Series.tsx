import { useEffect, useState } from "react";
import { BookOpen, FileText, Layers, ExternalLink } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { api, type SeriesEntry } from "@/lib/api";

export function Series() {
  const [series, setSeries] = useState<SeriesEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listSeries()
      .then(setSeries)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <Header
        eyebrow="Guiones"
        title="Series"
        description="Plantillas para videos largos definidas en config.json."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link to="/settings">Editar config.json</Link>
          </Button>
        }
      />

      <PageShell>
        <section className="page-hero">
          <div className="page-hero-inner">
            <div>
              <span className="eyebrow block mb-2">Long-form templates</span>
              <h1 className="page-title">
                Series con <span className="brand-text">estructura</span>
              </h1>
              <p className="page-subtitle">
                Plantillas de titulo, overlay y secciones para mantener consistencia
                cuando produzcas videos largos.
              </p>
            </div>
            <div className="metric-strip grid-cols-1 w-full sm:w-auto sm:min-w-[220px]">
              <div className="px-4 py-3">
                <span className="tiny-label">Plantillas</span>
                <div className="mt-1 font-mono text-[17px] font-semibold">{series.length}</div>
              </div>
            </div>
          </div>
        </section>

        {loading ? (
          <div className="app-card-grid">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-[280px]" />
            ))}
          </div>
        ) : series.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="Sin series configuradas"
            description="Las series se definen como un array 'series' en config.json. Cada entrada incluye id, title_template, thumbnail_overlay y opcionalmente un script_brief y section_themes."
            action={
              <Button asChild variant="brand">
                <Link to="/settings">Abrir configuración</Link>
              </Button>
            }
          />
        ) : (
          <div className="app-card-grid">
            {series.map((s) => (
              <SeriesCard key={s.id} entry={s} />
            ))}
          </div>
        )}
      </PageShell>
    </>
  );
}

function SeriesCard({ entry }: { entry: SeriesEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="studio-hover">
      <CardHeader className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="rounded-lg bg-accent/10 p-2 text-accent shrink-0">
              <BookOpen className="h-4 w-4" />
            </div>
            <CardTitle className="truncate">{entry.name || entry.id}</CardTitle>
          </div>
          <Badge variant="outline" className="font-mono text-[10px]">
            {entry.id}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {entry.title_template && (
          <Block icon={FileText} label="Title template" value={entry.title_template} />
        )}
        {entry.thumbnail_overlay && (
          <Block icon={Layers} label="Thumbnail overlay" value={entry.thumbnail_overlay} />
        )}
        {entry.script_brief && (
          <div>
            <div className="text-[10px] uppercase text-muted-foreground font-semibold mb-1">
              Script brief
            </div>
            <p className={"soft-panel text-xs text-muted-foreground p-3 " + (open ? "" : "line-clamp-4")}>
              {entry.script_brief}
            </p>
            {entry.script_brief.length > 200 && (
              <Button
                variant="link"
                size="sm"
                onClick={() => setOpen(!open)}
                className="px-0 h-auto mt-1"
              >
                {open ? "Ver menos" : "Ver más"}
              </Button>
            )}
          </div>
        )}
        {entry.section_themes && entry.section_themes.length > 0 && (
          <div>
            <div className="text-[10px] uppercase text-muted-foreground font-semibold mb-2">
              Sections ({entry.section_themes.length})
            </div>
            <ol className="space-y-1.5 text-xs text-muted-foreground list-decimal list-inside">
              {entry.section_themes.slice(0, open ? undefined : 3).map((t, i) => (
                <li key={i} className="line-clamp-2">
                  {t}
                </li>
              ))}
            </ol>
            {entry.section_themes.length > 3 && !open && (
              <Button
                variant="link"
                size="sm"
                onClick={() => setOpen(true)}
                className="px-0 h-auto mt-1 gap-1"
              >
                Ver las {entry.section_themes.length} secciones <ExternalLink className="h-3 w-3" />
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Block({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FileText;
  label: string;
  value: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] uppercase text-muted-foreground font-semibold mb-1">
        <Icon className="h-3 w-3" /> {label}
      </div>
      <p className="soft-panel text-xs font-mono px-2 py-1.5 break-words">
        {value}
      </p>
    </div>
  );
}
